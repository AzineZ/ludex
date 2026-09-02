from base64 import urlsafe_b64decode
from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.access_sessions import (
    ACCESS_SESSION_LIFETIME,
    issue_access_session,
    revoke_access_session,
    resolve_access_session,
)
from app.database import Base
from app.models import Profile, SteamAccessSession


NOW = datetime(2026, 9, 2, 15, tzinfo=UTC)


def _profile_id(session: Session, steam_id: str = "76561198000000000") -> int:
    profile = Profile(
        steam_id=steam_id,
        display_name="Test Player",
    )
    session.add(profile)
    session.flush()
    profile_id = profile.id
    session.commit()
    return profile_id


def _decode_token(token: str) -> bytes:
    padding = "=" * (-len(token) % 4)
    return urlsafe_b64decode(token + padding)


def test_issue_access_session_generates_32_random_bytes_and_stores_digest() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        profile_id = _profile_id(session)

        first = issue_access_session(
            session,
            profile_id,
            clock=lambda: NOW,
        )
        second = issue_access_session(
            session,
            profile_id,
            clock=lambda: NOW,
        )

        stored = session.scalars(
            select(SteamAccessSession).order_by(SteamAccessSession.id)
        ).all()

        assert first.token != second.token
        assert len(_decode_token(first.token)) == 32
        assert len(_decode_token(second.token)) == 32
        assert first.created_at == NOW
        assert first.expires_at == NOW + ACCESS_SESSION_LIFETIME
        assert ACCESS_SESSION_LIFETIME == timedelta(days=7)
        assert [row.token_digest for row in stored] == [
            sha256(first.token.encode("ascii")).digest(),
            sha256(second.token.encode("ascii")).digest(),
        ]
        assert all(not hasattr(row, "token") for row in stored)

    engine.dispose()


def test_resolve_access_session_accepts_only_active_tokens_without_sliding() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        profile_id = _profile_id(session)
        active = issue_access_session(
            session,
            profile_id,
            clock=lambda: NOW,
            token_generator=lambda: "active-token",
        )

        resolved = resolve_access_session(
            session,
            active.token,
            clock=lambda: NOW + timedelta(days=6),
        )

        assert resolved is not None
        assert resolved.profile_id == profile_id
        assert resolved.expires_at == active.expires_at
        assert resolve_access_session(
            session,
            active.token,
            clock=lambda: active.expires_at,
        ) is None
        assert resolve_access_session(
            session,
            "unknown-token",
            clock=lambda: NOW,
        ) is None

    engine.dispose()


def test_resolve_access_session_rejects_a_revoked_token() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        profile_id = _profile_id(session)
        issued = issue_access_session(
            session,
            profile_id,
            clock=lambda: NOW,
            token_generator=lambda: "revoked-token",
        )
        assert revoke_access_session(
            session,
            issued.token,
            clock=lambda: NOW + timedelta(hours=1),
        ) is True

        assert revoke_access_session(
            session,
            issued.token,
            clock=lambda: NOW + timedelta(hours=2),
        ) is False
        assert resolve_access_session(
            session,
            issued.token,
            clock=lambda: NOW + timedelta(hours=2),
        ) is None

    engine.dispose()


def test_independent_browser_sessions_for_one_profile_remain_active() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        profile_id = _profile_id(session)
        first = issue_access_session(
            session,
            profile_id,
            clock=lambda: NOW,
            token_generator=lambda: "first-browser",
        )
        second = issue_access_session(
            session,
            profile_id,
            clock=lambda: NOW,
            token_generator=lambda: "second-browser",
        )

        assert resolve_access_session(
            session,
            first.token,
            clock=lambda: NOW,
        ) is not None
        assert resolve_access_session(
            session,
            second.token,
            clock=lambda: NOW,
        ) is not None

    engine.dispose()


def test_replacement_revokes_only_the_presented_browser_token() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        profile_id = _profile_id(session)
        replaced = issue_access_session(
            session,
            profile_id,
            clock=lambda: NOW,
            token_generator=lambda: "replaced-browser",
        )
        independent = issue_access_session(
            session,
            profile_id,
            clock=lambda: NOW,
            token_generator=lambda: "independent-browser",
        )
        replacement = issue_access_session(
            session,
            profile_id,
            current_token=replaced.token,
            clock=lambda: NOW + timedelta(hours=1),
            token_generator=lambda: "replacement-browser",
        )

        assert resolve_access_session(
            session,
            replaced.token,
            clock=lambda: NOW + timedelta(hours=1),
        ) is None
        assert resolve_access_session(
            session,
            independent.token,
            clock=lambda: NOW + timedelta(hours=1),
        ) is not None
        assert resolve_access_session(
            session,
            replacement.token,
            clock=lambda: NOW + timedelta(hours=1),
        ) is not None

    engine.dispose()


def test_failed_replacement_rolls_back_presented_token_revocation() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        first_profile_id = _profile_id(session)
        second_profile_id = _profile_id(
            session,
            steam_id="76561198000000001",
        )
        current = issue_access_session(
            session,
            first_profile_id,
            clock=lambda: NOW,
            token_generator=lambda: "current-token",
        )
        issue_access_session(
            session,
            second_profile_id,
            clock=lambda: NOW,
            token_generator=lambda: "collision-token",
        )

        with pytest.raises(IntegrityError):
            issue_access_session(
                session,
                second_profile_id,
                current_token=current.token,
                clock=lambda: NOW + timedelta(hours=1),
                token_generator=lambda: "collision-token",
            )

        session.rollback()
        stored_current = session.scalar(
            select(SteamAccessSession).where(
                SteamAccessSession.token_digest
                == sha256(current.token.encode("ascii")).digest()
            )
        )

        assert stored_current is not None
        assert stored_current.revoked_at is None

    engine.dispose()


def test_issue_access_session_rejects_a_timezone_naive_clock() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        profile_id = _profile_id(session)

        with pytest.raises(
            ValueError,
            match="The access-session clock must be timezone-aware.",
        ):
            issue_access_session(
                session,
                profile_id,
                clock=lambda: datetime(2026, 9, 2, 15),
            )

        assert session.scalar(select(SteamAccessSession)) is None

    engine.dispose()
