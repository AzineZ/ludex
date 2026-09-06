from collections.abc import Generator
from hashlib import sha256
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.sessions.routes as session_routes_module
from app.sessions.http import ACCESS_SESSION_COOKIE_NAME
from app.sessions.routes import get_steam_abuse_controller
from app.sessions.service import IssuedAccessSession, issue_access_session
from app.abuse.steam import SteamAbuseController
from app.database import Base, get_database_session
from app.dependencies import get_steam_client
from app.main import app
from app.models import (
    Game,
    Profile,
    ProfileGame,
    SteamAccessSession,
    SteamUsageEvent,
)
from app.integrations.steam.client import (
    SteamAPIError,
    SteamAPIUnavailableError,
    SteamClient,
    SteamLibraryUnavailableError,
    SteamOwnedGame,
    SteamProfile,
)


FIRST_STEAM_ID = "76561198000000000"
SECOND_STEAM_ID = "76561198000000001"


@pytest.fixture
def session_api(
    steam_client: MagicMock,
) -> Generator[
    tuple[TestClient, sessionmaker[Session]],
    None,
    None,
]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    abuse_controller = SteamAbuseController()

    def override_database_session() -> Generator[Session, None, None]:
        with session_factory() as database_session:
            yield database_session

    def override_steam_client() -> SteamClient:
        return steam_client

    app.dependency_overrides[
        get_database_session
    ] = override_database_session
    app.dependency_overrides[get_steam_client] = override_steam_client
    app.dependency_overrides[
        get_steam_abuse_controller
    ] = lambda: abuse_controller

    try:
        with TestClient(app) as client:
            yield client, session_factory
    finally:
        app.dependency_overrides.pop(get_database_session, None)
        app.dependency_overrides.pop(get_steam_client, None)
        app.dependency_overrides.pop(get_steam_abuse_controller, None)
        engine.dispose()


def _store_cached_profile(
    session_factory: sessionmaker[Session],
    *,
    steam_id: str = FIRST_STEAM_ID,
    display_name: str = "Cached Player",
    cover_image_id: str | None = None,
) -> int:
    with session_factory.begin() as database_session:
        profile = Profile(
            steam_id=steam_id,
            display_name=display_name,
            profile_url=f"https://steamcommunity.com/profiles/{steam_id}/",
            avatar_url="https://example.com/cached-avatar.jpg",
        )
        game = Game(
            steam_app_id=int(steam_id[-2:]) + 10,
            name=f"{display_name} Game",
            icon_url=None,
            cover_image_id=cover_image_id,
        )
        profile.owned_games.append(
            ProfileGame(
                game=game,
                playtime_minutes=90,
                recent_playtime_minutes=15,
            )
        )
        database_session.add(profile)
        database_session.flush()
        return profile.id


def _configure_import(steam_client: MagicMock) -> None:
    steam_client.resolve_steam_id.return_value = FIRST_STEAM_ID
    steam_client.get_profile.return_value = SteamProfile(
        steam_id=FIRST_STEAM_ID,
        display_name="Imported Player",
        profile_url=(
            f"https://steamcommunity.com/profiles/{FIRST_STEAM_ID}/"
        ),
        avatar_url="https://example.com/imported-avatar.jpg",
    )
    steam_client.get_owned_games.return_value = [
        SteamOwnedGame(
            steam_app_id=20,
            name="Imported Game",
            icon_url=None,
            playtime_minutes=120,
            recent_playtime_minutes=30,
            last_played_at=None,
        )
    ]


def test_create_session_reuses_cached_numeric_profile_without_provider_calls(
    session_api: tuple[TestClient, sessionmaker[Session]],
    steam_client: MagicMock,
) -> None:
    client, session_factory = session_api
    _store_cached_profile(
        session_factory,
        cover_image_id="cached-cover",
    )

    response = client.post(
        "/session",
        json={"identifier": FIRST_STEAM_ID},
    )

    assert response.status_code == 201
    assert response.json()["steam_id"] == FIRST_STEAM_ID
    assert response.json()["display_name"] == "Cached Player"
    assert "id" not in response.json()
    assert response.json()["games"][0]["name"] == "Cached Player Game"
    assert response.json()["games"][0]["cover_url"] == (
        "https://images.igdb.com/igdb/image/upload/"
        "t_cover_big/cached-cover.jpg"
    )
    assert ACCESS_SESSION_COOKIE_NAME in client.cookies
    steam_client.resolve_steam_id.assert_not_called()
    steam_client.get_profile.assert_not_called()
    steam_client.get_owned_games.assert_not_called()

    with session_factory() as database_session:
        assert len(database_session.scalars(select(SteamAccessSession)).all()) == 1
        assert database_session.scalars(select(SteamUsageEvent)).all() == []


def test_uncached_numeric_session_reserves_provider_operation(
    session_api: tuple[TestClient, sessionmaker[Session]],
    steam_client: MagicMock,
) -> None:
    client, session_factory = session_api
    _configure_import(steam_client)

    response = client.post("/session", json={"identifier": FIRST_STEAM_ID})

    assert response.status_code == 201
    with session_factory() as database_session:
        events = database_session.scalars(select(SteamUsageEvent)).all()
        assert [event.category for event in events] == ["session_create"]
        assert len(events[0].subject_digest) == 32
        assert FIRST_STEAM_ID.encode("ascii") not in events[0].subject_digest


def test_create_session_resolves_vanity_then_reuses_cached_profile(
    session_api: tuple[TestClient, sessionmaker[Session]],
    steam_client: MagicMock,
) -> None:
    client, session_factory = session_api
    _store_cached_profile(session_factory)
    steam_client.resolve_steam_id.return_value = FIRST_STEAM_ID

    response = client.post(
        "/session",
        json={
            "identifier": "https://steamcommunity.com/id/cached-player"
        },
    )

    assert response.status_code == 201
    steam_client.resolve_steam_id.assert_called_once()
    steam_client.get_profile.assert_not_called()
    steam_client.get_owned_games.assert_not_called()

    with session_factory() as database_session:
        assert [
            event.category
            for event in database_session.scalars(select(SteamUsageEvent))
        ] == ["session_create"]


def test_sixth_session_attempt_is_generic_rate_limit_before_provider(
    session_api: tuple[TestClient, sessionmaker[Session]],
    steam_client: MagicMock,
) -> None:
    client, _ = session_api

    for index in range(5):
        response = client.post(
            "/session",
            json={"identifier": f"invalid identifier {index}"},
        )
        assert response.status_code == 422

    limited = client.post(
        "/session",
        json={"identifier": FIRST_STEAM_ID},
    )

    assert limited.status_code == 429
    assert limited.json() == {
        "detail": "Too many Steam requests. Try again later."
    }
    assert 1 <= int(limited.headers["retry-after"]) <= 600
    steam_client.resolve_steam_id.assert_not_called()
    steam_client.get_profile.assert_not_called()
    steam_client.get_owned_games.assert_not_called()


def test_create_session_imports_uncached_profile_and_sets_cookie(
    session_api: tuple[TestClient, sessionmaker[Session]],
    steam_client: MagicMock,
) -> None:
    client, _ = session_api
    _configure_import(steam_client)

    response = client.post(
        "/session",
        json={"identifier": FIRST_STEAM_ID},
    )

    assert response.status_code == 201
    assert response.json()["display_name"] == "Imported Player"
    assert "id" not in response.json()
    assert response.json()["games"][0]["name"] == "Imported Game"
    assert response.json()["games"][0]["cover_url"] is None
    assert response.headers["set-cookie"].startswith(
        f"{ACCESS_SESSION_COOKIE_NAME}="
    )
    steam_client.get_profile.assert_called_once_with(FIRST_STEAM_ID)
    steam_client.get_owned_games.assert_called_once_with(FIRST_STEAM_ID)


def test_failed_session_creation_preserves_current_session(
    session_api: tuple[TestClient, sessionmaker[Session]],
    steam_client: MagicMock,
) -> None:
    client, session_factory = session_api
    _store_cached_profile(session_factory)
    first = client.post(
        "/session",
        json={"identifier": FIRST_STEAM_ID},
    )
    assert first.status_code == 201
    current_token = client.cookies[ACCESS_SESSION_COOKIE_NAME]
    steam_client.resolve_steam_id.side_effect = SteamAPIUnavailableError(
        "Steam is currently unavailable."
    )

    failed = client.post(
        "/session",
        json={"identifier": "https://steamcommunity.com/id/unavailable"},
    )

    assert failed.status_code == 503
    assert client.cookies[ACCESS_SESSION_COOKIE_NAME] == current_token
    assert "set-cookie" not in failed.headers
    with session_factory() as database_session:
        stored = database_session.scalar(
            select(SteamAccessSession).where(
                SteamAccessSession.token_digest
                == sha256(current_token.encode("utf-8")).digest()
            )
        )
        assert stored is not None
        assert stored.revoked_at is None


def test_successful_session_replacement_revokes_only_current_cookie(
    session_api: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, session_factory = session_api
    _store_cached_profile(session_factory)
    _store_cached_profile(
        session_factory,
        steam_id=SECOND_STEAM_ID,
        display_name="Second Player",
    )
    first = client.post(
        "/session",
        json={"identifier": FIRST_STEAM_ID},
    )
    assert first.status_code == 201
    first_token = client.cookies[ACCESS_SESSION_COOKIE_NAME]

    second = client.post(
        "/session",
        json={"identifier": SECOND_STEAM_ID},
    )

    assert second.status_code == 201
    second_token = client.cookies[ACCESS_SESSION_COOKIE_NAME]
    assert second_token != first_token
    assert second.json()["steam_id"] == SECOND_STEAM_ID
    with session_factory() as database_session:
        stored = database_session.scalars(
            select(SteamAccessSession).order_by(SteamAccessSession.id)
        ).all()
        assert len(stored) == 2
        assert stored[0].revoked_at is not None
        assert stored[1].revoked_at is None


def test_failed_session_replacement_write_preserves_current_session(
    session_api: tuple[TestClient, sessionmaker[Session]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, session_factory = session_api
    first_profile_id = _store_cached_profile(session_factory)
    second_profile_id = _store_cached_profile(
        session_factory,
        steam_id=SECOND_STEAM_ID,
        display_name="Second Player",
    )
    assert client.post(
        "/session",
        json={"identifier": FIRST_STEAM_ID},
    ).status_code == 201
    current_token = client.cookies[ACCESS_SESSION_COOKIE_NAME]

    with session_factory() as database_session:
        issue_access_session(
            database_session,
            second_profile_id,
            token_generator=lambda: "collision-token",
        )

    def issue_colliding_replacement(
        database_session: Session,
        profile_id: int,
        *,
        current_token: str | None = None,
    ) -> IssuedAccessSession:
        return issue_access_session(
            database_session,
            profile_id,
            current_token=current_token,
            token_generator=lambda: "collision-token",
        )

    monkeypatch.setattr(
        session_routes_module,
        "issue_access_session",
        issue_colliding_replacement,
    )

    response = client.post(
        "/session",
        json={"identifier": SECOND_STEAM_ID},
    )

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Ludex is temporarily unavailable."
    }
    assert "set-cookie" not in response.headers
    assert client.cookies[ACCESS_SESSION_COOKIE_NAME] == current_token
    with session_factory() as database_session:
        current_session = database_session.scalar(
            select(SteamAccessSession).where(
                SteamAccessSession.token_digest
                == sha256(current_token.encode("utf-8")).digest()
            )
        )
        assert current_session is not None
        assert current_session.profile_id == first_profile_id
        assert current_session.revoked_at is None

    assert client.get("/session/profile").status_code == 200


def test_current_profile_uses_cookie_and_never_returns_internal_id(
    session_api: tuple[TestClient, sessionmaker[Session]],
    steam_client: MagicMock,
) -> None:
    client, session_factory = session_api
    _store_cached_profile(session_factory)
    assert client.post(
        "/session",
        json={"identifier": FIRST_STEAM_ID},
    ).status_code == 201
    steam_client.reset_mock()

    response = client.get("/session/profile")

    assert response.status_code == 200
    assert response.json()["steam_id"] == FIRST_STEAM_ID
    assert "id" not in response.json()
    assert "set-cookie" not in response.headers
    steam_client.resolve_steam_id.assert_not_called()
    steam_client.get_profile.assert_not_called()
    steam_client.get_owned_games.assert_not_called()


def test_current_profile_requires_session_cookie(
    session_api: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, _ = session_api

    response = client.get("/session/profile")

    assert response.status_code == 401
    assert response.json() == {
        "detail": "Steam access session required."
    }


def test_current_profile_sanitizes_database_unavailability(
    session_api: tuple[TestClient, sessionmaker[Session]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, session_factory = session_api
    _store_cached_profile(session_factory)
    assert client.post(
        "/session",
        json={"identifier": FIRST_STEAM_ID},
    ).status_code == 201
    current_token = client.cookies[ACCESS_SESSION_COOKIE_NAME]

    def fail_profile_read(*_: object, **__: object) -> None:
        raise OperationalError(
            "SELECT secret_column FROM private_table",
            {"password": "do-not-expose"},
            RuntimeError("database host is private.internal"),
        )

    monkeypatch.setattr(
        session_routes_module,
        "_load_profile_by_id",
        fail_profile_read,
    )

    with TestClient(app, raise_server_exceptions=False) as failure_client:
        failure_client.cookies.set(
            ACCESS_SESSION_COOKIE_NAME,
            current_token,
            domain="testserver.local",
            path="/",
        )
        response = failure_client.get("/session/profile")

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Ludex is temporarily unavailable."
    }
    assert "secret_column" not in response.text
    assert "do-not-expose" not in response.text
    assert "private.internal" not in response.text
    assert failure_client.cookies[ACCESS_SESSION_COOKIE_NAME] == current_token


def test_refresh_updates_only_session_profile_without_renewing_cookie(
    session_api: tuple[TestClient, sessionmaker[Session]],
    steam_client: MagicMock,
) -> None:
    client, session_factory = session_api
    _store_cached_profile(session_factory)
    assert client.post(
        "/session",
        json={"identifier": FIRST_STEAM_ID},
    ).status_code == 201
    current_token = client.cookies[ACCESS_SESSION_COOKIE_NAME]
    _configure_import(steam_client)

    response = client.post("/session/profile/refresh")

    assert response.status_code == 200
    assert response.json()["display_name"] == "Imported Player"
    assert "id" not in response.json()
    assert "set-cookie" not in response.headers
    assert client.cookies[ACCESS_SESSION_COOKIE_NAME] == current_token
    steam_client.get_profile.assert_called_once_with(FIRST_STEAM_ID)
    steam_client.get_owned_games.assert_called_once_with(FIRST_STEAM_ID)

    with session_factory() as database_session:
        assert [
            event.category
            for event in database_session.scalars(select(SteamUsageEvent))
        ] == ["refresh"]


def test_refresh_cooldown_returns_429_without_second_provider_call(
    session_api: tuple[TestClient, sessionmaker[Session]],
    steam_client: MagicMock,
) -> None:
    client, session_factory = session_api
    _store_cached_profile(session_factory)
    assert client.post(
        "/session",
        json={"identifier": FIRST_STEAM_ID},
    ).status_code == 201
    _configure_import(steam_client)
    assert client.post("/session/profile/refresh").status_code == 200
    steam_client.reset_mock()

    limited = client.post("/session/profile/refresh")

    assert limited.status_code == 429
    assert limited.json() == {
        "detail": "Too many Steam requests. Try again later."
    }
    assert 1 <= int(limited.headers["retry-after"]) <= 900
    steam_client.get_profile.assert_not_called()
    steam_client.get_owned_games.assert_not_called()


@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (
            SteamLibraryUnavailableError(
                "This Steam library is private or unavailable."
            ),
            422,
        ),
        (
            SteamAPIUnavailableError(
                "Steam is currently unavailable."
            ),
            503,
        ),
        (
            SteamAPIError("Steam returned invalid response data."),
            502,
        ),
    ],
)
def test_failed_refresh_preserves_cached_profile_and_session(
    session_api: tuple[TestClient, sessionmaker[Session]],
    steam_client: MagicMock,
    error: SteamAPIError,
    expected_status: int,
) -> None:
    client, session_factory = session_api
    _store_cached_profile(session_factory)
    assert client.post(
        "/session",
        json={"identifier": FIRST_STEAM_ID},
    ).status_code == 201
    current_token = client.cookies[ACCESS_SESSION_COOKIE_NAME]
    steam_client.get_profile.return_value = SteamProfile(
        steam_id=FIRST_STEAM_ID,
        display_name="Uncommitted Name",
        profile_url=None,
        avatar_url=None,
    )
    steam_client.get_owned_games.side_effect = error

    response = client.post("/session/profile/refresh")

    assert response.status_code == expected_status
    assert response.json() == {"detail": str(error)}
    assert "set-cookie" not in response.headers
    assert client.cookies[ACCESS_SESSION_COOKIE_NAME] == current_token

    cached = client.get("/session/profile")
    assert cached.status_code == 200
    assert cached.json()["display_name"] == "Cached Player"
    assert [game["name"] for game in cached.json()["games"]] == [
        "Cached Player Game"
    ]

    with session_factory() as database_session:
        stored = database_session.scalar(
            select(SteamAccessSession).where(
                SteamAccessSession.token_digest
                == sha256(current_token.encode("utf-8")).digest()
            )
        )
        assert stored is not None
        assert stored.revoked_at is None


def test_delete_session_revokes_cookie_and_returns_to_unauthorized_state(
    session_api: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, session_factory = session_api
    _store_cached_profile(session_factory)
    assert client.post(
        "/session",
        json={"identifier": FIRST_STEAM_ID},
    ).status_code == 201

    response = client.delete("/session")

    assert response.status_code == 204
    assert response.content == b""
    assert ACCESS_SESSION_COOKIE_NAME not in client.cookies
    assert client.get("/session/profile").status_code == 401
    with session_factory() as database_session:
        stored = database_session.scalar(select(SteamAccessSession))
        assert stored is not None
        assert stored.revoked_at is not None


def test_failed_session_revocation_write_preserves_current_session(
    session_api: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, session_factory = session_api
    _store_cached_profile(session_factory)
    assert client.post(
        "/session",
        json={"identifier": FIRST_STEAM_ID},
    ).status_code == 201
    current_token = client.cookies[ACCESS_SESSION_COOKIE_NAME]

    with session_factory() as database_session:
        engine = database_session.get_bind()

    def fail_revocation(_, __, statement, ___, ____, _____) -> None:
        if statement.lstrip().upper().startswith(
            "UPDATE STEAM_ACCESS_SESSIONS"
        ):
            raise OperationalError(
                statement,
                {},
                RuntimeError("simulated revocation failure"),
            )

    event.listen(engine, "before_cursor_execute", fail_revocation)
    try:
        response = client.delete("/session")
    finally:
        event.remove(engine, "before_cursor_execute", fail_revocation)

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Ludex is temporarily unavailable."
    }
    assert "set-cookie" not in response.headers
    assert client.cookies[ACCESS_SESSION_COOKIE_NAME] == current_token
    with session_factory() as database_session:
        stored = database_session.scalar(
            select(SteamAccessSession).where(
                SteamAccessSession.token_digest
                == sha256(current_token.encode("utf-8")).digest()
            )
        )
        assert stored is not None
        assert stored.revoked_at is None

    assert client.get("/session/profile").status_code == 200
