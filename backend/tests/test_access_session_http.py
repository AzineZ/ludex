from collections.abc import Callable, Generator
from datetime import UTC, datetime, timedelta
from hashlib import sha256

from fastapi import Depends, FastAPI, Response
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.access_session_http import (
    ACCESS_SESSION_COOKIE_NAME,
    clear_access_session_cookie,
    get_access_session_clock,
    require_access_session,
    set_access_session_cookie,
)
from app.access_sessions import ActiveAccessSession, IssuedAccessSession
from app.database import Base, get_database_session
from app.models import Profile, SteamAccessSession


NOW = datetime(2026, 9, 2, 15, tzinfo=UTC)
EXPIRES_AT = NOW + timedelta(days=7)


def _issued_session() -> IssuedAccessSession:
    return IssuedAccessSession(
        token="raw-browser-token",
        profile_id=7,
        created_at=NOW,
        expires_at=EXPIRES_AT,
    )


def test_set_cookie_uses_fixed_local_security_contract() -> None:
    response = Response()

    set_access_session_cookie(
        response,
        _issued_session(),
        secure=False,
    )

    header = response.headers["set-cookie"]
    assert header.startswith(
        f"{ACCESS_SESSION_COOKIE_NAME}=raw-browser-token;"
    )
    assert "Domain=" not in header
    assert "expires=Wed, 09 Sep 2026 15:00:00 GMT" in header
    assert "HttpOnly" in header
    assert "Max-Age=604800" in header
    assert "Path=/" in header
    assert "SameSite=lax" in header
    assert "Secure" not in header


def test_set_cookie_is_secure_outside_local_http_development() -> None:
    response = Response()

    set_access_session_cookie(
        response,
        _issued_session(),
        secure=True,
    )

    assert "Secure" in response.headers["set-cookie"]


def test_clear_cookie_preserves_scope_and_security_attributes() -> None:
    response = Response()

    clear_access_session_cookie(response, secure=True)

    header = response.headers["set-cookie"]
    assert header.startswith(f'{ACCESS_SESSION_COOKIE_NAME}="";')
    assert "Domain=" not in header
    assert "HttpOnly" in header
    assert "Max-Age=0" in header
    assert "Path=/" in header
    assert "SameSite=lax" in header
    assert "Secure" in header


@pytest.fixture
def protected_client() -> Generator[
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

    test_app = FastAPI()

    def override_database_session() -> Generator[Session, None, None]:
        with session_factory() as database_session:
            yield database_session

    def override_clock() -> Callable[[], datetime]:
        return lambda: NOW

    @test_app.get("/protected")
    def protected(
        access_session: ActiveAccessSession = Depends(
            require_access_session
        ),
    ) -> dict[str, object]:
        return {
            "profile_id": access_session.profile_id,
            "expires_at": access_session.expires_at,
        }

    test_app.dependency_overrides[
        get_database_session
    ] = override_database_session
    test_app.dependency_overrides[get_access_session_clock] = override_clock

    try:
        with TestClient(test_app) as client:
            yield client, session_factory
    finally:
        engine.dispose()


def _store_session(
    session_factory: sessionmaker[Session],
    *,
    token_digest: bytes,
    expires_at: datetime = EXPIRES_AT,
    revoked_at: datetime | None = None,
) -> int:
    with session_factory.begin() as database_session:
        profile = Profile(
            steam_id="76561198000000000",
            display_name="Test Player",
        )
        database_session.add(profile)
        database_session.flush()
        profile_id = profile.id
        database_session.add(
            SteamAccessSession(
                token_digest=token_digest,
                profile_id=profile_id,
                created_at=NOW - timedelta(days=1),
                expires_at=expires_at,
                revoked_at=revoked_at,
            )
        )
    return profile_id


def test_dependency_resolves_valid_cookie_without_sliding_it(
    protected_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, session_factory = protected_client
    token = "valid-token"
    profile_id = _store_session(
        session_factory,
        token_digest=sha256(token.encode("ascii")).digest(),
    )
    client.cookies.set(
        ACCESS_SESSION_COOKIE_NAME,
        token,
        domain="testserver.local",
        path="/",
    )

    response = client.get("/protected")

    assert response.status_code == 200
    assert response.json() == {
        "profile_id": profile_id,
        "expires_at": "2026-09-09T15:00:00Z",
    }
    assert "set-cookie" not in response.headers


def test_dependency_returns_generic_401_when_cookie_is_missing(
    protected_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, _ = protected_client

    response = client.get("/protected")

    assert response.status_code == 401
    assert response.json() == {"detail": "Steam access session required."}
    assert "set-cookie" not in response.headers


@pytest.mark.parametrize("state", ["unknown", "expired", "revoked"])
def test_dependency_clears_presented_invalid_cookie_with_same_401(
    protected_client: tuple[TestClient, sessionmaker[Session]],
    state: str,
) -> None:
    client, session_factory = protected_client
    token = f"{state}-token"
    if state != "unknown":
        _store_session(
            session_factory,
            token_digest=sha256(token.encode("ascii")).digest(),
            expires_at=(
                NOW if state == "expired" else EXPIRES_AT
            ),
            revoked_at=(NOW if state == "revoked" else None),
        )
    client.cookies.set(
        ACCESS_SESSION_COOKIE_NAME,
        token,
        domain="testserver.local",
        path="/",
    )

    response = client.get("/protected")

    assert response.status_code == 401
    assert response.json() == {"detail": "Steam access session required."}
    header = response.headers["set-cookie"]
    assert header.startswith(f'{ACCESS_SESSION_COOKIE_NAME}="";')
    assert "Max-Age=0" in header
    assert "Path=/" in header
    assert "HttpOnly" in header
    assert ACCESS_SESSION_COOKIE_NAME not in client.cookies
