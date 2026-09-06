from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.dependencies import get_steam_client, get_steam_rate_limit_hmac_key
from app.config import settings
from app.main import app
from app.abuse.steam import SteamAbuseController
from app.sessions.routes import get_steam_abuse_controller


def test_wrong_origin_is_rejected_before_provider_dependency() -> None:
    steam_client = MagicMock()
    app.dependency_overrides[get_steam_client] = lambda: steam_client
    try:
        with TestClient(app) as client:
            response = client.post(
                "/session",
                headers={"Origin": "https://attacker.example"},
                json={"identifier": "76561198000000000"},
            )
    finally:
        app.dependency_overrides.pop(get_steam_client, None)

    assert response.status_code == 403
    assert response.json() == {"detail": "Request origin is not allowed."}
    steam_client.resolve_steam_id.assert_not_called()


def test_exact_origin_reaches_normal_validation() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/session",
            headers={"Origin": "http://localhost:5173"},
            json={"identifier": "invalid identifier"},
        )

    assert response.status_code == 422


def test_oversized_body_is_rejected_before_route_parsing() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/session",
            content=b"x" * 4097,
            headers={
                "Content-Type": "application/json",
                "Origin": "http://localhost:5173",
            },
        )

    assert response.status_code == 413
    assert response.json() == {"detail": "Request body is too large."}


def test_missing_origin_remains_available_to_non_browser_operator_checks() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/session",
            json={"identifier": "invalid identifier"},
        )

    assert response.status_code == 422


def test_hosted_session_attempt_fails_closed_without_forwarded_client(
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "deployment_environment", "staging")
    controller = SteamAbuseController()
    app.dependency_overrides[get_steam_abuse_controller] = lambda: controller
    app.dependency_overrides[get_steam_rate_limit_hmac_key] = lambda: b"k" * 32
    try:
        with TestClient(app) as client:
            missing = client.post(
                "/session",
                json={"identifier": "invalid identifier"},
            )
            forwarded = client.post(
                "/session",
                headers={"X-Forwarded-For": "8.8.8.8, 10.0.0.2"},
                json={"identifier": "invalid identifier"},
            )
    finally:
        app.dependency_overrides.pop(get_steam_abuse_controller, None)
        app.dependency_overrides.pop(get_steam_rate_limit_hmac_key, None)

    assert missing.status_code == 429
    assert forwarded.status_code == 422
