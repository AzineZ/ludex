"""Rate, quota, and concurrency controls for Steam-backed HTTP actions."""

from collections import OrderedDict, deque
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, time, timedelta
import hashlib
import hmac
from ipaddress import ip_address
import threading

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import SteamUsageEvent


SESSION_ATTEMPT_TEN_MINUTE_LIMIT = 5
SESSION_ATTEMPT_DAILY_LIMIT = 20
IDENTIFIER_SESSION_DAILY_LIMIT = 3
GLOBAL_SESSION_DAILY_LIMIT = 50
GLOBAL_PROVIDER_CALL_DAILY_LIMIT = 300
REFRESH_COOLDOWN = timedelta(minutes=15)
REFRESH_DAILY_LIMIT = 4
USAGE_WINDOW = timedelta(hours=24)
MAX_CLIENTS_IN_MEMORY = 2048
MAX_GLOBAL_SYNCHRONIZATIONS = 2


class RateLimitExceeded(RuntimeError):
    """Carry a bounded retry delay without exposing the limiting subject."""

    def __init__(self, retry_after: int) -> None:
        super().__init__("The Steam action rate limit was reached.")
        self.retry_after = max(1, min(retry_after, 24 * 60 * 60))


def _require_aware(timestamp: datetime) -> datetime:
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("Rate-limit timestamps must be timezone-aware.")
    return timestamp.astimezone(UTC)


def _retry_seconds(deadline: datetime, now: datetime) -> int:
    return max(1, int((deadline - now).total_seconds()))


def _next_utc_day(now: datetime) -> datetime:
    return datetime.combine(
        now.date() + timedelta(days=1),
        time.min,
        tzinfo=UTC,
    )


def fingerprint_subject(key: bytes, namespace: str, value: str) -> bytes:
    """Return an opaque fixed-size bucket without retaining its raw input."""
    if not key or not namespace or not value:
        raise ValueError("Rate-limit fingerprint inputs must be non-empty.")
    message = f"{namespace}\0{value}".encode("utf-8")
    return hmac.new(key, message, hashlib.sha256).digest()


def resolve_client_address(
    *,
    deployment_environment: str,
    socket_host: str | None,
    forwarded_for: str | None,
) -> str:
    """Resolve a memory-only client key under the configured proxy boundary."""
    if deployment_environment == "local":
        if not socket_host:
            raise ValueError("The local client address is unavailable.")
        return socket_host

    if not forwarded_for:
        raise ValueError("The hosted client address is unavailable.")
    first_address = forwarded_for.split(",", 1)[0].strip()
    try:
        parsed_address = ip_address(first_address)
    except ValueError as error:
        raise ValueError("The hosted client address is invalid.") from error
    if not parsed_address.is_global:
        raise ValueError("The hosted client address is not public.")
    return parsed_address.compressed


class SteamAbuseController:
    """Own bounded process-local request and synchronization state."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._attempts: OrderedDict[str, deque[datetime]] = OrderedDict()
        self._active_steam_ids: set[str] = set()
        self._active_synchronizations = 0

    def record_session_attempt(self, client: str, *, now: datetime) -> None:
        current_time = _require_aware(now)
        ten_minutes_ago = current_time - timedelta(minutes=10)
        one_day_ago = current_time - USAGE_WINDOW

        with self._lock:
            attempts = self._attempts.get(client)
            if attempts is None:
                if len(self._attempts) >= MAX_CLIENTS_IN_MEMORY:
                    self._attempts.popitem(last=False)
                attempts = deque()
                self._attempts[client] = attempts
            else:
                self._attempts.move_to_end(client)

            while attempts and attempts[0] <= one_day_ago:
                attempts.popleft()
            recent = [stamp for stamp in attempts if stamp > ten_minutes_ago]
            if len(recent) >= SESSION_ATTEMPT_TEN_MINUTE_LIMIT:
                raise RateLimitExceeded(
                    _retry_seconds(recent[0] + timedelta(minutes=10), current_time)
                )
            if len(attempts) >= SESSION_ATTEMPT_DAILY_LIMIT:
                raise RateLimitExceeded(
                    _retry_seconds(attempts[0] + USAGE_WINDOW, current_time)
                )
            attempts.append(current_time)

    @contextmanager
    def steam_sync(self, steam_id: str) -> Iterator[None]:
        """Acquire one identity and one of two global slots without waiting."""
        with self._lock:
            if (
                steam_id in self._active_steam_ids
                or self._active_synchronizations
                >= MAX_GLOBAL_SYNCHRONIZATIONS
            ):
                raise RateLimitExceeded(5)
            self._active_steam_ids.add(steam_id)
            self._active_synchronizations += 1

        try:
            yield
        finally:
            with self._lock:
                self._active_steam_ids.discard(steam_id)
                self._active_synchronizations -= 1


def _advisory_lock(database_session: Session, *digests: bytes) -> None:
    bind = database_session.get_bind()
    if bind.dialect.name != "postgresql":
        return
    keys = sorted(
        {
            int.from_bytes(digest[:8], byteorder="big", signed=True)
            for digest in digests
        }
    )
    for key in keys:
        database_session.execute(select(func.pg_advisory_xact_lock(key)))


def _count_events(
    database_session: Session,
    *,
    category: str,
    created_after: datetime,
    subject_digest: bytes | None = None,
) -> int:
    statement = select(func.count()).select_from(SteamUsageEvent).where(
        SteamUsageEvent.category == category,
        SteamUsageEvent.created_at >= created_after,
    )
    if subject_digest is not None:
        statement = statement.where(
            SteamUsageEvent.subject_digest == subject_digest
        )
    return database_session.scalar(statement) or 0


@contextmanager
def _reservation_transaction(
    database_session: Session,
    now: datetime,
) -> Iterator[None]:
    database_session.rollback()
    try:
        with database_session.begin():
            database_session.execute(
                delete(SteamUsageEvent).where(SteamUsageEvent.expires_at <= now)
            )
            yield
    except Exception:
        database_session.rollback()
        raise


def reserve_session_creation(
    database_session: Session,
    subject_digest: bytes,
    *,
    now: datetime,
) -> None:
    """Reserve one provider-backed creation against two durable ceilings."""
    current_time = _require_aware(now)
    global_digest = b"\0" * 32
    day_start = datetime.combine(current_time.date(), time.min, tzinfo=UTC)
    next_day = _next_utc_day(current_time)

    with _reservation_transaction(database_session, current_time):
        _advisory_lock(database_session, global_digest, subject_digest)
        if _count_events(
            database_session,
            category="session_create",
            created_after=current_time - USAGE_WINDOW,
            subject_digest=subject_digest,
        ) >= IDENTIFIER_SESSION_DAILY_LIMIT:
            raise RateLimitExceeded(24 * 60 * 60)
        if _count_events(
            database_session,
            category="session_create",
            created_after=day_start,
        ) >= GLOBAL_SESSION_DAILY_LIMIT:
            raise RateLimitExceeded(_retry_seconds(next_day, current_time))
        database_session.add(
            SteamUsageEvent(
                category="session_create",
                subject_digest=subject_digest,
                created_at=current_time,
                expires_at=current_time + USAGE_WINDOW,
            )
        )


def reserve_provider_call(
    database_session: Session,
    hmac_key: bytes,
    *,
    now: datetime,
) -> None:
    """Reserve one actual Steam call under the UTC-day global ceiling."""
    current_time = _require_aware(now)
    global_digest = fingerprint_subject(hmac_key, "global", "steam")
    day_start = datetime.combine(current_time.date(), time.min, tzinfo=UTC)
    next_day = _next_utc_day(current_time)

    with _reservation_transaction(database_session, current_time):
        _advisory_lock(database_session, global_digest)
        if _count_events(
            database_session,
            category="provider_call",
            created_after=day_start,
        ) >= GLOBAL_PROVIDER_CALL_DAILY_LIMIT:
            raise RateLimitExceeded(_retry_seconds(next_day, current_time))
        database_session.add(
            SteamUsageEvent(
                category="provider_call",
                subject_digest=global_digest,
                created_at=current_time,
                expires_at=next_day,
            )
        )


def reserve_refresh(
    database_session: Session,
    subject_digest: bytes,
    *,
    now: datetime,
) -> None:
    """Reserve one authorized refresh under cooldown and rolling-day caps."""
    current_time = _require_aware(now)
    cooldown_start = current_time - REFRESH_COOLDOWN
    day_start = current_time - USAGE_WINDOW

    with _reservation_transaction(database_session, current_time):
        _advisory_lock(database_session, subject_digest)
        most_recent = database_session.scalar(
            select(func.max(SteamUsageEvent.created_at)).where(
                SteamUsageEvent.category == "refresh",
                SteamUsageEvent.subject_digest == subject_digest,
                SteamUsageEvent.created_at > cooldown_start,
            )
        )
        if most_recent is not None:
            if most_recent.tzinfo is None:
                most_recent = most_recent.replace(tzinfo=UTC)
            raise RateLimitExceeded(
                _retry_seconds(most_recent + REFRESH_COOLDOWN, current_time)
            )
        if _count_events(
            database_session,
            category="refresh",
            created_after=day_start,
            subject_digest=subject_digest,
        ) >= REFRESH_DAILY_LIMIT:
            raise RateLimitExceeded(24 * 60 * 60)
        database_session.add(
            SteamUsageEvent(
                category="refresh",
                subject_digest=subject_digest,
                created_at=current_time,
                expires_at=current_time + USAGE_WINDOW,
            )
        )
