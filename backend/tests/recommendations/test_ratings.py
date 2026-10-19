from types import SimpleNamespace

import pytest

from app.recommendations.ratings import (
    CRITIC_HEADLINE_MINIMUM_REVIEWS,
    TOTAL_HEADLINE_MINIMUM_RATINGS,
    GameRatings,
    RatingHeadline,
    RatingScore,
    RatingSource,
    game_ratings,
)
from tests.recommendations.recommendation_api_support import (
    RecommendationAPI,
    _add_recommendation_library,
    _valid_preference_body,
    recommendation_api,
)
from app.models import Game


def _row(
    total: float | None = None,
    total_count: int | None = None,
    critics: float | None = None,
    critics_count: int | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        igdb_total_rating=total,
        igdb_total_rating_count=total_count,
        igdb_aggregated_rating=critics,
        igdb_aggregated_rating_count=critics_count,
    )


def test_headline_thresholds_match_the_approved_sample_sizes() -> None:
    assert CRITIC_HEADLINE_MINIMUM_REVIEWS == 5
    assert TOTAL_HEADLINE_MINIMUM_RATINGS == 20


@pytest.mark.parametrize(
    ("row", "expected"),
    [
        (_row(88.0, 1_204, 91.0, 5), RatingHeadline(RatingSource.CRITICS, 91)),
        (_row(88.0, 1_204, 40.0, 4), RatingHeadline(RatingSource.TOTAL, 88)),
        (_row(88.0, 20, None, None), RatingHeadline(RatingSource.TOTAL, 88)),
        (_row(88.0, 19, 91.0, 4), None),
        (_row(None, None, None, None), None),
    ],
)
def test_headline_prefers_well_reviewed_critics_then_widely_rated_totals(
    row: SimpleNamespace,
    expected: RatingHeadline | None,
) -> None:
    assert game_ratings(row).headline == expected


def test_scores_round_half_up_and_need_at_least_one_vote() -> None:
    assert game_ratings(_row(87.5, 1, 84.49, 3)) == GameRatings(
        critics=RatingScore(score=84, count=3),
        total=RatingScore(score=88, count=1),
    )
    assert game_ratings(_row(87.5, 0, 84.0, None)) == GameRatings()


def test_guided_results_expose_ratings_with_their_counts(
    recommendation_api: RecommendationAPI,
) -> None:
    _add_recommendation_library(recommendation_api, 2)
    rated = recommendation_api.database_session.get(Game, 201)
    rated.igdb_total_rating = 87.4
    rated.igdb_total_rating_count = 1_204
    rated.igdb_aggregated_rating = 91.0
    rated.igdb_aggregated_rating_count = 3
    recommendation_api.database_session.commit()

    response = recommendation_api.client.post(
        "/recommendations",
        json=_valid_preference_body(),
    )

    assert response.status_code == 200
    items = response.json()["items"]
    assert items[0]["ratings"] == {
        "headline": {"source": "total", "score": 87},
        "critics": {"score": 91, "count": 3},
        "total": {"score": 87, "count": 1_204},
    }
    assert items[1]["ratings"] == {
        "headline": None,
        "critics": None,
        "total": None,
    }
