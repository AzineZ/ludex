"""Turn cached IGDB averages into display-only ratings.

Ratings never influence scoring, eligibility, or what reaches Gemini. IGDB
only provides averages and vote counts, so a few outlier reviews can skew a
small sample; the card badge therefore needs a minimum sample, prefers
critic reviews, and Game details always show the count beside a score.
"""

from dataclasses import dataclass
from enum import StrEnum
import math

from sqlalchemy import Column

from app.models import Game

CRITIC_HEADLINE_MINIMUM_REVIEWS = 5
TOTAL_HEADLINE_MINIMUM_RATINGS = 20

RATING_COLUMNS: tuple[Column, ...] = (
    Game.igdb_total_rating,
    Game.igdb_total_rating_count,
    Game.igdb_aggregated_rating,
    Game.igdb_aggregated_rating_count,
)


class RatingSource(StrEnum):
    """Identify which IGDB average a headline score comes from."""

    CRITICS = "critics"
    TOTAL = "total"


@dataclass(frozen=True)
class RatingScore:
    """Hold one rounded 0–100 average and how many votes produced it."""

    score: int
    count: int


@dataclass(frozen=True)
class RatingHeadline:
    """Hold the single score shown on a result card."""

    source: RatingSource
    score: int


@dataclass(frozen=True)
class GameRatings:
    """Hold every available IGDB score for one game."""

    critics: RatingScore | None = None
    total: RatingScore | None = None

    @property
    def headline(self) -> RatingHeadline | None:
        """Prefer a well-reviewed critic score, then a widely rated total."""
        if (
            self.critics is not None
            and self.critics.count >= CRITIC_HEADLINE_MINIMUM_REVIEWS
        ):
            return RatingHeadline(RatingSource.CRITICS, self.critics.score)
        if (
            self.total is not None
            and self.total.count >= TOTAL_HEADLINE_MINIMUM_RATINGS
        ):
            return RatingHeadline(RatingSource.TOTAL, self.total.score)
        return None


def _rating_score(
    average: float | None,
    count: int | None,
) -> RatingScore | None:
    if average is None or count is None or count < 1:
        return None
    return RatingScore(score=math.floor(average + 0.5), count=count)


def game_ratings(row: object) -> GameRatings:
    """Build ratings from a row that selected ``RATING_COLUMNS``."""
    return GameRatings(
        critics=_rating_score(
            row.igdb_aggregated_rating,
            row.igdb_aggregated_rating_count,
        ),
        total=_rating_score(
            row.igdb_total_rating,
            row.igdb_total_rating_count,
        ),
    )
