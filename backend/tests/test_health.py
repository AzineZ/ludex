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
