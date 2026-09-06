from collections.abc import Generator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_database_session
from app.main import app
from app.models import (
    Game,
    GameIGDBMetadataTerm,
    IGDBMetadataTerm,
    Profile,
    ProfileGame,
)
from app.sessions.http import require_access_session
from app.sessions.service import ActiveAccessSession


@dataclass(frozen=True)
class RecommendationAPI:
    """Provide the HTTP client and database handles used by route tests."""

    client: TestClient
    database_session: Session
    engine: Engine
    access_session_override: Callable[[], ActiveAccessSession]

@pytest.fixture
def recommendation_api() -> Generator[RecommendationAPI, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )
    Base.metadata.create_all(engine)

    def override_database_session() -> Generator[Session, None, None]:
        with session_factory() as database_session:
            yield database_session

    app.dependency_overrides[
        get_database_session
    ] = override_database_session

    def override_access_session() -> ActiveAccessSession:
        return ActiveAccessSession(
            profile_id=1,
            created_at=datetime.now(UTC) - timedelta(days=1),
            expires_at=datetime.now(UTC) + timedelta(days=6),
        )

    app.dependency_overrides[
        require_access_session
    ] = override_access_session

    try:
        with session_factory() as database_session:
            with TestClient(app) as client:
                yield RecommendationAPI(
                    client=client,
                    database_session=database_session,
                    engine=engine,
                    access_session_override=override_access_session,
                )
    finally:
        app.dependency_overrides.pop(get_database_session, None)
        app.dependency_overrides.pop(require_access_session, None)
        engine.dispose()

def _profile(profile_id: int = 1) -> Profile:
    return Profile(
        id=profile_id,
        steam_id=str(76561198000000000 + profile_id),
        display_name=f"Player {profile_id}",
    )

def _term_link(
    kind: str,
    igdb_id: int,
    name: str,
) -> GameIGDBMetadataTerm:
    return GameIGDBMetadataTerm(
        term=IGDBMetadataTerm(
            kind=kind,
            igdb_id=igdb_id,
            name=name,
        )
    )

def _owned_game(
    profile: Profile,
    steam_app_id: int,
    name: str,
    *,
    status: str = "ready",
    cover_image_id: str | None = None,
    playtime_minutes: int = 0,
    normal_completion_seconds: int | None = None,
    links: tuple[GameIGDBMetadataTerm, ...] = (),
) -> Game:
    game = Game(
        steam_app_id=steam_app_id,
        name=name,
        igdb_status=status,
        cover_image_id=cover_image_id,
        time_to_beat_normally_seconds=normal_completion_seconds,
    )
    game.metadata_term_links.extend(links)
    game.profile_games.append(
        ProfileGame(
            profile=profile,
            playtime_minutes=playtime_minutes,
        )
    )
    return game

def _valid_preference_body(
    steam_app_id: int = 100,
    *,
    genre_ids: list[int] | None = None,
) -> dict[str, Any]:
    return {
        "references": [
            {
                "steam_app_id": steam_app_id,
                "facets": {
                    "genre_ids": genre_ids or [10],
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

def _valid_refinement_body(
    rejected_steam_app_ids: list[object] | None = None,
) -> dict[str, Any]:
    return {
        "preference": _valid_preference_body(),
        "rejected_steam_app_ids": rejected_steam_app_ids or [],
    }

def _assert_error(
    response: Any,
    *,
    status_code: int,
    code: str,
    field: str,
    message: str,
) -> None:
    assert response.status_code == status_code
    assert response.json() == {
        "error": {
            "code": code,
            "field": field,
            "message": message,
        }
    }

def _add_recommendation_library(
    recommendation_api: RecommendationAPI,
    candidate_count: int,
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
            200 + index,
            f"Candidate {index}",
            cover_image_id=("candidate-cover" if index == 1 else None),
            playtime_minutes=index,
            normal_completion_seconds=3_600,
            links=(GameIGDBMetadataTerm(term=genre),),
        )
        for index in range(1, candidate_count + 1)
    )
    recommendation_api.database_session.add_all(
        (reference, *candidates)
    )
    recommendation_api.database_session.commit()
