from datetime import UTC, datetime

import pytest

from app.integrations.igdb.client import IGDBResponseError
from app.integrations.igdb.metadata import (
    GAME_METADATA_FIELDS,
    IGDBGameMetadata,
    IGDBNamedEntity,
    IGDBRatings,
    normalize_game_metadata,
    normalize_ratings,
)
from app.integrations.igdb.persistence import apply_ready_metadata
from app.models import Game


ENRICHED_AT = datetime(2026, 10, 19, tzinfo=UTC)


def test_enrichment_requests_every_rating_field() -> None:
    for field in (
        "total_rating",
        "total_rating_count",
        "aggregated_rating",
        "aggregated_rating_count",
    ):
        assert field in GAME_METADATA_FIELDS.split(",")


def test_ratings_are_normalized_from_a_game_response() -> None:
    metadata = normalize_game_metadata(
        {
            "id": 1,
            "name": "Rated",
            "updated_at": 1_700_000_000,
            "total_rating": 87.4,
            "total_rating_count": 1_204,
            "aggregated_rating": 91,
            "aggregated_rating_count": 12,
        }
    )

    assert metadata.ratings == IGDBRatings(
        total_rating=87.4,
        total_rating_count=1_204,
        aggregated_rating=91.0,
        aggregated_rating_count=12,
    )


def test_missing_ratings_stay_unknown() -> None:
    assert normalize_ratings({"id": 1}) == IGDBRatings()


@pytest.mark.parametrize(
    "field_values",
    [
        {"total_rating": 100.5},
        {"aggregated_rating": -1},
        {"total_rating": True},
        {"total_rating": "87"},
        {"total_rating_count": -3},
        {"aggregated_rating_count": 2.5},
    ],
)
def test_invalid_ratings_are_rejected(field_values: dict[str, object]) -> None:
    with pytest.raises(IGDBResponseError):
        normalize_ratings(field_values)


def test_ready_metadata_stores_ratings_and_when_they_were_checked() -> None:
    game = Game(steam_app_id=10, name="Rated")
    apply_ready_metadata(
        game,
        IGDBGameMetadata(
            igdb_game_id=1,
            name="Rated",
            summary=None,
            first_release_at=None,
            cover_image_id=None,
            genres=(IGDBNamedEntity(5, "Shooter"),),
            themes=(),
            keywords=(),
            game_modes=(),
            updated_at=ENRICHED_AT,
            ratings=IGDBRatings(
                total_rating=87.4,
                total_rating_count=1_204,
                aggregated_rating=None,
                aggregated_rating_count=None,
            ),
        ),
        ENRICHED_AT,
    )

    assert (
        game.igdb_total_rating,
        game.igdb_total_rating_count,
        game.igdb_aggregated_rating,
        game.igdb_aggregated_rating_count,
        game.igdb_ratings_checked_at,
    ) == (87.4, 1_204, None, None, ENRICHED_AT)
