from typing import Any

import pytest
from pydantic import ValidationError

from app.recommendations.contracts import (
    PlayStatus,
    RecommendationPreference,
)


def test_accepts_minimum_preference() -> None:
    payload = {
        "references": [
            {
                "steam_app_id": 100,
                "facets": {
                    "genre_ids": [12],
                    "theme_ids": [],
                    "keyword_ids": [],
                    "game_mode_ids": [],
                },
            }
        ],
        "constraints": {
            "maximum_completion_minutes": None,
            "play_status": "either",
        },
    }

    preference = RecommendationPreference.model_validate(payload)

    assert preference.constraints.play_status is PlayStatus.EITHER
    assert preference.model_dump(mode="json") == payload


def test_accepts_maximum_preference_and_canonicalizes_facets() -> None:
    payload = {
        "references": [
            {
                "steam_app_id": 300,
                "facets": {
                    "genre_ids": [30, 10],
                    "theme_ids": [20],
                    "keyword_ids": [300, 100, 200],
                    "game_mode_ids": [2, 1],
                },
            },
            {
                "steam_app_id": 100,
                "facets": {
                    "genre_ids": [10],
                    "theme_ids": [],
                    "keyword_ids": [400, 200, 300],
                    "game_mode_ids": [],
                },
            },
            {
                "steam_app_id": 200,
                "facets": {
                    "genre_ids": [],
                    "theme_ids": [20],
                    "keyword_ids": [600, 500, 400],
                    "game_mode_ids": [],
                },
            },
        ],
        "constraints": {
            "maximum_completion_minutes": 60_000,
            "play_status": "previously_played",
        },
    }

    preference = RecommendationPreference.model_validate(payload)

    assert [
        reference.steam_app_id for reference in preference.references
    ] == [300, 100, 200]
    assert preference.references[0].facets.genre_ids == (10, 30)
    assert preference.references[0].facets.keyword_ids == (100, 200, 300)
    assert preference.model_dump(mode="json") == {
        **payload,
        "references": [
            {
                **payload["references"][0],
                "facets": {
                    "genre_ids": [10, 30],
                    "theme_ids": [20],
                    "keyword_ids": [100, 200, 300],
                    "game_mode_ids": [1, 2],
                },
            },
            {
                **payload["references"][1],
                "facets": {
                    **payload["references"][1]["facets"],
                    "keyword_ids": [200, 300, 400],
                },
            },
            {
                **payload["references"][2],
                "facets": {
                    **payload["references"][2]["facets"],
                    "keyword_ids": [400, 500, 600],
                },
            },
        ],
    }


def _minimum_payload() -> dict[str, Any]:
    return {
        "references": [
            {
                "steam_app_id": 100,
                "facets": {
                    "genre_ids": [12],
                    "theme_ids": [],
                    "keyword_ids": [],
                    "game_mode_ids": [],
                },
            }
        ],
        "constraints": {
            "maximum_completion_minutes": None,
            "play_status": "either",
        },
    }


@pytest.mark.parametrize(
    "location",
    ["preference", "reference", "facets", "constraints"],
)
def test_rejects_extra_fields(location: str) -> None:
    payload = _minimum_payload()

    if location == "preference":
        payload["unexpected"] = True
    elif location == "reference":
        payload["references"][0]["unexpected"] = True
    elif location == "facets":
        payload["references"][0]["facets"]["unexpected"] = []
    else:
        payload["constraints"]["unexpected"] = True

    with pytest.raises(ValidationError):
        RecommendationPreference.model_validate(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("steam_app_id", True),
        ("steam_app_id", "100"),
        ("genre_id", True),
        ("genre_id", "12"),
        ("maximum_completion_minutes", True),
        ("maximum_completion_minutes", "30"),
    ],
)
def test_rejects_coerced_integer_values(
    field: str,
    value: object,
) -> None:
    payload = _minimum_payload()

    if field == "steam_app_id":
        payload["references"][0]["steam_app_id"] = value
    elif field == "genre_id":
        payload["references"][0]["facets"]["genre_ids"] = [value]
    else:
        payload["constraints"]["maximum_completion_minutes"] = value

    with pytest.raises(ValidationError):
        RecommendationPreference.model_validate(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("steam_app_id", 0),
        ("steam_app_id", -1),
        ("genre_id", 0),
        ("genre_id", -1),
    ],
)
def test_rejects_nonpositive_ids(
    field: str,
    value: int,
) -> None:
    payload = _minimum_payload()

    if field == "steam_app_id":
        payload["references"][0]["steam_app_id"] = value
    else:
        payload["references"][0]["facets"]["genre_ids"] = [value]

    with pytest.raises(ValidationError):
        RecommendationPreference.model_validate(payload)


@pytest.mark.parametrize("value", [29, 60_001])
def test_rejects_completion_minutes_outside_range(value: int) -> None:
    payload = _minimum_payload()
    payload["constraints"]["maximum_completion_minutes"] = value

    with pytest.raises(ValidationError):
        RecommendationPreference.model_validate(payload)


@pytest.mark.parametrize("reference_count", [0, 4])
def test_rejects_reference_count_outside_range(
    reference_count: int,
) -> None:
    payload = _minimum_payload()
    reference = payload["references"][0]
    payload["references"] = [
        {
            **reference,
            "steam_app_id": steam_app_id,
        }
        for steam_app_id in range(1, reference_count + 1)
    ]

    with pytest.raises(ValidationError):
        RecommendationPreference.model_validate(payload)


def test_rejects_duplicate_reference_ids() -> None:
    payload = _minimum_payload()
    payload["references"].append(
        {
            **payload["references"][0],
        }
    )

    with pytest.raises(ValidationError):
        RecommendationPreference.model_validate(payload)


@pytest.mark.parametrize(
    "facet_field",
    [
        "genre_ids",
        "theme_ids",
        "keyword_ids",
        "game_mode_ids",
    ],
)
def test_rejects_duplicate_facets_within_category(
    facet_field: str,
) -> None:
    payload = _minimum_payload()
    payload["references"][0]["facets"][facet_field] = [12, 12]

    with pytest.raises(ValidationError):
        RecommendationPreference.model_validate(payload)


def test_rejects_more_than_three_keywords() -> None:
    payload = _minimum_payload()
    payload["references"][0]["facets"]["keyword_ids"] = [
        10,
        20,
        30,
        40,
    ]

    with pytest.raises(ValidationError):
        RecommendationPreference.model_validate(payload)


def test_rejects_reference_without_selected_facets() -> None:
    payload = _minimum_payload()
    payload["references"][0]["facets"] = {
        "genre_ids": [],
        "theme_ids": [],
        "keyword_ids": [],
        "game_mode_ids": [],
    }

    with pytest.raises(ValidationError):
        RecommendationPreference.model_validate(payload)


@pytest.mark.parametrize(
    "play_status",
    [" either", "either ", "Either"],
)
def test_rejects_noncanonical_play_status(play_status: str) -> None:
    payload = _minimum_payload()
    payload["constraints"]["play_status"] = play_status

    with pytest.raises(ValidationError):
        RecommendationPreference.model_validate(payload)


@pytest.mark.parametrize("field", ["references", "constraints"])
def test_requires_top_level_fields(field: str) -> None:
    payload = _minimum_payload()
    del payload[field]

    with pytest.raises(ValidationError):
        RecommendationPreference.model_validate(payload)


@pytest.mark.parametrize("field", ["steam_app_id", "facets"])
def test_requires_reference_fields(field: str) -> None:
    payload = _minimum_payload()
    del payload["references"][0][field]

    with pytest.raises(ValidationError):
        RecommendationPreference.model_validate(payload)


@pytest.mark.parametrize(
    "field",
    [
        "genre_ids",
        "theme_ids",
        "keyword_ids",
        "game_mode_ids",
    ],
)
def test_requires_every_facet_array(field: str) -> None:
    payload = _minimum_payload()
    del payload["references"][0]["facets"][field]

    with pytest.raises(ValidationError):
        RecommendationPreference.model_validate(payload)


@pytest.mark.parametrize(
    "field",
    ["maximum_completion_minutes", "play_status"],
)
def test_requires_constraint_fields(field: str) -> None:
    payload = _minimum_payload()
    del payload["constraints"][field]

    with pytest.raises(ValidationError):
        RecommendationPreference.model_validate(payload)


def test_accepts_lower_completion_boundary_and_unplayed_status() -> None:
    payload = _minimum_payload()
    payload["constraints"] = {
        "maximum_completion_minutes": 30,
        "play_status": "unplayed",
    }

    preference = RecommendationPreference.model_validate(payload)

    assert preference.constraints.maximum_completion_minutes == 30
    assert preference.constraints.play_status is PlayStatus.UNPLAYED


def test_preference_and_nested_models_are_frozen() -> None:
    preference = RecommendationPreference.model_validate(
        _minimum_payload()
    )

    with pytest.raises(ValidationError):
        preference.references = ()

    with pytest.raises(ValidationError):
        preference.references[0].facets.genre_ids = (99,)
