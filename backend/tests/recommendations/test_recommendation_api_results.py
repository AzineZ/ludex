import logging
from typing import Any

import pytest
from sqlalchemy import event
from sqlalchemy.exc import OperationalError

import app.recommendations.api.results as results_routes_module
from app.config import settings
from app.gemini.client import GeminiClient
from app.models import GameIGDBMetadataTerm, IGDBMetadataTerm
from tests.recommendations.recommendation_api_support import (
    RecommendationAPI,
    _add_recommendation_library,
    _assert_error,
    _owned_game,
    _profile,
    _valid_preference_body,
    _valid_refinement_body,
    recommendation_api,
)


@pytest.mark.parametrize(
    ("candidate_count", "expected_outcome"),
    [
        (0, "empty"),
        (2, "sparse"),
        (6, "complete"),
    ],
)
def test_final_recommendation_endpoint_returns_every_success_outcome(
    recommendation_api: RecommendationAPI,
    candidate_count: int,
    expected_outcome: str,
) -> None:
    _add_recommendation_library(recommendation_api, candidate_count)

    response = recommendation_api.client.post(
        "/recommendations",
        json=_valid_preference_body(),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["outcome"] == expected_outcome
    assert payload["eligible_count"] == candidate_count
    assert payload["returned_count"] == candidate_count
    assert [item["rank"] for item in payload["items"]] == list(
        range(1, candidate_count + 1)
    )
    assert [item["steam_app_id"] for item in payload["items"]] == list(
        range(201, 201 + candidate_count)
    )
    if payload["items"]:
        first = payload["items"][0]
        assert first["title"] == "Candidate 1"
        assert first["profile_playtime_minutes"] == 1
        assert first["normal_completion_seconds"] == 3_600
        assert first["factual_evidence"] == {
            "version": "factual-overlap-v1",
            "score_basis_points": 10_000,
            "active_budget": 30,
            "contributions": [
                {
                    "reference_steam_app_id": 100,
                    "facet_kind": "genre",
                    "facet_igdb_id": 10,
                    "match_state": "matched",
                    "points_numerator": 10_000,
                    "points_denominator": 1,
                }
            ],
        }
        assert first["facet_labels"] == [
            {
                "facet_kind": "genre",
                "facet_igdb_id": 10,
                "name": "Adventure",
            }
        ]
        assert first["match_summary"] == {
            "reasons": [
                {
                    "facet_kind": "genre",
                    "facet_igdb_id": 10,
                    "name": "Adventure",
                    "reference_steam_app_ids": [100],
                    "points_numerator": 10_000,
                    "points_denominator": 1,
                }
            ],
            "additional_match_count": 0,
            "text": "Matches your Adventure preference.",
        }
        assert first["tradeoff"] is None

def test_recommendation_database_failure_returns_safe_retryable_error(
    recommendation_api: RecommendationAPI,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def fail_recommendation(*_: object, **__: object) -> None:
        raise OperationalError(
            "SELECT secret_column FROM private_table",
            {"password": "do-not-expose"},
            RuntimeError("database host is private.internal"),
        )

    monkeypatch.setattr(
        results_routes_module,
        "recommend_cached_games",
        fail_recommendation,
    )

    with caplog.at_level(logging.ERROR, logger="ludex.reliability"):
        response = recommendation_api.client.post(
            "/recommendations",
            json=_valid_preference_body(),
        )

    _assert_error(
        response,
        status_code=503,
        code="service_unavailable",
        field="request",
        message="Recommendations are temporarily unavailable.",
    )
    assert "secret_column" not in response.text
    assert "do-not-expose" not in response.text
    assert "private.internal" not in response.text
    reliability_records = [
        record
        for record in caplog.records
        if record.name == "ludex.reliability"
    ]
    assert len(reliability_records) == 1
    record = reliability_records[0]
    assert record.getMessage() == "Database request failed."
    assert record.operation == "create_final_recommendations"
    assert record.failure_category == "database_unavailable"
    assert record.status_code == 503
    assert "secret_column" not in caplog.text
    assert "do-not-expose" not in caplog.text
    assert "private.internal" not in caplog.text

def test_refinement_endpoint_excludes_rejected_games(
    recommendation_api: RecommendationAPI,
) -> None:
    _add_recommendation_library(recommendation_api, 6)

    response = recommendation_api.client.post(
        "/recommendations/refine",
        json=_valid_refinement_body([201, 203]),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["outcome"] == "sparse"
    assert payload["eligible_count"] == 4
    assert payload["returned_count"] == 4
    assert [item["steam_app_id"] for item in payload["items"]] == [
        202,
        204,
        205,
        206,
    ]

def test_refinement_endpoint_accepts_an_empty_exclusion_set(
    recommendation_api: RecommendationAPI,
) -> None:
    _add_recommendation_library(recommendation_api, 2)

    response = recommendation_api.client.post(
        "/recommendations/refine",
        json=_valid_refinement_body(),
    )

    assert response.status_code == 200
    assert response.json()["returned_count"] == 2

def test_refinement_endpoint_accepts_exactly_thirty_exclusions(
    recommendation_api: RecommendationAPI,
) -> None:
    _add_recommendation_library(recommendation_api, 2)

    response = recommendation_api.client.post(
        "/recommendations/refine",
        json=_valid_refinement_body(list(range(1_000, 1_030))),
    )

    assert response.status_code == 200
    assert response.json()["returned_count"] == 2

@pytest.mark.parametrize(
    (
        "rejected_steam_app_ids",
        "expected_code",
        "expected_field",
        "expected_message",
    ),
    [
        (
            [201, 201],
            "duplicate_rejected_game",
            "rejected_steam_app_ids[1]",
            "Rejected game IDs must be unique.",
        ),
        (
            list(range(1, 32)),
            "too_many_rejected_games",
            "rejected_steam_app_ids",
            "A session may exclude at most 30 rejected games.",
        ),
        (
            [True],
            "invalid_type",
            "rejected_steam_app_ids[0]",
            "This field has an invalid type.",
        ),
        (
            [0],
            "invalid_value",
            "rejected_steam_app_ids[0]",
            "IDs must be positive integers.",
        ),
    ],
)
def test_refinement_rejects_invalid_exclusion_lists(
    recommendation_api: RecommendationAPI,
    rejected_steam_app_ids: list[object],
    expected_code: str,
    expected_field: str,
    expected_message: str,
) -> None:
    response = recommendation_api.client.post(
        "/recommendations/refine",
        json=_valid_refinement_body(rejected_steam_app_ids),
    )

    _assert_error(
        response,
        status_code=422,
        code=expected_code,
        field=expected_field,
        message=expected_message,
    )

def test_refinement_requires_the_bounded_exclusion_field(
    recommendation_api: RecommendationAPI,
) -> None:
    response = recommendation_api.client.post(
        "/recommendations/refine",
        json={"preference": _valid_preference_body()},
    )

    _assert_error(
        response,
        status_code=422,
        code="missing_field",
        field="rejected_steam_app_ids",
        message="This field is required.",
    )

def test_final_recommendation_endpoint_maps_preference_failure(
    recommendation_api: RecommendationAPI,
) -> None:
    response = recommendation_api.client.post(
        "/recommendations",
        json=_valid_preference_body(),
    )

    _assert_error(
        response,
        status_code=404,
        code="profile_not_found",
        field="profile_id",
        message="The selected profile does not exist.",
    )

@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/recommendations", _valid_preference_body()),
        (
            "/recommendations/refine",
            _valid_refinement_body([201]),
        ),
    ],
)
def test_recommendation_requests_are_bounded_read_only_and_cache_only(
    recommendation_api: RecommendationAPI,
    path: str,
    body: dict[str, Any],
) -> None:
    _add_recommendation_library(recommendation_api, 6)
    statements: list[str] = []

    def record_statement(
        connection: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        statements.append(statement)

    event.listen(
        recommendation_api.engine,
        "before_cursor_execute",
        record_statement,
    )
    try:
        response = recommendation_api.client.post(
            path,
            json=body,
        )
    finally:
        event.remove(
            recommendation_api.engine,
            "before_cursor_execute",
            record_statement,
        )

    assert response.status_code == 200
    selects = [
        statement
        for statement in statements
        if statement.lstrip().upper().startswith("SELECT")
    ]
    writes = [
        statement
        for statement in statements
        if statement.lstrip().upper().startswith(
            ("INSERT", "UPDATE", "DELETE")
        )
    ]
    assert len(selects) == 5
    assert writes == []
    combined_sql = " ".join(statement.lower() for statement in selects)
    assert "game_trait" not in combined_sql
    assert "gemini" not in combined_sql

def test_large_library_is_deterministic_with_fixed_query_count(
    recommendation_api: RecommendationAPI,
) -> None:
    profile = _profile()
    genre = IGDBMetadataTerm(
        kind="genre",
        igdb_id=10,
        name="Adventure",
    )
    reference = _owned_game(
        profile,
        100,
        "Reference Game",
        links=(GameIGDBMetadataTerm(term=genre),),
    )
    candidates = tuple(
        _owned_game(
            profile,
            steam_app_id,
            f"Candidate {steam_app_id}",
            links=(GameIGDBMetadataTerm(term=genre),),
        )
        for steam_app_id in range(1_500, 1_000, -1)
    )
    recommendation_api.database_session.add_all(
        (reference, *candidates)
    )
    recommendation_api.database_session.commit()
    statements: list[str] = []

    def record_statement(
        connection: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        statements.append(statement)

    event.listen(
        recommendation_api.engine,
        "before_cursor_execute",
        record_statement,
    )
    try:
        first = recommendation_api.client.post(
            "/recommendations",
            json=_valid_preference_body(),
        )
        second = recommendation_api.client.post(
            "/recommendations",
            json=_valid_preference_body(),
        )
    finally:
        event.remove(
            recommendation_api.engine,
            "before_cursor_execute",
            record_statement,
        )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    assert first.json()["outcome"] == "complete"
    assert first.json()["eligible_count"] == 500
    assert first.json()["returned_count"] == 6
    assert [
        item["steam_app_id"] for item in first.json()["items"]
    ] == list(range(1_001, 1_007))

    selects = [
        statement
        for statement in statements
        if statement.lstrip().upper().startswith("SELECT")
    ]
    writes = [
        statement
        for statement in statements
        if statement.lstrip().upper().startswith(
            ("INSERT", "UPDATE", "DELETE")
        )
    ]
    assert len(selects) == 10
    assert writes == []
    combined_sql = " ".join(statement.lower() for statement in selects)
    assert "game_trait" not in combined_sql
    assert "gemini" not in combined_sql

def test_cached_recommendations_do_not_require_or_call_gemini(
    recommendation_api: RecommendationAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _add_recommendation_library(recommendation_api, 6)
    monkeypatch.setattr(settings, "gemini_api_key", None)

    def reject_gemini_call(*_: object, **__: object) -> None:
        raise AssertionError("Gemini must not run for recommendations.")

    monkeypatch.setattr(
        GeminiClient,
        "generate_structured_content",
        reject_gemini_call,
    )

    response = recommendation_api.client.post(
        "/recommendations",
        json=_valid_preference_body(),
    )

    assert response.status_code == 200
    assert response.json()["outcome"] == "complete"
    assert response.json()["returned_count"] == 6
