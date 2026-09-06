from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Game


@dataclass(frozen=True)
class IGDBMetadataCoverage:
    """Summarize factual metadata coverage across uniquely owned games."""

    total_games: int
    pending_games: int
    ready_games: int
    missing_games: int
    ambiguous_games: int
    attempted_games: int
    error_games: int

    @property
    def definitive_games(self) -> int:
        """Return games with a completed factual match outcome."""
        return (
            self.ready_games
            + self.missing_games
            + self.ambiguous_games
        )

    @property
    def completion_ratio(self) -> float:
        """Return the portion of owned games with definitive outcomes."""
        if self.total_games == 0:
            return 0.0

        return self.definitive_games / self.total_games

    @property
    def match_ratio(self) -> float:
        """Return the matched portion of definitive outcomes."""
        if self.definitive_games == 0:
            return 0.0

        return self.ready_games / self.definitive_games


def get_igdb_metadata_coverage(
    session: Session,
) -> IGDBMetadataCoverage:
    """Measure factual IGDB coverage across unique currently owned games.

    A shared game is counted once even when several profiles own it. Cached game
    rows no longer owned by any saved profile are excluded from this report.

    Args:
        session: The database session used for read-only coverage queries.

    Returns:
        Counts and ratios describing current factual metadata coverage.
    """
    is_owned = Game.profile_games.any()

    status_rows = session.execute(
        select(
            Game.igdb_status,
            func.count(Game.steam_app_id),
        )
        .where(is_owned)
        .group_by(Game.igdb_status)
    ).all()

    counts = {
        status: count
        for status, count in status_rows
    }

    attempted_games = session.scalar(
        select(func.count(Game.steam_app_id)).where(
            is_owned,
            Game.igdb_last_attempted_at.is_not(None),
        )
    ) or 0

    error_games = session.scalar(
        select(func.count(Game.steam_app_id)).where(
            is_owned,
            Game.igdb_last_error.is_not(None),
        )
    ) or 0

    pending_games = counts.get("pending", 0)
    ready_games = counts.get("ready", 0)
    missing_games = counts.get("missing", 0)
    ambiguous_games = counts.get("ambiguous", 0)

    return IGDBMetadataCoverage(
        total_games=(
            pending_games
            + ready_games
            + missing_games
            + ambiguous_games
        ),
        pending_games=pending_games,
        ready_games=ready_games,
        missing_games=missing_games,
        ambiguous_games=ambiguous_games,
        attempted_games=attempted_games,
        error_games=error_games,
    )
