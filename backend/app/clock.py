"""Share the UTC clock helpers used wherever timestamps are read or stored."""

from collections.abc import Callable
from datetime import UTC, datetime


Clock = Callable[[], datetime]


def utc_now() -> datetime:
    """Return the current timezone-aware UTC time."""
    return datetime.now(UTC)


def read_utc_time(clock: Clock, *, clock_name: str) -> datetime:
    """Read one injected clock, rejecting timezone-naive values."""
    timestamp = clock()
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError(f"The {clock_name} clock must be timezone-aware.")
    return timestamp.astimezone(UTC)


def stored_utc_time(timestamp: datetime) -> datetime:
    """Treat timezone-naive SQLite test values as stored UTC timestamps."""
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        return timestamp.replace(tzinfo=UTC)
    return timestamp.astimezone(UTC)
