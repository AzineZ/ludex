from unittest.mock import Mock

import pytest

import app.recommendations.api.assistant as assistant_routes
from app.gemini.reranking.service import (
    RerankAssistantItem,
    RerankAssistantResult,
    RerankAssistantStatus,
)
from app.main import app
from tests.gemini.reranking.test_candidate_pool import _add_game
from tests.recommendations.recommendation_api_support import (
    RecommendationAPI,
    _assert_error,
    recommendation_api,
)


def test_assistant_genres_returns_only_profile_ready_options(
    recommendation_api: RecommendationAPI,
) -> None:
    _add_game(
        recommendation_api.database_session,
        profile_id=1,
        steam_app_id=1,
    )
    _add_game(
        recommendation_api.database_session,
        profile_id=1,
        steam_app_id=2,
    )

    response = recommendation_api.client.get(
        "/recommendations/assistant/genres"
    )

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {"igdb_id": 31, "name": "Adventure", "eligible_count": 2}
        ]
    }


def test_assistant_filter_options_are_provider_free(
    recommendation_api: RecommendationAPI,
) -> None:
    _add_game(
        recommendation_api.database_session,
        profile_id=1,
        steam_app_id=1,
        theme=(17, "Fantasy"),
        game_mode=(1, "Single player"),
    )

    response = recommendation_api.client.post(
        "/recommendations/assistant/filters",
        json={
            "selected_genre_id": 31,
            "play_status": "either",
            "maximum_completion_minutes": None,
            "theme_ids": [17],
            "game_mode_ids": [1],
            "rejected_steam_app_ids": [],
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "eligible_count": 1,
        "candidate_limit": 200,
        "themes": [{"igdb_id": 17, "name": "Fantasy", "eligible_count": 1}],
        "game_modes": [
            {"igdb_id": 1, "name": "Single player", "eligible_count": 1}
        ],
    }


def test_assistant_submit_maps_ai_summary_and_prompt_specific_reasoning(
    recommendation_api: RecommendationAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recommend = Mock(
        return_value=RerankAssistantResult(
            status=RerankAssistantStatus.RANKED,
            eligible_count=1,
            items=(
                RerankAssistantItem(
                    rank=1,
                    steam_app_id=7,
                    title="A Short Hike",
                    cover_url="https://images.example/cover.jpg",
                    profile_playtime_minutes=0,
                    normal_completion_seconds=7_200,
                    summary="A gentle, low-pressure hiking adventure.",
                    reasoning=(
                        "Its gentle pace fits your request for something relaxing."
                    ),
                ),
            ),
        )
    )
    monkeypatch.setattr(assistant_routes, "recommend_with_gemini", recommend)

    response = recommendation_api.client.post(
        "/recommendations/assistant",
        json={
            "prompt": "Something relaxing",
            "selected_genre_id": 31,
            "filters": {
                "play_status": "either",
                "maximum_completion_minutes": None,
                "theme_ids": [],
                "game_mode_ids": [],
            },
            "rejected_steam_app_ids": [],
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "ranked",
        "eligible_count": 1,
        "candidate_limit": 200,
        "items": [
            {
                "rank": 1,
                "steam_app_id": 7,
                "title": "A Short Hike",
                "cover_url": "https://images.example/cover.jpg",
                "profile_playtime_minutes": 0,
                "normal_completion_seconds": 7200,
                "summary": "A gentle, low-pressure hiking adventure.",
                "reasoning": (
                    "Its gentle pace fits your request for something relaxing."
                ),
                "content_source": "ai_generated",
            }
        ],
        "message": None,
        "guided_fallback_available": True,
    }
    assert recommend.call_args.kwargs["profile_id"] == 1


def test_assistant_missing_configuration_is_a_successful_fallback_state(
    recommendation_api: RecommendationAPI,
) -> None:
    _add_game(
        recommendation_api.database_session,
        profile_id=1,
        steam_app_id=1,
    )

    response = recommendation_api.client.post(
        "/recommendations/assistant",
        json={
            "prompt": "Something relaxing",
            "selected_genre_id": 31,
            "filters": {
                "play_status": "either",
                "maximum_completion_minutes": None,
                "theme_ids": [],
                "game_mode_ids": [],
            },
            "rejected_steam_app_ids": [],
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "unavailable"
    assert response.json()["guided_fallback_available"] is True


def test_assistant_revalidates_unavailable_genre_at_http_boundary(
    recommendation_api: RecommendationAPI,
) -> None:
    response = recommendation_api.client.post(
        "/recommendations/assistant/filters",
        json={
            "selected_genre_id": 999,
            "play_status": "either",
            "maximum_completion_minutes": None,
            "rejected_steam_app_ids": [],
        },
    )

    _assert_error(
        response,
        status_code=409,
        code="assistant_option_unavailable",
        field="selected_genre_id",
        message="The selected genre is not available for this library.",
    )


def test_assistant_routes_require_access_session(
    recommendation_api: RecommendationAPI,
) -> None:
    from app.sessions.http import require_access_session

    app.dependency_overrides.pop(require_access_session, None)
    try:
        response = recommendation_api.client.get(
            "/recommendations/assistant/genres"
        )
    finally:
        app.dependency_overrides[
            require_access_session
        ] = recommendation_api.access_session_override

    assert response.status_code == 401
