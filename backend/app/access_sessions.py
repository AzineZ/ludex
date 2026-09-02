from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Profile, SteamAccessSession


ACCESS_SESSION_LIFETIME = timedelta(days=7)

Clock = Callable[[], datetime]
TokenGenerator = Callable[[], str]


@dataclass(frozen=True)
class IssuedAccessSession:
    """Return the one raw token that may be sent to its browser."""

    token: str
    profile_id: int
    created_at: datetime
    expires_at: datetime


@dataclass(frozen=True)
class ActiveAccessSession:
    """Identify an active session without exposing persistence details."""

    profile_id: int
    created_at: datetime
    expires_at: datetime


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _generate_token() -> str:
    return secrets.token_urlsafe(32)


def _read_time(clock: Clock) -> datetime:
    timestamp = clock()
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("The access-session clock must be timezone-aware.")
    return timestamp.astimezone(UTC)


def _token_digest(token: str) -> bytes:
    return sha256(token.encode("utf-8")).digest()


def _stored_time(timestamp: datetime) -> datetime:
    """Treat timezone-naive SQLite test values as stored UTC timestamps."""
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        return timestamp.replace(tzinfo=UTC)
    return timestamp.astimezone(UTC)


def issue_access_session(
    database_session: Session,
    profile_id: int,
    *,
    current_token: str | None = None,
    clock: Clock = _utc_now,
    token_generator: TokenGenerator = _generate_token,
) -> IssuedAccessSession:
    """Issue one fixed-lifetime token and optionally replace one active token."""
    created_at = _read_time(clock)
    expires_at = created_at + ACCESS_SESSION_LIFETIME
    token = token_generator()
    token_digest = _token_digest(token)

    with database_session.begin():
        profile_exists = database_session.scalar(
            select(Profile.id).where(Profile.id == profile_id)
        )
        if profile_exists is None:
            raise LookupError("Profile not found.")

        if current_token is not None:
            current_session = database_session.scalar(
                select(SteamAccessSession).where(
                    SteamAccessSession.token_digest
                    == _token_digest(current_token),
                    SteamAccessSession.revoked_at.is_(None),
                    SteamAccessSession.expires_at > created_at,
                )
            )
            if current_session is not None:
                current_session.revoked_at = created_at

        database_session.add(
            SteamAccessSession(
                token_digest=token_digest,
                profile_id=profile_id,
                created_at=created_at,
                expires_at=expires_at,
            )
        )

    return IssuedAccessSession(
        token=token,
        profile_id=profile_id,
        created_at=created_at,
        expires_at=expires_at,
    )


def resolve_access_session(
    database_session: Session,
    token: str,
    *,
    clock: Clock = _utc_now,
) -> ActiveAccessSession | None:
    """Resolve an active digest without changing its fixed expiration."""
    current_time = _read_time(clock)
    stored_session = database_session.scalar(
        select(SteamAccessSession).where(
            SteamAccessSession.token_digest == _token_digest(token),
            SteamAccessSession.revoked_at.is_(None),
            SteamAccessSession.expires_at > current_time,
        )
    )
    if stored_session is None:
        return None

    return ActiveAccessSession(
        profile_id=stored_session.profile_id,
        created_at=_stored_time(stored_session.created_at),
        expires_at=_stored_time(stored_session.expires_at),
    )


def revoke_access_session(
    database_session: Session,
    token: str,
    *,
    clock: Clock = _utc_now,
) -> bool:
    """Revoke one active browser token without affecting other sessions."""
    revoked_at = _read_time(clock)

    with database_session.begin():
        stored_session = database_session.scalar(
            select(SteamAccessSession).where(
                SteamAccessSession.token_digest == _token_digest(token),
                SteamAccessSession.revoked_at.is_(None),
                SteamAccessSession.expires_at > revoked_at,
            )
        )
        if stored_session is None:
            return False
        stored_session.revoked_at = revoked_at

    return True
