from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import CheckConstraint, create_engine, event, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Profile, SteamAccessSession


NOW = datetime(2026, 9, 2, 12, tzinfo=UTC)
DIGEST = bytes(range(32))


def _engine():
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _) -> None:
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    return engine


def _profile() -> Profile:
    return Profile(
        steam_id="76561198000000000",
        display_name="Test Player",
    )


def _access_session(**overrides) -> SteamAccessSession:
    values = {
        "token_digest": DIGEST,
        "created_at": NOW,
        "expires_at": NOW + timedelta(days=7),
        "revoked_at": None,
    }
    values.update(overrides)
    return SteamAccessSession(**values)


def test_access_session_defines_digest_lifetime_and_profile_boundary() -> None:
    table = SteamAccessSession.__table__

    assert set(table.columns.keys()) == {
        "id",
        "token_digest",
        "profile_id",
        "created_at",
        "expires_at",
        "revoked_at",
    }
    assert table.c.token_digest.type.length == 32
    assert table.c.token_digest.nullable is False
    assert table.c.token_digest.unique is True
    assert table.c.token_digest.index is True
    assert table.c.profile_id.index is True
    assert table.c.expires_at.index is True

    foreign_key = next(iter(table.c.profile_id.foreign_keys))
    assert foreign_key.target_fullname == "profiles.id"
    assert foreign_key.ondelete == "CASCADE"

    constraint_names = {
        constraint.name
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert constraint_names == {
        "ck_steam_access_sessions_digest_length",
        "ck_steam_access_sessions_expiration_order",
        "ck_steam_access_sessions_revocation_order",
    }


def test_access_session_round_trips_only_a_digest_for_its_profile() -> None:
    engine = _engine()

    with Session(engine) as session:
        profile = _profile()
        profile.access_sessions.append(_access_session())
        session.add(profile)
        session.commit()
        session.expire_all()

        stored = session.scalar(select(SteamAccessSession))

        assert stored is not None
        assert stored.token_digest == DIGEST
        assert stored.profile.steam_id == "76561198000000000"
        assert not hasattr(stored, "token")

    engine.dispose()


@pytest.mark.parametrize(
    "overrides",
    [
        {"token_digest": b"too-short"},
        {"expires_at": NOW},
        {"revoked_at": NOW - timedelta(seconds=1)},
    ],
)
def test_access_session_rejects_invalid_digest_or_lifetime(overrides) -> None:
    engine = _engine()

    with Session(engine) as session:
        profile = _profile()
        profile.access_sessions.append(_access_session(**overrides))
        session.add(profile)

        with pytest.raises(IntegrityError):
            session.commit()

    engine.dispose()


def test_access_session_rejects_a_duplicate_token_digest() -> None:
    engine = _engine()

    with Session(engine) as session:
        first_profile = _profile()
        first_profile.access_sessions.append(_access_session())
        second_profile = Profile(
            steam_id="76561198000000001",
            display_name="Second Player",
        )
        second_profile.access_sessions.append(_access_session())
        session.add_all([first_profile, second_profile])

        with pytest.raises(IntegrityError):
            session.commit()

    engine.dispose()


def test_deleting_a_profile_cascades_to_its_access_sessions() -> None:
    engine = _engine()

    with Session(engine) as session:
        profile = _profile()
        profile.access_sessions.append(_access_session())
        session.add(profile)
        session.commit()

        profile_id = profile.id
        session.delete(profile)
        session.commit()

        assert session.get(Profile, profile_id) is None
        assert session.scalar(select(SteamAccessSession)) is None

    assert "steam_access_sessions" in inspect(engine).get_table_names()
    engine.dispose()
