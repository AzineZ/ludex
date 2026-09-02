from collections.abc import Generator
from unittest.mock import MagicMock

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.database import get_database_session
from app.main import app


def test_health_check_reports_database_connection() -> None:
    database_session = MagicMock(spec=Session)

    def override_database_session() -> Generator[Session, None, None]:
        yield database_session

    app.dependency_overrides[get_database_session] = override_database_session

    try:
        with TestClient(app) as client:
            response = client.get("/health")
    finally:
        app.dependency_overrides.pop(get_database_session, None)

    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
        "database": "connected",
    }
    database_session.execute.assert_called_once()


def test_cors_allows_credentials_only_for_configured_frontend() -> None:
    with TestClient(app) as client:
        allowed = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
        unlisted = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:4173",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == (
        "http://localhost:5173"
    )
    assert allowed.headers["access-control-allow-credentials"] == "true"
    assert "access-control-allow-origin" not in unlisted.headers
