from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.abuse.steam import SteamAbuseController
from app.database import get_database_session
from app.dependencies import (
    BudgetedSteamClient,
    get_steam_client,
    get_steam_rate_limit_hmac_key,
)
from app.integrations.steam.client import SteamClient
from app.profiles.schemas import ProfileCreateRequest, SessionProfileResponse
from app.sessions.http import (
    ACCESS_SESSION_COOKIE_NAME,
    clear_access_session_cookie,
    require_access_session,
    set_access_session_cookie,
)
from app.sessions.profiles import (
    load_profile_by_id,
    refresh_profile_or_raise,
    resolve_profile_for_session,
    session_profile_response,
)
from app.sessions.rate_limits import (
    enforce_session_attempt_limit,
    get_steam_abuse_clock,
    get_steam_abuse_controller,
)
from app.sessions.service import (
    ActiveAccessSession,
    issue_access_session,
    revoke_access_session,
)


router = APIRouter(tags=["session"])


@router.post(
    "/session",
    response_model=SessionProfileResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_session(
    request_body: ProfileCreateRequest,
    request: Request,
    response: Response,
    database_session: Annotated[
        Session,
        Depends(get_database_session),
    ],
    steam_client: Annotated[
        SteamClient | BudgetedSteamClient,
        Depends(get_steam_client),
    ],
    controller: Annotated[
        SteamAbuseController,
        Depends(get_steam_abuse_controller),
    ],
    hmac_key: Annotated[
        bytes,
        Depends(get_steam_rate_limit_hmac_key),
    ],
    _attempt_limit: Annotated[
        None,
        Depends(enforce_session_attempt_limit),
    ],
) -> SessionProfileResponse:
    """Acknowledge use, then authorize this browser for one profile."""
    profile_id = resolve_profile_for_session(
        database_session,
        steam_client,
        request_body.identifier,
        controller=controller,
        hmac_key=hmac_key,
        now=get_steam_abuse_clock(),
    )
    issued_session = issue_access_session(
        database_session,
        profile_id,
        current_token=request.cookies.get(ACCESS_SESSION_COOKIE_NAME),
    )
    profile = load_profile_by_id(database_session, profile_id)
    if profile is None:
        raise RuntimeError("Issued access-session profile is missing.")

    set_access_session_cookie(response, issued_session)
    return session_profile_response(profile)


@router.get(
    "/session/profile",
    response_model=SessionProfileResponse,
)
def read_session_profile(
    access_session: Annotated[
        ActiveAccessSession,
        Depends(require_access_session),
    ],
    database_session: Annotated[
        Session,
        Depends(get_database_session),
    ],
) -> SessionProfileResponse:
    """Return the cached profile authorized by the current browser cookie."""
    profile = load_profile_by_id(
        database_session,
        access_session.profile_id,
    )
    if profile is None:
        raise RuntimeError("Authorized access-session profile is missing.")
    return session_profile_response(profile)


@router.post(
    "/session/profile/refresh",
    response_model=SessionProfileResponse,
)
def refresh_session_profile(
    request: Request,
    access_session: Annotated[
        ActiveAccessSession,
        Depends(require_access_session),
    ],
    database_session: Annotated[
        Session,
        Depends(get_database_session),
    ],
    steam_client: Annotated[
        SteamClient | BudgetedSteamClient,
        Depends(get_steam_client),
    ],
    controller: Annotated[
        SteamAbuseController,
        Depends(get_steam_abuse_controller),
    ],
    hmac_key: Annotated[
        bytes,
        Depends(get_steam_rate_limit_hmac_key),
    ],
) -> SessionProfileResponse:
    """Refresh only the profile authorized by the browser cookie."""
    profile = refresh_profile_or_raise(
        database_session,
        steam_client,
        access_session.profile_id,
        current_token=request.cookies[ACCESS_SESSION_COOKIE_NAME],
        controller=controller,
        hmac_key=hmac_key,
        now=get_steam_abuse_clock(),
    )
    return session_profile_response(profile)


@router.delete(
    "/session",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_session(
    request: Request,
    response: Response,
    _access_session: Annotated[
        ActiveAccessSession,
        Depends(require_access_session),
    ],
    database_session: Annotated[
        Session,
        Depends(get_database_session),
    ],
) -> None:
    """Revoke only the current browser session and expire its cookie."""
    token = request.cookies[ACCESS_SESSION_COOKIE_NAME]
    database_session.rollback()
    revoke_access_session(database_session, token)
    clear_access_session_cookie(response)
