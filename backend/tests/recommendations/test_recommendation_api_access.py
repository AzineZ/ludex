from datetime import UTC, datetime, timedelta
from hashlib import sha256

from app.main import app
from app.models import SteamAccessSession
from app.recommendations.api.router import router
from app.sessions.http import (
    ACCESS_SESSION_COOKIE_NAME,
    require_access_session,
)
from tests.recommendations.recommendation_api_support import (
    RecommendationAPI,
    _owned_game,
    _profile,
    recommendation_api,
)


def test_router_uses_session_scoped_prefix() -> None:
    assert router.prefix == "/recommendations"
    assert router.tags == ["recommendations"]

def test_recommendation_routes_require_access_session(
    recommendation_api: RecommendationAPI,
) -> None:
    app.dependency_overrides.pop(require_access_session, None)
    try:
        response = recommendation_api.client.get(
            "/recommendations/references",
            params={"query": "game"},
        )
    finally:
        app.dependency_overrides[
            require_access_session
        ] = recommendation_api.access_session_override

    assert response.status_code == 401
    assert response.json() == {
        "detail": "Steam access session required."
    }

def test_real_cookie_cannot_select_another_profile_with_query_parameter(
    recommendation_api: RecommendationAPI,
) -> None:
    token = "authorized-browser"
    selected_profile = _profile(1)
    selected_profile.access_sessions.append(
        SteamAccessSession(
            token_digest=sha256(token.encode("utf-8")).digest(),
            created_at=datetime.now(UTC) - timedelta(hours=1),
            expires_at=datetime.now(UTC) + timedelta(days=6),
        )
    )
    other_profile = _profile(2)
    recommendation_api.database_session.add_all(
        [
            _owned_game(selected_profile, 100, "Selected Game"),
            _owned_game(other_profile, 200, "Other Secret Game"),
        ]
    )
    recommendation_api.database_session.commit()
    recommendation_api.client.cookies.set(
        ACCESS_SESSION_COOKIE_NAME,
        token,
        domain="testserver.local",
        path="/",
    )

    app.dependency_overrides.pop(require_access_session, None)
    try:
        response = recommendation_api.client.get(
            "/recommendations/references",
            params={"query": "other", "profile_id": 2},
        )
    finally:
        app.dependency_overrides[
            require_access_session
        ] = recommendation_api.access_session_override

    assert response.status_code == 200
    assert response.json() == {"items": []}

def test_legacy_profile_and_recommendation_routes_are_absent(
    recommendation_api: RecommendationAPI,
) -> None:
    paths = recommendation_api.client.get("/openapi.json").json()["paths"]

    assert "/profiles" not in paths
    assert "/profiles/{profile_id}" not in paths
    assert "/profiles/{profile_id}/refresh" not in paths
    assert all(
        not path.startswith("/profiles/{profile_id}/recommendations")
        for path in paths
    )
