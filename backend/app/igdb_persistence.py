from collections.abc import Sequence
from datetime import datetime

from app.igdb_metadata import IGDBGameMetadata
from app.igdb_matching import (
    IGDBMatchResult,
    IGDBMatchStatus,
)
from app.models import (
    Game,
    GameIGDBMetadataTerm,
    IGDBMetadataTerm,
)
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload


def apply_ready_metadata(
    game: Game,
    metadata: IGDBGameMetadata,
    enriched_at: datetime,
) -> None:
    """Apply validated factual IGDB metadata to one shared game."""
    if enriched_at.utcoffset() is None:
        raise ValueError("The enrichment time must be timezone-aware.")

    game.igdb_game_id = metadata.igdb_game_id
    game.igdb_status = "ready"
    game.igdb_last_attempted_at = enriched_at
    game.igdb_last_error = None
    game.igdb_enriched_at = enriched_at
    game.igdb_metadata_updated_at = metadata.updated_at
    game.summary = metadata.summary
    game.first_release_at = metadata.first_release_at
    game.cover_image_id = metadata.cover_image_id

    time_to_beat = metadata.time_to_beat

    if time_to_beat is None:
        game.time_to_beat_hastily_seconds = None
        game.time_to_beat_normally_seconds = None
        game.time_to_beat_completely_seconds = None
        game.time_to_beat_submission_count = None
        game.time_to_beat_updated_at = None
        return

    game.time_to_beat_hastily_seconds = time_to_beat.hastily_seconds
    game.time_to_beat_normally_seconds = time_to_beat.normally_seconds
    game.time_to_beat_completely_seconds = (
        time_to_beat.completely_seconds
    )
    game.time_to_beat_submission_count = (
        time_to_beat.submission_count
    )
    game.time_to_beat_updated_at = time_to_beat.updated_at


def replace_metadata_terms(
    session: Session,
    game: Game,
    metadata: IGDBGameMetadata,
) -> None:
    """Replace one game's term links using reusable lookup rows."""
    groups = (
        ("genre", metadata.genres),
        ("theme", metadata.themes),
        ("keyword", metadata.keywords),
        ("game_mode", metadata.game_modes),
    )
    desired = {
        (kind, entity.igdb_id): entity.name
        for kind, entities in groups
        for entity in entities
    }

    terms_by_key: dict[tuple[str, int], IGDBMetadataTerm] = {}

    if desired:
        kinds = {kind for kind, _ in desired}
        igdb_ids = {igdb_id for _, igdb_id in desired}

        candidates = session.scalars(
            select(IGDBMetadataTerm).where(
                IGDBMetadataTerm.kind.in_(kinds),
                IGDBMetadataTerm.igdb_id.in_(igdb_ids),
            )
        ).all()

        terms_by_key = {
            (term.kind, term.igdb_id): term
            for term in candidates
            if (term.kind, term.igdb_id) in desired
        }

    for key, name in desired.items():
        term = terms_by_key.get(key)

        if term is None:
            term = IGDBMetadataTerm(
                kind=key[0],
                igdb_id=key[1],
                name=name,
            )
            session.add(term)
            terms_by_key[key] = term
        else:
            term.name = name

    for link in list(game.metadata_term_links):
        key = (link.term.kind, link.term.igdb_id)

        if key not in desired:
            game.metadata_term_links.remove(link)

    linked_keys = {
        (link.term.kind, link.term.igdb_id)
        for link in game.metadata_term_links
    }

    for key, term in terms_by_key.items():
        if key not in linked_keys:
            game.metadata_term_links.append(
                GameIGDBMetadataTerm(term=term)
            )


def apply_unmatched_result(
    game: Game,
    status: IGDBMatchStatus,
    attempted_at: datetime,
) -> None:
    """Apply a definitive missing or ambiguous IGDB outcome."""
    if status not in {
        IGDBMatchStatus.MISSING,
        IGDBMatchStatus.AMBIGUOUS,
    }:
        raise ValueError("The result must be missing or ambiguous.")

    if attempted_at.utcoffset() is None:
        raise ValueError("The attempt time must be timezone-aware.")

    game.igdb_game_id = None
    game.igdb_status = status.value
    game.igdb_last_attempted_at = attempted_at
    game.igdb_last_error = None
    game.igdb_enriched_at = None
    game.igdb_metadata_updated_at = None
    game.summary = None
    game.first_release_at = None
    game.cover_image_id = None
    game.time_to_beat_hastily_seconds = None
    game.time_to_beat_normally_seconds = None
    game.time_to_beat_completely_seconds = None
    game.time_to_beat_submission_count = None
    game.time_to_beat_updated_at = None
    game.metadata_term_links.clear()


def persist_metadata_batch(
    session: Session,
    match_results: Sequence[IGDBMatchResult],
    metadata_records: Sequence[IGDBGameMetadata],
    attempted_at: datetime,
) -> None:
    """Persist one complete batch of factual IGDB outcomes atomically.

    Args:
        session: The database session used for the transaction.
        match_results: One definitive match outcome per attempted Steam game.
        metadata_records: Validated metadata for every matched IGDB game.
        attempted_at: The timezone-aware time at which enrichment was attempted.

    Raises:
        ValueError: If timestamps, results, metadata, or local games are
            incomplete, duplicated, or inconsistent.
    """
    if attempted_at.utcoffset() is None:
        raise ValueError("The attempt time must be timezone-aware.")

    results_by_steam_id: dict[int, IGDBMatchResult] = {}
    expected_igdb_ids: set[int] = set()

    for result in match_results:
        steam_app_id = result.steam_app_id

        if (
            not isinstance(steam_app_id, int)
            or isinstance(steam_app_id, bool)
            or steam_app_id <= 0
        ):
            raise ValueError("Steam App IDs must be positive integers.")

        if steam_app_id in results_by_steam_id:
            raise ValueError("Match results contain a duplicate Steam App ID.")

        results_by_steam_id[steam_app_id] = result

        if result.status is IGDBMatchStatus.MATCHED:
            if result.igdb_game_id is None:
                raise ValueError(
                    "Matched results must contain an IGDB game ID."
                )

            expected_igdb_ids.add(result.igdb_game_id)
        elif result.status in {
            IGDBMatchStatus.MISSING,
            IGDBMatchStatus.AMBIGUOUS,
        }:
            if result.igdb_game_id is not None:
                raise ValueError(
                    "Unmatched results cannot contain an IGDB game ID."
                )
        else:
            raise ValueError("The match result has an unsupported status.")

    metadata_by_igdb_id: dict[int, IGDBGameMetadata] = {}

    for metadata in metadata_records:
        if metadata.igdb_game_id in metadata_by_igdb_id:
            raise ValueError("Metadata contains a duplicate IGDB game ID.")

        metadata_by_igdb_id[metadata.igdb_game_id] = metadata

    if set(metadata_by_igdb_id) != expected_igdb_ids:
        raise ValueError(
            "Metadata must exactly cover every matched IGDB game."
        )

    if not results_by_steam_id:
        return

    with session.begin():
        games = session.scalars(
            select(Game)
            .options(
                selectinload(Game.metadata_term_links).selectinload(
                    GameIGDBMetadataTerm.term
                )
            )
            .where(
                Game.steam_app_id.in_(results_by_steam_id)
            )
        ).all()

        games_by_steam_id = {
            game.steam_app_id: game
            for game in games
        }

        if set(games_by_steam_id) != set(results_by_steam_id):
            raise ValueError(
                "Every match result must reference a saved Steam game."
            )

        for steam_app_id, result in results_by_steam_id.items():
            game = games_by_steam_id[steam_app_id]

            if result.status is IGDBMatchStatus.MATCHED:
                assert result.igdb_game_id is not None
                metadata = metadata_by_igdb_id[result.igdb_game_id]

                apply_ready_metadata(game, metadata, attempted_at)
                replace_metadata_terms(session, game, metadata)

                # Make newly created shared terms visible to later games in
                # this batch even when the production session disables
                # automatic flushing.
                session.flush()
            else:
                apply_unmatched_result(
                    game,
                    result.status,
                    attempted_at,
                )


def record_metadata_failure(
    session: Session,
    steam_app_ids: Sequence[int],
    attempted_at: datetime,
    error_message: str,
) -> None:
    """Record a temporary IGDB failure without changing cached facts.

    Args:
        session: The database session used for the transaction.
        steam_app_ids: Shared Steam games affected by the failed attempt.
        attempted_at: The timezone-aware time of the failed attempt.
        error_message: A safe diagnostic message describing the failure.

    Raises:
        ValueError: If the timestamp, IDs, message, or local games are invalid.
    """
    if attempted_at.utcoffset() is None:
        raise ValueError("The attempt time must be timezone-aware.")

    unique_steam_app_ids = list(dict.fromkeys(steam_app_ids))

    for steam_app_id in unique_steam_app_ids:
        if (
            not isinstance(steam_app_id, int)
            or isinstance(steam_app_id, bool)
            or steam_app_id <= 0
        ):
            raise ValueError("Steam App IDs must be positive integers.")

    if not isinstance(error_message, str) or not error_message.strip():
        raise ValueError("The error message must be a non-empty string.")

    if not unique_steam_app_ids:
        return

    # The database column is bounded so an unexpectedly large upstream
    # message cannot cause failure recording itself to fail.
    stored_error = error_message.strip()[:500]

    with session.begin():
        games = session.scalars(
            select(Game).where(
                Game.steam_app_id.in_(unique_steam_app_ids)
            )
        ).all()

        games_by_steam_id = {
            game.steam_app_id: game
            for game in games
        }

        if set(games_by_steam_id) != set(unique_steam_app_ids):
            raise ValueError(
                "Every failed attempt must reference a saved Steam game."
            )

        for game in games:
            game.igdb_last_attempted_at = attempted_at
            game.igdb_last_error = stored_error
