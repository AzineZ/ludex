"""Fetch display-only IGDB ratings for games enriched before they existed.

Ready games are never re-enriched, so this one-time backfill adds ratings
without touching match status, facets, or any other cached metadata.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.clock import utc_now
from app.integrations.igdb.client import IGDBClient, IGDBResponseError
from app.integrations.igdb.metadata import (
    GAME_RATING_FIELDS,
    METADATA_QUERY_LIMIT,
    IGDBRatings,
    normalize_ratings,
)
from app.integrations.igdb.persistence import apply_ratings
from app.models import Game


RATINGS_BATCH_SIZE = 100
RATINGS_BATCH_PAUSE_SECONDS = 1.0


@dataclass(frozen=True)
class UncheckedRatingGame:
    """Identify one ready game whose ratings were never fetched."""

    steam_app_id: int
    igdb_game_id: int


def get_unchecked_rating_games(
    session: Session,
) -> list[UncheckedRatingGame]:
    """Return ready matched games without a rating check, by Steam App ID."""
    rows = session.execute(
        select(Game.steam_app_id, Game.igdb_game_id)
        .where(
            Game.igdb_status == "ready",
            Game.igdb_game_id.is_not(None),
            Game.igdb_ratings_checked_at.is_(None),
        )
        .order_by(Game.steam_app_id)
    ).all()
    return [
        UncheckedRatingGame(
            steam_app_id=row.steam_app_id,
            igdb_game_id=row.igdb_game_id,
        )
        for row in rows
    ]


def fetch_game_ratings(
    client: IGDBClient,
    igdb_game_ids: Sequence[int],
) -> dict[int, IGDBRatings]:
    """Fetch ratings for at most one batch of IGDB games.

    A game IGDB no longer returns is reported with empty ratings so it is
    checked once rather than retried forever.
    """
    requested_ids = list(dict.fromkeys(igdb_game_ids))
    if len(requested_ids) > RATINGS_BATCH_SIZE:
        raise ValueError("Fetch at most 100 IGDB games per ratings batch.")
    if not requested_ids:
        return {}

    id_values = ",".join(str(game_id) for game_id in requested_ids)
    raw_games = client.query(
        "games",
        (
            f"fields id,{GAME_RATING_FIELDS};"
            f" where id = ({id_values});"
            f" limit {METADATA_QUERY_LIMIT};"
        ),
    )

    ratings_by_id = {game_id: IGDBRatings() for game_id in requested_ids}
    seen_ids: set[int] = set()
    for raw_game in raw_games:
        if not isinstance(raw_game, dict):
            raise IGDBResponseError("IGDB returned an invalid ratings entry.")
        igdb_game_id = raw_game.get("id")
        if igdb_game_id not in ratings_by_id or igdb_game_id in seen_ids:
            raise IGDBResponseError("IGDB returned unexpected ratings.")
        seen_ids.add(igdb_game_id)
        ratings_by_id[igdb_game_id] = normalize_ratings(raw_game)

    return ratings_by_id


def backfill_game_ratings(
    session: Session,
    client: IGDBClient,
    games: Sequence[UncheckedRatingGame],
    clock: Callable[[], datetime] = utc_now,
    sleeper: Callable[[float], None] = time.sleep,
) -> int:
    """Store ratings batch by batch and return the number of games updated.

    Each batch is fetched before its transaction starts and committed on its
    own, so an IGDB failure keeps earlier batches and leaves the rest
    unchecked for the next run.
    """
    updated_count = 0
    for start in range(0, len(games), RATINGS_BATCH_SIZE):
        if start:
            sleeper(RATINGS_BATCH_PAUSE_SECONDS)
        batch = games[start: start + RATINGS_BATCH_SIZE]
        ratings_by_id = fetch_game_ratings(
            client,
            [game.igdb_game_id for game in batch],
        )
        checked_at = clock()

        stored_games = session.scalars(
            select(Game).where(
                Game.steam_app_id.in_(
                    [game.steam_app_id for game in batch]
                )
            )
        ).all()
        for stored_game in stored_games:
            # Skip games re-matched or reset since they were selected.
            if (
                stored_game.igdb_status != "ready"
                or stored_game.igdb_game_id not in ratings_by_id
            ):
                continue
            apply_ratings(
                stored_game,
                ratings_by_id[stored_game.igdb_game_id],
                checked_at,
            )
            updated_count += 1
        session.commit()

    return updated_count
