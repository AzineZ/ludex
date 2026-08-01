import os
from collections.abc import Generator
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://ludex:ludex@localhost:5432/ludex",
)
os.environ.setdefault("FRONTEND_ORIGIN", "http://localhost:5173")
os.environ.setdefault("STEAM_API_KEY", "test-steam-api-key")

from app.steam_client import SteamClient
from app.main import app
from app.dependencies import get_steam_client
from app.database import Base, get_database_session


@pytest.fixture
def steam_client() -> MagicMock:
    return MagicMock(spec=SteamClient)


@pytest.fixture
def profile_api_client(
    steam_client: MagicMock,
) -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    test_session_factory = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)

    def override_database_session() -> Generator[Session, None, None]:
        with test_session_factory() as database_session:
            yield database_session

    def override_steam_client() -> SteamClient:
        return steam_client

    app.dependency_overrides[
        get_database_session
    ] = override_database_session
    app.dependency_overrides[
        get_steam_client
    ] = override_steam_client

    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_database_session, None)
        app.dependency_overrides.pop(get_steam_client, None)
        engine.dispose()
