"""Enrich newly imported games in the background after a library loads."""

from collections import Counter
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
import logging
import threading
import time

from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.integrations.igdb.client import IGDBAPIError, IGDBClient
from app.integrations.igdb.enrichment import (
    MAX_ENRICHMENT_GAMES_PER_RUN,
    enrich_game_metadata,
    get_pending_owned_steam_app_ids,
)
from app.integrations.igdb.locking import igdb_enrichment_lock
from app.integrations.igdb.matching import IGDBMatchResult, IGDBMatchStatus


AUTOMATIC_ENRICHMENT_MAX_PASSES = 2

SessionFactory = Callable[[], Session]
ClientProvider = Callable[[], IGDBClient]
EnrichmentService = Callable[
    [Session, IGDBClient, Sequence[int]],
    list[IGDBMatchResult],
]
EnrichmentLock = Callable[[], AbstractContextManager[bool]]

# Logged under uvicorn's error logger, like the Gemini diagnostics, so the lines
# reach the hosted service's standard output and appear in the Render log.
AUTOMATIC_ENRICHMENT_LOGGER = "uvicorn.error.ludex.igdb"
_LOGGER = logging.getLogger(AUTOMATIC_ENRICHMENT_LOGGER)
_LOGGER.setLevel(logging.INFO)


class SharedIGDBClient:
    """Create one IGDB client per process so its access token is reused."""

    def __init__(self, factory: Callable[[], IGDBClient]) -> None:
        self._factory = factory
        self._client: IGDBClient | None = None
        self._guard = threading.Lock()

    def get(self) -> IGDBClient:
        """Return the process client, creating it on first use."""
        with self._guard:
            if self._client is None:
                self._client = self._factory()
            return self._client

    def close(self) -> None:
        """Release the HTTP connection pool, if a client was created."""
        with self._guard:
            if self._client is not None:
                self._client.close()
                self._client = None


def _create_igdb_client() -> IGDBClient:
    return IGDBClient(
        settings.igdb_client_id,
        settings.igdb_client_secret.get_secret_value(),
    )


shared_igdb_client = SharedIGDBClient(_create_igdb_client)


def run_automatic_enrichment(
    *,
    enabled: bool | None = None,
    session_factory: SessionFactory = SessionLocal,
    client_provider: ClientProvider = shared_igdb_client.get,
    enrichment_service: EnrichmentService = enrich_game_metadata,
    enrichment_lock: EnrichmentLock = igdb_enrichment_lock,
) -> int:
    """Enrich pending owned games after an import, never raising.

    The run skips immediately when the feature is disabled or another manual
    or automatic run holds the enrichment lock. Otherwise it processes every
    pending owned game, not only the caller's, and checks once more for games
    that arrived during the run. One trigger enriches at most
    ``MAX_ENRICHMENT_GAMES_PER_RUN`` games.

    Returns:
        The number of games processed, which is zero when the run skips or
        fails before its first batch completes.
    """
    if not (
        settings.igdb_auto_enrichment_enabled if enabled is None else enabled
    ):
        return 0

    started_at = time.monotonic()
    outcomes: Counter[IGDBMatchStatus] = Counter()

    def duration_ms() -> int:
        return round((time.monotonic() - started_at) * 1000)

    try:
        with enrichment_lock() as lock_acquired:
            if not lock_acquired:
                _LOGGER.info(
                    "event=igdb_auto_enrichment_skipped "
                    "skip_reason=enrichment_already_running"
                )
                return 0

            for _ in range(AUTOMATIC_ENRICHMENT_MAX_PASSES):
                remaining = MAX_ENRICHMENT_GAMES_PER_RUN - sum(outcomes.values())
                if remaining <= 0:
                    break
                with session_factory() as database_session:
                    pending_ids = get_pending_owned_steam_app_ids(
                        database_session
                    )[:remaining]
                if not pending_ids:
                    break
                with session_factory() as database_session:
                    results = enrichment_service(
                        database_session,
                        client_provider(),
                        pending_ids,
                    )
                outcomes.update(result.status for result in results)
    except IGDBAPIError:
        _LOGGER.warning(
            "event=igdb_auto_enrichment_failed failure_category=igdb_unavailable "
            "processed_game_count=%s duration_ms=%s",
            sum(outcomes.values()),
            duration_ms(),
        )
    except Exception as error:
        _LOGGER.error(
            "event=igdb_auto_enrichment_failed failure_category=unexpected_error "
            "error_type=%s processed_game_count=%s duration_ms=%s",
            type(error).__name__,
            sum(outcomes.values()),
            duration_ms(),
        )
    else:
        if outcomes:
            _LOGGER.info(
                "event=igdb_auto_enrichment_completed processed_game_count=%s "
                "ready=%s missing=%s ambiguous=%s duration_ms=%s",
                sum(outcomes.values()),
                outcomes[IGDBMatchStatus.MATCHED],
                outcomes[IGDBMatchStatus.MISSING],
                outcomes[IGDBMatchStatus.AMBIGUOUS],
                duration_ms(),
            )
    return sum(outcomes.values())
