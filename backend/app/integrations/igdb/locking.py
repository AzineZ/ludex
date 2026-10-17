"""Serialize every IGDB enrichment run, manual or automatic."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import text

from app.database import engine


IGDB_ENRICHMENT_ADVISORY_LOCK_KEY = 0x4C55444558494744


@contextmanager
def igdb_enrichment_lock() -> Iterator[bool]:
    """Try to hold one transaction-scoped PostgreSQL lock without waiting.

    Yields:
        Whether this caller holds the lock for the duration of the block.
    """
    with engine.connect() as connection:
        with connection.begin():
            acquired = connection.scalar(
                text("SELECT pg_try_advisory_xact_lock(:lock_key)"),
                {"lock_key": IGDB_ENRICHMENT_ADVISORY_LOCK_KEY},
            )
            yield bool(acquired)
