from collections.abc import Callable, Sequence
from datetime import UTC, datetime
import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.igdb_client import IGDBAPIError, IGDBClient
from app.igdb_matching import (
    IGDBMatchResult,
    IGDBMatchStatus,
    match_steam_app_ids,
)
from app.igdb_metadata import fetch_game_metadata
from app.igdb_persistence import (
    persist_metadata_batch,
    record_metadata_failure,
)
from app.models import Game


ENRICHMENT_BATCH_SIZE = 100
ENRICHMENT_BATCH_PAUSE_SECONDS = 1.0


def get_pending_owned_steam_app_ids(session: Session) -> list[int]:
    """Return uniquely owned pending games in stable Steam App ID order."""
    return list(
        session.scalars(
            select(Game.steam_app_id)
            .where(
                Game.profile_games.any(),
                Game.igdb_status == "pending",
            )
            .order_by(Game.steam_app_id)
        )
    )


def _utc_now() -> datetime:
    """Return the current timezone-aware UTC time."""
    return datetime.now(UTC)


def _unique_steam_app_ids(
    steam_app_ids: Sequence[int],
) -> list[int]:
    """Validate and deduplicate Steam App IDs in request order."""
    unique_ids = list(dict.fromkeys(steam_app_ids))

    for steam_app_id in unique_ids:
        if (
            not isinstance(steam_app_id, int)
            or isinstance(steam_app_id, bool)
            or steam_app_id <= 0
        ):
            raise ValueError("Steam App IDs must be positive integers.")

    return unique_ids


def enrich_game_metadata(
    session: Session,
    client: IGDBClient,
    steam_app_ids: Sequence[int],
    clock: Callable[[], datetime] = _utc_now,
    sleeper: Callable[[float], None] = time.sleep,
) -> list[IGDBMatchResult]:
    """Match, retrieve, and persist factual metadata in bounded batches.

    External requests finish before each database transaction begins. Successful
    batches commit independently, while temporary IGDB failures preserve cached
    facts and record diagnostic attempt information.

    Args:
        session: The database session used for persistence.
        client: The configured backend-only IGDB client.
        steam_app_ids: Shared Steam games to enrich.
        clock: Injectable timezone-aware clock used by tests.
        sleeper: Injectable delay function used between request batches.

    Returns:
        Match outcomes in deduplicated Steam App ID order.

    Raises:
        ValueError: If identifiers, timestamps, or normalized results are
            inconsistent.
        IGDBAPIError: If matching or metadata retrieval fails.
    """
    requested_ids = _unique_steam_app_ids(steam_app_ids)
    all_results: list[IGDBMatchResult] = []

    for start in range(0, len(requested_ids), ENRICHMENT_BATCH_SIZE):
        batch = requested_ids[start: start + ENRICHMENT_BATCH_SIZE]
        attempted_at = clock()

        if attempted_at.utcoffset() is None:
            raise ValueError("The enrichment clock must be timezone-aware.")

        try:
            match_results = match_steam_app_ids(client, batch)

            if {
                result.steam_app_id
                for result in match_results
            } != set(batch):
                raise ValueError(
                    "Matching must exactly cover the enrichment batch."
                )

            matched_igdb_ids = list(
                dict.fromkeys(
                    result.igdb_game_id
                    for result in match_results
                    if result.status is IGDBMatchStatus.MATCHED
                    and result.igdb_game_id is not None
                )
            )
            metadata_records = fetch_game_metadata(
                client,
                matched_igdb_ids,
            )

            persist_metadata_batch(
                session,
                match_results,
                metadata_records,
                attempted_at,
            )
        except IGDBAPIError as error:
            record_metadata_failure(
                session,
                batch,
                attempted_at,
                str(error),
            )
            raise

        all_results.extend(match_results)

        has_another_batch = (
            start + ENRICHMENT_BATCH_SIZE < len(requested_ids)
        )

        if has_another_batch:
            sleeper(ENRICHMENT_BATCH_PAUSE_SECONDS)

    return all_results
