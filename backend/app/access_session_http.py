from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated, NoReturn

from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.access_sessions import (
    ACCESS_SESSION_LIFETIME,
    ActiveAccessSession,
    IssuedAccessSession,
    resolve_access_session,
)
from app.config import settings
from app.database import get_database_session


ACCESS_SESSION_COOKIE_NAME = "ludex_access_session"
ACCESS_SESSION_REQUIRED_DETAIL = "Steam access session required."

AccessSessionClock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(UTC)


def get_access_session_clock() -> AccessSessionClock:
    """Provide the request clock and a deterministic test seam."""
    return _utc_now


def _cookie_secure(secure: bool | None) -> bool:
    if secure is None:
        return settings.access_session_cookie_secure
    return secure


def set_access_session_cookie(
    response: Response,
    access_session: IssuedAccessSession,
    *,
    secure: bool | None = None,
) -> None:
    """Send one opaque access token using the fixed browser contract."""
    response.set_cookie(
        key=ACCESS_SESSION_COOKIE_NAME,
        value=access_session.token,
        max_age=int(ACCESS_SESSION_LIFETIME.total_seconds()),
        expires=access_session.expires_at,
        path="/",
        secure=_cookie_secure(secure),
        httponly=True,
        samesite="lax",
    )


def clear_access_session_cookie(
    response: Response,
    *,
    secure: bool | None = None,
) -> None:
    """Expire the access cookie with the same scope and security flags."""
    response.delete_cookie(
        key=ACCESS_SESSION_COOKIE_NAME,
        path="/",
        secure=_cookie_secure(secure),
        httponly=True,
        samesite="lax",
    )


def _cleared_cookie_header() -> str:
    response = Response()
    clear_access_session_cookie(response)
    return response.headers["set-cookie"]


def _raise_session_required(*, clear_cookie: bool) -> NoReturn:
    headers = None
    if clear_cookie:
        headers = {"Set-Cookie": _cleared_cookie_header()}
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=ACCESS_SESSION_REQUIRED_DETAIL,
        headers=headers,
    )


def require_access_session(
    request: Request,
    database_session: Annotated[
        Session,
        Depends(get_database_session),
    ],
    clock: Annotated[
        AccessSessionClock,
        Depends(get_access_session_clock),
    ],
) -> ActiveAccessSession:
    """Resolve browser authority without accepting a profile identifier."""
    token = request.cookies.get(ACCESS_SESSION_COOKIE_NAME)
    if token is None:
        _raise_session_required(clear_cookie=False)

    access_session = resolve_access_session(
        database_session,
        token,
        clock=clock,
    )
    if access_session is None:
        _raise_session_required(clear_cookie=True)

    return access_session
