from collections.abc import Generator
import logging
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
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


def test_health_check_sanitizes_database_unavailability(
    caplog: pytest.LogCaptureFixture,
) -> None:
    database_session = MagicMock(spec=Session)
    database_session.execute.side_effect = OperationalError(
        "SELECT secret_column FROM private_table",
        {"password": "do-not-expose"},
        RuntimeError("database host is private.internal"),
    )

    def override_database_session() -> Generator[Session, None, None]:
        yield database_session

    app.dependency_overrides[get_database_session] = override_database_session

    try:
        with caplog.at_level(logging.ERROR, logger="ludex.reliability"):
            with TestClient(app, raise_server_exceptions=False) as client:
                response = client.get("/health")
    finally:
        app.dependency_overrides.pop(get_database_session, None)

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Ludex is temporarily unavailable."
    }
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
    assert record.operation == "health_check"
    assert record.failure_category == "database_unavailable"
    assert record.status_code == 503
    assert "secret_column" not in caplog.text
    assert "do-not-expose" not in caplog.text
    assert "private.internal" not in caplog.text


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
