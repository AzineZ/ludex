from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.gemini.prompt.quota import (
    MAX_PROMPT_ATTEMPTS,
    SESSION_PROMPT_DAILY_LIMIT,
    PromptQuotaExceeded,
    PromptQuotaPolicy,
    PromptQuotaReason,
    complete_prompt_reservation,
    reserve_prompt_attempt,
    reserve_prompt_message,
)
from app.models import (
    GeminiPromptReservation,
    GeminiPromptUsageEvent,
    Profile,
    SteamAccessSession,
)


NOW = datetime(2026, 9, 10, 18, tzinfo=UTC)


@pytest.fixture
def quota_database():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        profile = Profile(steam_id="76561198000000001", display_name="Player")
        session.add(profile)
        session.flush()
        access = SteamAccessSession(
            token_digest=b"x" * 32,
            profile_id=profile.id,
            created_at=NOW - timedelta(minutes=1),
            expires_at=NOW + timedelta(days=7),
        )
        session.add(access)
        session.commit()
        yield session, access.id
    engine.dispose()


def _reserve_message(
    session: Session,
    access_session_id: int,
    *,
    now: datetime = NOW,
    reservation_id: str = "reservation",
    lease_seconds: int = 60,
):
    return reserve_prompt_message(
        session,
        access_session_id=access_session_id,
        now=now,
        lease_duration=timedelta(seconds=lease_seconds),
        reservation_id_factory=lambda: reservation_id,
    )


def _assert_reason(error, reason: PromptQuotaReason) -> None:
    assert error.value.reason is reason
    assert error.value.retry_after_seconds >= 1
    assert str(error.value) == "AI recommendations are temporarily unavailable."


def test_one_in_flight_message_is_enforced_and_completion_releases_it(
    quota_database,
) -> None:
    session, access_session_id = quota_database
    first = _reserve_message(session, access_session_id)

    with pytest.raises(PromptQuotaExceeded) as error:
        _reserve_message(
            session,
            access_session_id,
            reservation_id="second",
        )
    _assert_reason(error, PromptQuotaReason.PROMPT_IN_FLIGHT)

    assert complete_prompt_reservation(
        session,
        reservation_id=first.reservation_id,
        now=NOW + timedelta(seconds=1),
    )
    second = _reserve_message(
        session,
        access_session_id,
        now=NOW + timedelta(seconds=2),
        reservation_id="second",
    )
    assert second.reservation_id == "second"


def test_message_limit_is_five_per_pacific_day(quota_database) -> None:
    session, access_session_id = quota_database
    for index in range(SESSION_PROMPT_DAILY_LIMIT):
        current = NOW + timedelta(seconds=index * 2)
        reservation = _reserve_message(
            session,
            access_session_id,
            now=current,
            reservation_id=f"message-{index}",
        )
        complete_prompt_reservation(
            session,
            reservation_id=reservation.reservation_id,
            now=current + timedelta(seconds=1),
        )

    with pytest.raises(PromptQuotaExceeded) as error:
        _reserve_message(
            session,
            access_session_id,
            now=NOW + timedelta(seconds=20),
            reservation_id="message-6",
        )
    _assert_reason(error, PromptQuotaReason.SESSION_DAILY_LIMIT)


def test_message_limit_resets_at_pacific_midnight(quota_database) -> None:
    session, access_session_id = quota_database
    before_reset = datetime(2026, 9, 10, 6, 50, tzinfo=UTC)
    for index in range(SESSION_PROMPT_DAILY_LIMIT):
        current = before_reset + timedelta(seconds=index * 2)
        reservation = _reserve_message(
            session,
            access_session_id,
            now=current,
            reservation_id=f"prior-{index}",
        )
        complete_prompt_reservation(
            session,
            reservation_id=reservation.reservation_id,
            now=current + timedelta(seconds=1),
        )

    after_reset = datetime(2026, 9, 10, 7, 1, tzinfo=UTC)
    reservation = _reserve_message(
        session,
        access_session_id,
        now=after_reset,
        reservation_id="new-day",
    )
    assert reservation.reservation_id == "new-day"


def test_expired_lease_is_released_durably(quota_database) -> None:
    session, access_session_id = quota_database
    _reserve_message(
        session,
        access_session_id,
        reservation_id="expired",
        lease_seconds=1,
    )

    replacement = _reserve_message(
        session,
        access_session_id,
        now=NOW + timedelta(seconds=2),
        reservation_id="replacement",
    )

    expired = session.get(GeminiPromptReservation, "expired")
    assert expired.completed_at == expired.expires_at
    assert replacement.reservation_id == "replacement"


def test_each_message_allows_at_most_two_provider_attempts(
    quota_database,
) -> None:
    session, access_session_id = quota_database
    reservation = _reserve_message(session, access_session_id)
    policy = PromptQuotaPolicy(15, 500)

    attempts = [
        reserve_prompt_attempt(
            session,
            reservation_id=reservation.reservation_id,
            policy=policy,
            now=NOW + timedelta(seconds=index),
        )
        for index in range(MAX_PROMPT_ATTEMPTS)
    ]
    assert [attempt.attempt_number for attempt in attempts] == [1, 2]

    with pytest.raises(PromptQuotaExceeded) as error:
        reserve_prompt_attempt(
            session,
            reservation_id=reservation.reservation_id,
            policy=policy,
            now=NOW + timedelta(seconds=3),
        )
    _assert_reason(error, PromptQuotaReason.ATTEMPT_LIMIT)


def test_policy_reserves_twenty_percent_and_honors_lower_ceiling() -> None:
    ordinary = PromptQuotaPolicy(15, 500)
    lowered = PromptQuotaPolicy(15, 500, global_daily_ceiling=25)

    assert ordinary.minute_budget == 12
    assert ordinary.daily_budget == 400
    assert lowered.daily_budget == 25


def test_global_minute_budget_is_reserved_before_provider_io(
    quota_database,
) -> None:
    session, access_session_id = quota_database
    active = _reserve_message(session, access_session_id)
    completed = GeminiPromptReservation(
        id="completed",
        access_session_id=access_session_id,
        created_at=NOW - timedelta(minutes=2),
        expires_at=NOW - timedelta(minutes=1),
        completed_at=NOW - timedelta(minutes=1),
    )
    session.add(completed)
    session.flush()
    session.add_all(
        GeminiPromptUsageEvent(
            reservation_id=completed.id,
            created_at=NOW - timedelta(seconds=30 - index),
            expires_at=NOW + timedelta(hours=6),
        )
        for index in range(4)
    )
    session.commit()

    with pytest.raises(PromptQuotaExceeded) as error:
        reserve_prompt_attempt(
            session,
            reservation_id=active.reservation_id,
            policy=PromptQuotaPolicy(5, 20),
            now=NOW,
        )
    _assert_reason(error, PromptQuotaReason.PROJECT_MINUTE_LIMIT)


def test_global_daily_budget_uses_pacific_day(quota_database) -> None:
    session, access_session_id = quota_database
    active = _reserve_message(session, access_session_id)
    completed = GeminiPromptReservation(
        id="daily-completed",
        access_session_id=access_session_id,
        created_at=NOW - timedelta(hours=3),
        expires_at=NOW - timedelta(hours=2),
        completed_at=NOW - timedelta(hours=2),
    )
    session.add(completed)
    session.flush()
    session.add(
        GeminiPromptUsageEvent(
            reservation_id=completed.id,
            created_at=NOW - timedelta(hours=1),
            expires_at=NOW + timedelta(hours=6),
        )
    )
    session.commit()

    with pytest.raises(PromptQuotaExceeded) as error:
        reserve_prompt_attempt(
            session,
            reservation_id=active.reservation_id,
            policy=PromptQuotaPolicy(100, 2),
            now=NOW,
        )
    _assert_reason(error, PromptQuotaReason.PROJECT_DAILY_LIMIT)


def test_revoked_session_cannot_reserve_a_message(quota_database) -> None:
    session, access_session_id = quota_database
    access = session.get(SteamAccessSession, access_session_id)
    access.revoked_at = NOW
    session.commit()

    with pytest.raises(PromptQuotaExceeded) as error:
        _reserve_message(session, access_session_id)
    _assert_reason(error, PromptQuotaReason.INVALID_SESSION)


def test_quota_rows_never_store_prompt_text() -> None:
    reservation_columns = set(GeminiPromptReservation.__table__.columns.keys())
    event_columns = set(GeminiPromptUsageEvent.__table__.columns.keys())

    assert reservation_columns == {
        "id",
        "access_session_id",
        "created_at",
        "expires_at",
        "completed_at",
    }
    assert event_columns == {
        "id",
        "reservation_id",
        "created_at",
        "expires_at",
    }
