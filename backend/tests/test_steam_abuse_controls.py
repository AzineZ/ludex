from datetime import UTC, datetime, timedelta
from ipaddress import ip_address
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.abuse.steam import (
    RateLimitExceeded,
    SteamAbuseController,
    fingerprint_subject,
    reserve_provider_call,
    reserve_refresh,
    reserve_session_creation,
    resolve_client_address,
)
from app.database import Base
from app.dependencies import BudgetedSteamClient
from app.models import SteamUsageEvent


NOW = datetime(2026, 9, 6, 20, tzinfo=UTC)
HMAC_KEY = b"test-rate-limit-key-with-32-bytes!!"


@pytest.fixture
def database_session() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def test_subject_fingerprint_is_fixed_and_identifier_free() -> None:
    digest = fingerprint_subject(HMAC_KEY, "identifier", "private-vanity")

    assert len(digest) == 32
    assert b"private-vanity" not in digest
    assert digest == fingerprint_subject(
        HMAC_KEY,
        "identifier",
        "private-vanity",
    )


def test_hosted_client_address_requires_first_public_forwarded_ip() -> None:
    assert resolve_client_address(
        deployment_environment="production",
        socket_host="10.0.0.2",
        forwarded_for="8.8.8.8, 10.0.0.2",
    ) == "8.8.8.8"
    assert ip_address("8.8.8.8").is_global

    with pytest.raises(ValueError):
        resolve_client_address(
            deployment_environment="staging",
            socket_host="10.0.0.2",
            forwarded_for=None,
        )
    with pytest.raises(ValueError):
        resolve_client_address(
            deployment_environment="staging",
            socket_host="10.0.0.2",
            forwarded_for="127.0.0.1",
        )


def test_local_client_address_uses_socket_without_proxy_trust() -> None:
    assert resolve_client_address(
        deployment_environment="local",
        socket_host="testclient",
        forwarded_for="203.0.113.9",
    ) == "testclient"


def test_attempt_limits_apply_before_any_identifier_result() -> None:
    controller = SteamAbuseController()

    for _ in range(5):
        controller.record_session_attempt("198.51.100.7", now=NOW)

    with pytest.raises(RateLimitExceeded) as error:
        controller.record_session_attempt("198.51.100.7", now=NOW)

    assert 1 <= error.value.retry_after <= 600


def test_attempt_limit_has_rolling_daily_ceiling() -> None:
    controller = SteamAbuseController()

    for index in range(20):
        controller.record_session_attempt(
            "198.51.100.8",
            now=NOW + timedelta(minutes=11 * index),
        )

    with pytest.raises(RateLimitExceeded) as error:
        controller.record_session_attempt(
            "198.51.100.8",
            now=NOW + timedelta(minutes=221),
        )

    assert 1 <= error.value.retry_after <= 24 * 60 * 60


def test_session_creation_budget_is_per_identifier_and_global(
    database_session: Session,
) -> None:
    subject = fingerprint_subject(HMAC_KEY, "identifier", "some-player")

    for _ in range(3):
        reserve_session_creation(database_session, subject, now=NOW)

    with pytest.raises(RateLimitExceeded):
        reserve_session_creation(database_session, subject, now=NOW)

    assert database_session.scalar(
        select(func.count()).select_from(SteamUsageEvent)
    ) == 3
    assert all(
        len(event.subject_digest) == 32
        for event in database_session.scalars(select(SteamUsageEvent))
    )


def test_provider_call_budget_stops_at_300_per_utc_day(
    database_session: Session,
) -> None:
    global_subject = fingerprint_subject(HMAC_KEY, "global", "steam")
    database_session.add_all(
        SteamUsageEvent(
            category="provider_call",
            subject_digest=global_subject,
            created_at=NOW,
            expires_at=datetime(2026, 9, 7, tzinfo=UTC),
        )
        for _ in range(300)
    )
    database_session.commit()

    with pytest.raises(RateLimitExceeded) as error:
        reserve_provider_call(database_session, HMAC_KEY, now=NOW)

    assert error.value.retry_after == 4 * 60 * 60


def test_refresh_budget_enforces_cooldown_and_four_per_day(
    database_session: Session,
) -> None:
    subject = fingerprint_subject(HMAC_KEY, "refresh", "session-and-steam")

    reserve_refresh(database_session, subject, now=NOW)
    with pytest.raises(RateLimitExceeded) as cooldown:
        reserve_refresh(
            database_session,
            subject,
            now=NOW + timedelta(minutes=14),
        )
    assert cooldown.value.retry_after == 60

    for hours in (1, 2, 3):
        reserve_refresh(
            database_session,
            subject,
            now=NOW + timedelta(hours=hours),
        )
    with pytest.raises(RateLimitExceeded):
        reserve_refresh(
            database_session,
            subject,
            now=NOW + timedelta(hours=4),
        )


def test_expired_usage_events_are_removed_during_reservation(
    database_session: Session,
) -> None:
    database_session.add(
        SteamUsageEvent(
            category="session_create",
            subject_digest=b"x" * 32,
            created_at=NOW - timedelta(days=2),
            expires_at=NOW - timedelta(days=1),
        )
    )
    database_session.commit()

    reserve_session_creation(
        database_session,
        fingerprint_subject(HMAC_KEY, "identifier", "new"),
        now=NOW,
    )

    assert database_session.scalar(
        select(func.count()).select_from(SteamUsageEvent)
    ) == 1


def test_sync_concurrency_rejects_same_identity_and_third_global_slot() -> None:
    controller = SteamAbuseController()

    with controller.steam_sync("steam-1"):
        with pytest.raises(RateLimitExceeded):
            with controller.steam_sync("steam-1"):
                pass
        with controller.steam_sync("steam-2"):
            with pytest.raises(RateLimitExceeded):
                with controller.steam_sync("steam-3"):
                    pass


def test_budgeted_client_reserves_before_lazy_construction(
    database_session: Session,
) -> None:
    inner_client = MagicMock()
    inner_client.get_profile.return_value = "profile"
    client_factory = MagicMock(return_value=inner_client)
    client = BudgetedSteamClient(
        database_session,
        HMAC_KEY,
        clock=lambda: NOW,
        client_factory=client_factory,
    )

    client_factory.assert_not_called()
    assert client.get_profile("76561198000000000") == "profile"

    client_factory.assert_called_once_with()
    inner_client.get_profile.assert_called_once_with("76561198000000000")
    events = database_session.scalars(select(SteamUsageEvent)).all()
    assert [event.category for event in events] == ["provider_call"]

    client.close()
    inner_client.close.assert_called_once_with()
