from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from enum import StrEnum
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.models import (
    GeminiPromptReservation,
    GeminiPromptUsageEvent,
    SteamAccessSession,
)


SESSION_PROMPT_DAILY_LIMIT = 5
MAX_PROMPT_ATTEMPTS = 2
PACIFIC = ZoneInfo("America/Los_Angeles")
GLOBAL_PROMPT_LOCK_KEY = 0x4C5544455850524D

ReservationIDFactory = Callable[[], str]


def _new_reservation_id() -> str:
    return str(uuid4())


class PromptQuotaReason(StrEnum):
    INVALID_SESSION = "invalid_session"
    PROMPT_IN_FLIGHT = "prompt_in_flight"
    SESSION_DAILY_LIMIT = "session_daily_limit"
    RESERVATION_UNAVAILABLE = "reservation_unavailable"
    ATTEMPT_LIMIT = "attempt_limit"
    PROJECT_MINUTE_LIMIT = "project_minute_limit"
    PROJECT_DAILY_LIMIT = "project_daily_limit"


class PromptQuotaExceeded(RuntimeError):
    def __init__(
        self,
        reason: PromptQuotaReason,
        *,
        retry_after_seconds: int,
    ) -> None:
        super().__init__("AI recommendations are temporarily unavailable.")
        self.reason = reason
        self.retry_after_seconds = max(1, retry_after_seconds)


@dataclass(frozen=True)
class PromptQuotaPolicy:
    provider_requests_per_minute: int
    provider_requests_per_day: int
    global_daily_ceiling: int | None = None
    reserve_percent: int = 80

    def __post_init__(self) -> None:
        values = (
            self.provider_requests_per_minute,
            self.provider_requests_per_day,
            self.reserve_percent,
        )
        if any(
            not isinstance(value, int)
            or isinstance(value, bool)
            or value <= 0
            for value in values
        ):
            raise ValueError("Prompt quota limits must be positive integers.")
        if self.reserve_percent > 100:
            raise ValueError("Prompt quota reserve percent cannot exceed 100.")
        if (
            self.global_daily_ceiling is not None
            and (
                not isinstance(self.global_daily_ceiling, int)
                or isinstance(self.global_daily_ceiling, bool)
                or self.global_daily_ceiling <= 0
            )
        ):
            raise ValueError("The global daily ceiling must be positive.")
        if self.minute_budget < 1 or self.daily_budget < 1:
            raise ValueError("The reserved provider budget is too small.")

    @property
    def minute_budget(self) -> int:
        return (
            self.provider_requests_per_minute * self.reserve_percent
        ) // 100

    @property
    def daily_budget(self) -> int:
        reserved = (
            self.provider_requests_per_day * self.reserve_percent
        ) // 100
        if self.global_daily_ceiling is None:
            return reserved
        return min(reserved, self.global_daily_ceiling)


@dataclass(frozen=True)
class PromptReservation:
    reservation_id: str
    access_session_id: int
    created_at: datetime
    expires_at: datetime


@dataclass(frozen=True)
class PromptAttemptReservation:
    reservation_id: str
    attempt_number: int
    reserved_at: datetime


def _utc_time(timestamp: datetime) -> datetime:
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("Prompt quota timestamps must be timezone-aware.")
    return timestamp.astimezone(UTC)


def _stored_time(timestamp: datetime) -> datetime:
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        return timestamp.replace(tzinfo=UTC)
    return timestamp.astimezone(UTC)


def _pacific_day_bounds(now: datetime) -> tuple[datetime, datetime]:
    local = now.astimezone(PACIFIC)
    start_local = datetime.combine(local.date(), time.min, tzinfo=PACIFIC)
    next_local = datetime.combine(
        local.date() + timedelta(days=1),
        time.min,
        tzinfo=PACIFIC,
    )
    return start_local.astimezone(UTC), next_local.astimezone(UTC)


def _retry_seconds(deadline: datetime, now: datetime) -> int:
    return max(1, int((deadline - now).total_seconds()))


def _advisory_lock(session: Session, *keys: int) -> None:
    if session.get_bind().dialect.name != "postgresql":
        return
    for key in sorted(set(keys)):
        session.execute(select(func.pg_advisory_xact_lock(key)))


@contextmanager
def _transaction(session: Session) -> Iterator[None]:
    session.rollback()
    try:
        with session.begin():
            yield
    except Exception:
        session.rollback()
        raise


def _expire_stale_reservations(session: Session, now: datetime) -> None:
    session.execute(
        update(GeminiPromptReservation)
        .where(
            GeminiPromptReservation.completed_at.is_(None),
            GeminiPromptReservation.expires_at <= now,
        )
        .values(completed_at=GeminiPromptReservation.expires_at)
    )


def reserve_prompt_message(
    session: Session,
    *,
    access_session_id: int,
    now: datetime,
    lease_duration: timedelta,
    reservation_id_factory: ReservationIDFactory = _new_reservation_id,
) -> PromptReservation:
    """Reserve one daily prompt slot and one in-flight session lease."""
    current_time = _utc_time(now)
    if (
        not isinstance(lease_duration, timedelta)
        or not timedelta(seconds=1)
        <= lease_duration
        <= timedelta(minutes=5)
    ):
        raise ValueError("Prompt lease duration must be 1 second to 5 minutes.")
    day_start, next_day = _pacific_day_bounds(current_time)

    with _transaction(session):
        _expire_stale_reservations(session, current_time)
        session.execute(
            delete(GeminiPromptReservation).where(
                GeminiPromptReservation.completed_at.is_not(None),
                GeminiPromptReservation.created_at < day_start,
            )
        )
        _advisory_lock(session, access_session_id)
        access = session.scalar(
            select(SteamAccessSession).where(
                SteamAccessSession.id == access_session_id,
                SteamAccessSession.revoked_at.is_(None),
                SteamAccessSession.expires_at > current_time,
            )
        )
        if access is None:
            raise PromptQuotaExceeded(
                PromptQuotaReason.INVALID_SESSION,
                retry_after_seconds=1,
            )
        active = session.scalar(
            select(GeminiPromptReservation).where(
                GeminiPromptReservation.access_session_id
                == access_session_id,
                GeminiPromptReservation.completed_at.is_(None),
            )
        )
        if active is not None:
            raise PromptQuotaExceeded(
                PromptQuotaReason.PROMPT_IN_FLIGHT,
                retry_after_seconds=_retry_seconds(
                    _stored_time(active.expires_at),
                    current_time,
                ),
            )
        daily_count = session.scalar(
            select(func.count())
            .select_from(GeminiPromptReservation)
            .where(
                GeminiPromptReservation.access_session_id
                == access_session_id,
                GeminiPromptReservation.created_at >= day_start,
            )
        ) or 0
        if daily_count >= SESSION_PROMPT_DAILY_LIMIT:
            raise PromptQuotaExceeded(
                PromptQuotaReason.SESSION_DAILY_LIMIT,
                retry_after_seconds=_retry_seconds(next_day, current_time),
            )

        reservation_id = reservation_id_factory()
        if (
            not isinstance(reservation_id, str)
            or not reservation_id
            or reservation_id != reservation_id.strip()
            or len(reservation_id) > 36
        ):
            raise ValueError("Prompt reservation IDs must be bounded strings.")
        access_expiry = _stored_time(access.expires_at)
        expires_at = min(current_time + lease_duration, access_expiry)
        session.add(
            GeminiPromptReservation(
                id=reservation_id,
                access_session_id=access_session_id,
                created_at=current_time,
                expires_at=expires_at,
                completed_at=None,
            )
        )

    return PromptReservation(
        reservation_id=reservation_id,
        access_session_id=access_session_id,
        created_at=current_time,
        expires_at=expires_at,
    )


def reserve_prompt_attempt(
    session: Session,
    *,
    reservation_id: str,
    policy: PromptQuotaPolicy,
    now: datetime,
) -> PromptAttemptReservation:
    """Durably reserve one provider attempt before any provider I/O."""
    current_time = _utc_time(now)
    day_start, next_day = _pacific_day_bounds(current_time)
    minute_start = current_time - timedelta(minutes=1)

    with _transaction(session):
        _expire_stale_reservations(session, current_time)
        reservation = session.scalar(
            select(GeminiPromptReservation).where(
                GeminiPromptReservation.id == reservation_id
            )
        )
        if (
            reservation is None
            or reservation.completed_at is not None
            or _stored_time(reservation.expires_at) <= current_time
        ):
            raise PromptQuotaExceeded(
                PromptQuotaReason.RESERVATION_UNAVAILABLE,
                retry_after_seconds=1,
            )
        _advisory_lock(
            session,
            GLOBAL_PROMPT_LOCK_KEY,
            reservation.access_session_id,
        )
        reservation = session.scalar(
            select(GeminiPromptReservation).where(
                GeminiPromptReservation.id == reservation_id
            )
        )
        if (
            reservation is None
            or reservation.completed_at is not None
            or _stored_time(reservation.expires_at) <= current_time
        ):
            raise PromptQuotaExceeded(
                PromptQuotaReason.RESERVATION_UNAVAILABLE,
                retry_after_seconds=1,
            )
        access_valid = session.scalar(
            select(SteamAccessSession.id).where(
                SteamAccessSession.id == reservation.access_session_id,
                SteamAccessSession.revoked_at.is_(None),
                SteamAccessSession.expires_at > current_time,
            )
        )
        if access_valid is None:
            raise PromptQuotaExceeded(
                PromptQuotaReason.INVALID_SESSION,
                retry_after_seconds=1,
            )

        attempt_count = session.scalar(
            select(func.count())
            .select_from(GeminiPromptUsageEvent)
            .where(
                GeminiPromptUsageEvent.reservation_id == reservation_id
            )
        ) or 0
        if attempt_count >= MAX_PROMPT_ATTEMPTS:
            raise PromptQuotaExceeded(
                PromptQuotaReason.ATTEMPT_LIMIT,
                retry_after_seconds=_retry_seconds(
                    _stored_time(reservation.expires_at),
                    current_time,
                ),
            )

        minute_events = tuple(
            session.scalars(
                select(GeminiPromptUsageEvent)
                .where(GeminiPromptUsageEvent.created_at > minute_start)
                .order_by(GeminiPromptUsageEvent.created_at)
            ).all()
        )
        if len(minute_events) >= policy.minute_budget:
            retry_at = _stored_time(minute_events[0].created_at) + timedelta(
                minutes=1
            )
            raise PromptQuotaExceeded(
                PromptQuotaReason.PROJECT_MINUTE_LIMIT,
                retry_after_seconds=_retry_seconds(retry_at, current_time),
            )
        daily_count = session.scalar(
            select(func.count())
            .select_from(GeminiPromptUsageEvent)
            .where(GeminiPromptUsageEvent.created_at >= day_start)
        ) or 0
        if daily_count >= policy.daily_budget:
            raise PromptQuotaExceeded(
                PromptQuotaReason.PROJECT_DAILY_LIMIT,
                retry_after_seconds=_retry_seconds(next_day, current_time),
            )

        session.add(
            GeminiPromptUsageEvent(
                reservation_id=reservation_id,
                created_at=current_time,
                expires_at=next_day,
            )
        )

    return PromptAttemptReservation(
        reservation_id=reservation_id,
        attempt_number=attempt_count + 1,
        reserved_at=current_time,
    )


def complete_prompt_reservation(
    session: Session,
    *,
    reservation_id: str,
    now: datetime,
) -> bool:
    """Release one in-flight lease while retaining its bounded counters."""
    current_time = _utc_time(now)
    with _transaction(session):
        reservation = session.scalar(
            select(GeminiPromptReservation).where(
                GeminiPromptReservation.id == reservation_id
            )
        )
        if reservation is None or reservation.completed_at is not None:
            return False
        _advisory_lock(session, reservation.access_session_id)
        reservation = session.scalar(
            select(GeminiPromptReservation).where(
                GeminiPromptReservation.id == reservation_id,
                GeminiPromptReservation.completed_at.is_(None),
            )
        )
        if reservation is None:
            return False
        reservation.completed_at = current_time
    return True
