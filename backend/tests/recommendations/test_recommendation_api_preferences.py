from copy import deepcopy

import pytest

from tests.recommendations.recommendation_api_support import (
    RecommendationAPI,
    _assert_error,
    _owned_game,
    _profile,
    _term_link,
    _valid_preference_body,
    recommendation_api,
)


def test_validate_preference_returns_canonical_direct_object(
    recommendation_api: RecommendationAPI,
) -> None:
    profile = _profile()
    recommendation_api.database_session.add(
        _owned_game(
            profile,
            100,
            "Reference Game",
            links=(
                _term_link("genre", 10, "Adventure"),
                _term_link("genre", 20, "Role-playing"),
            ),
        )
    )
    recommendation_api.database_session.commit()
    request_body = _valid_preference_body(
        genre_ids=[20, 10]
    )

    response = recommendation_api.client.post(
        "/recommendations/preferences/validate",
        json=request_body,
    )

    assert response.status_code == 200
    assert response.json() == {
        "references": [
            {
                "steam_app_id": 100,
                "facets": {
                    "genre_ids": [10, 20],
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

def test_validation_maps_unknown_profile_to_not_found(
    recommendation_api: RecommendationAPI,
) -> None:
    response = recommendation_api.client.post(
        "/recommendations/preferences/validate",
        json=_valid_preference_body(),
    )

    _assert_error(
        response,
        status_code=404,
        code="profile_not_found",
        field="profile_id",
        message="The selected profile does not exist.",
    )

def test_validation_maps_unowned_reference_to_not_found(
    recommendation_api: RecommendationAPI,
) -> None:
    recommendation_api.database_session.add(_profile())
    recommendation_api.database_session.commit()

    response = recommendation_api.client.post(
        "/recommendations/preferences/validate",
        json=_valid_preference_body(),
    )

    _assert_error(
        response,
        status_code=404,
        code="reference_not_owned",
        field="references[0].steam_app_id",
        message=(
            "The selected reference game is not owned by this profile."
        ),
    )

def test_validation_maps_unavailable_metadata_to_conflict(
    recommendation_api: RecommendationAPI,
) -> None:
    profile = _profile()
    recommendation_api.database_session.add(
        _owned_game(
            profile,
            100,
            "Unavailable Reference",
            status="pending",
        )
    )
    recommendation_api.database_session.commit()

    response = recommendation_api.client.post(
        "/recommendations/preferences/validate",
        json=_valid_preference_body(),
    )

    _assert_error(
        response,
        status_code=409,
        code="reference_metadata_unavailable",
        field="references[0].steam_app_id",
        message=(
            "Factual metadata is unavailable for this reference game."
        ),
    )

def test_validation_maps_invalid_membership_to_unprocessable(
    recommendation_api: RecommendationAPI,
) -> None:
    profile = _profile()
    recommendation_api.database_session.add(
        _owned_game(profile, 100, "Reference Game")
    )
    recommendation_api.database_session.commit()

    response = recommendation_api.client.post(
        "/recommendations/preferences/validate",
        json=_valid_preference_body(),
    )

    _assert_error(
        response,
        status_code=422,
        code="facet_not_on_reference",
        field="references[0].facets.genre_ids[0]",
        message=(
            "The selected facet does not belong to this reference game."
        ),
    )

def _structural_request_case(case_name: str) -> object:
    body = deepcopy(_valid_preference_body())
    reference = body["references"][0]
    facets = reference["facets"]
    constraints = body["constraints"]

    if case_name == "missing_references":
        del body["references"]
    elif case_name == "unexpected_top_level":
        body["unexpected"] = True
    elif case_name == "references_wrong_type":
        body["references"] = "not-a-list"
    elif case_name == "invalid_reference_count":
        body["references"] = []
    elif case_name == "duplicate_reference":
        body["references"].append(deepcopy(reference))
    elif case_name == "steam_id_wrong_type":
        reference["steam_app_id"] = True
    elif case_name == "steam_id_not_positive":
        reference["steam_app_id"] = 0
    elif case_name == "missing_facet_array":
        del facets["theme_ids"]
    elif case_name == "unexpected_facet":
        facets["unexpected"] = []
    elif case_name == "facet_id_wrong_type":
        facets["genre_ids"] = [True]
    elif case_name == "facet_id_not_positive":
        facets["genre_ids"] = [0]
    elif case_name == "duplicate_facet":
        facets["genre_ids"] = [10, 10]
    elif case_name == "empty_facets":
        facets["genre_ids"] = []
    elif case_name == "too_many_keywords":
        facets["genre_ids"] = []
        facets["keyword_ids"] = [1, 2, 3, 4]
    elif case_name == "missing_constraint":
        del constraints["maximum_completion_minutes"]
    elif case_name == "completion_wrong_type":
        constraints["maximum_completion_minutes"] = True
    elif case_name == "completion_out_of_range":
        constraints["maximum_completion_minutes"] = 29
    elif case_name == "invalid_play_status":
        constraints["play_status"] = "sometimes"
    elif case_name == "unexpected_constraint":
        constraints["unexpected"] = True
    elif case_name == "non_object_body":
        return []
    else:
        raise AssertionError(f"Unknown structural case: {case_name}")

    return body

@pytest.mark.parametrize(
    (
        "case_name",
        "expected_code",
        "expected_field",
        "expected_message",
    ),
    [
        (
            "missing_references",
            "missing_field",
            "references",
            "This field is required.",
        ),
        (
            "unexpected_top_level",
            "unexpected_field",
            "unexpected",
            "Unexpected fields are not allowed.",
        ),
        (
            "references_wrong_type",
            "invalid_type",
            "references",
            "This field has an invalid type.",
        ),
        (
            "invalid_reference_count",
            "invalid_reference_count",
            "references",
            "Select between one and three reference games.",
        ),
        (
            "duplicate_reference",
            "duplicate_reference",
            "references[1].steam_app_id",
            "Reference games must be unique.",
        ),
        (
            "steam_id_wrong_type",
            "invalid_type",
            "references[0].steam_app_id",
            "This field has an invalid type.",
        ),
        (
            "steam_id_not_positive",
            "invalid_value",
            "references[0].steam_app_id",
            "IDs must be positive integers.",
        ),
        (
            "missing_facet_array",
            "missing_field",
            "references[0].facets.theme_ids",
            "This field is required.",
        ),
        (
            "unexpected_facet",
            "unexpected_field",
            "references[0].facets.unexpected",
            "Unexpected fields are not allowed.",
        ),
        (
            "facet_id_wrong_type",
            "invalid_type",
            "references[0].facets.genre_ids[0]",
            "This field has an invalid type.",
        ),
        (
            "facet_id_not_positive",
            "invalid_value",
            "references[0].facets.genre_ids[0]",
            "IDs must be positive integers.",
        ),
        (
            "duplicate_facet",
            "duplicate_facet",
            "references[0].facets.genre_ids[1]",
            "Facet IDs must be unique within their category.",
        ),
        (
            "empty_facets",
            "empty_reference_facets",
            "references[0].facets",
            "Select at least one facet from this reference game.",
        ),
        (
            "too_many_keywords",
            "too_many_keywords",
            "references[0].facets.keyword_ids",
            "Select no more than three keywords per reference game.",
        ),
        (
            "missing_constraint",
            "missing_field",
            "constraints.maximum_completion_minutes",
            "This field is required.",
        ),
        (
            "completion_wrong_type",
            "invalid_type",
            "constraints.maximum_completion_minutes",
            "This field has an invalid type.",
        ),
        (
            "completion_out_of_range",
            "invalid_value",
            "constraints.maximum_completion_minutes",
            (
                "Maximum completion time must be between 30 and "
                "60000 minutes."
            ),
        ),
        (
            "invalid_play_status",
            "invalid_value",
            "constraints.play_status",
            (
                "Play status must be unplayed, previously_played, "
                "or either."
            ),
        ),
        (
            "unexpected_constraint",
            "unexpected_field",
            "constraints.unexpected",
            "Unexpected fields are not allowed.",
        ),
        (
            "non_object_body",
            "invalid_type",
            "body",
            "The request body must be a JSON object.",
        ),
    ],
)
def test_validation_translates_structural_request_failures(
    recommendation_api: RecommendationAPI,
    case_name: str,
    expected_code: str,
    expected_field: str,
    expected_message: str,
) -> None:
    response = recommendation_api.client.post(
        "/recommendations/preferences/validate",
        json=_structural_request_case(case_name),
    )

    _assert_error(
        response,
        status_code=422,
        code=expected_code,
        field=expected_field,
        message=expected_message,
    )

def test_validation_rejects_missing_body(
    recommendation_api: RecommendationAPI,
) -> None:
    response = recommendation_api.client.post(
        "/recommendations/preferences/validate"
    )

    _assert_error(
        response,
        status_code=422,
        code="missing_field",
        field="body",
        message="This field is required.",
    )

def test_validation_rejects_invalid_json(
    recommendation_api: RecommendationAPI,
) -> None:
    response = recommendation_api.client.post(
        "/recommendations/preferences/validate",
        content=b'{"references": [}',
        headers={"content-type": "application/json"},
    )

    _assert_error(
        response,
        status_code=422,
        code="invalid_type",
        field="body",
        message="The request body must be a JSON object.",
    )
