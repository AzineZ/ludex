from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database import get_database_session
from app.dependencies import get_steam_client
from app.integrations.igdb.images import igdb_cover_url
from app.integrations.steam.client import (
    SteamAPIError,
    SteamAPIUnavailableError,
    SteamClient,
    SteamLibraryUnavailableError,
    SteamProfileNotFoundError,
)
from app.integrations.steam.identifiers import (
    InvalidSteamIdentifierError,
    normalize_steam_identifier,
)
from app.models import Profile, ProfileGame
from app.profiles.schemas import (
    OwnedGameResponse,
    ProfileCreateRequest,
    SessionProfileResponse,
)
from app.profiles.service import sync_profile_by_steam_id
from app.sessions.http import (
    ACCESS_SESSION_COOKIE_NAME,
    clear_access_session_cookie,
    require_access_session,
    set_access_session_cookie,
)
from app.sessions.service import (
    ActiveAccessSession,
    issue_access_session,
    revoke_access_session,
)


router = APIRouter(tags=["session"])


def _load_profile_by_id(
    database_session: Session,
    profile_id: int,
) -> Profile | None:
    return database_session.scalar(
        select(Profile)
        .options(
            selectinload(Profile.owned_games).selectinload(
                ProfileGame.game
            )
        )
        .where(Profile.id == profile_id)
    )


def _load_profile_by_steam_id(
    database_session: Session,
    steam_id: str,
) -> Profile | None:
    return database_session.scalar(
        select(Profile).where(Profile.steam_id == steam_id)
    )


def _raise_profile_error(error: Exception) -> NoReturn:
    if isinstance(error, InvalidSteamIdentifierError):
        error_status = status.HTTP_422_UNPROCESSABLE_CONTENT
    elif isinstance(error, SteamProfileNotFoundError):
        error_status = status.HTTP_404_NOT_FOUND
    elif isinstance(error, SteamLibraryUnavailableError):
        error_status = status.HTTP_422_UNPROCESSABLE_CONTENT
    elif isinstance(error, SteamAPIUnavailableError):
        error_status = status.HTTP_503_SERVICE_UNAVAILABLE
    else:
        error_status = status.HTTP_502_BAD_GATEWAY

    raise HTTPException(
        status_code=error_status,
        detail=str(error),
    ) from error


def _resolve_profile_for_session(
    database_session: Session,
    steam_client: SteamClient,
    raw_identifier: str,
) -> int:
    try:
        identifier = normalize_steam_identifier(raw_identifier)
        if identifier.kind == "steam_id":
            steam_id = identifier.value
        else:
            steam_id = steam_client.resolve_steam_id(identifier)

        cached_profile = _load_profile_by_steam_id(
            database_session,
            steam_id,
        )
        if cached_profile is not None:
            profile_id = cached_profile.id
            database_session.rollback()
            return profile_id

        database_session.rollback()
        profile = sync_profile_by_steam_id(
            database_session,
            steam_client,
            steam_id,
        )
        profile_id = profile.id
        database_session.rollback()
        return profile_id
    except (
        InvalidSteamIdentifierError,
        SteamAPIError,
    ) as error:
        database_session.rollback()
        _raise_profile_error(error)


def _refresh_profile_or_raise(
    database_session: Session,
    steam_client: SteamClient,
    profile_id: int,
) -> Profile:
    steam_id = database_session.scalar(
        select(Profile.steam_id).where(Profile.id == profile_id)
    )
    if steam_id is None:
        database_session.rollback()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Steam access session required.",
        )

    database_session.rollback()
    try:
        return sync_profile_by_steam_id(
            database_session,
            steam_client,
            steam_id,
        )
    except SteamAPIError as error:
        _raise_profile_error(error)


def _session_profile_response(profile: Profile) -> SessionProfileResponse:
    sorted_ownerships = sorted(
        profile.owned_games,
        key=lambda ownership: (
            ownership.game.name.casefold(),
            ownership.steam_app_id,
        ),
    )
    return SessionProfileResponse(
        steam_id=profile.steam_id,
        display_name=profile.display_name,
        profile_url=profile.profile_url,
        avatar_url=profile.avatar_url,
        created_at=profile.created_at,
        last_synced_at=profile.last_synced_at,
        games=[
            OwnedGameResponse(
                steam_app_id=ownership.steam_app_id,
                name=ownership.game.name,
                icon_url=ownership.game.icon_url,
                cover_url=igdb_cover_url(
                    ownership.game.cover_image_id
                ),
                playtime_minutes=ownership.playtime_minutes,
                recent_playtime_minutes=(
                    ownership.recent_playtime_minutes
                ),
                last_played_at=ownership.last_played_at,
            )
            for ownership in sorted_ownerships
        ],
    )


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
        SteamClient,
        Depends(get_steam_client),
    ],
) -> SessionProfileResponse:
    """Reuse or import one profile and authorize this browser to access it."""
    profile_id = _resolve_profile_for_session(
        database_session,
        steam_client,
        request_body.identifier,
    )
    issued_session = issue_access_session(
        database_session,
        profile_id,
        current_token=request.cookies.get(ACCESS_SESSION_COOKIE_NAME),
    )
    profile = _load_profile_by_id(database_session, profile_id)
    if profile is None:
        raise RuntimeError("Issued access-session profile is missing.")

    set_access_session_cookie(response, issued_session)
    return _session_profile_response(profile)


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
    profile = _load_profile_by_id(
        database_session,
        access_session.profile_id,
    )
    if profile is None:
        raise RuntimeError("Authorized access-session profile is missing.")
    return _session_profile_response(profile)


@router.post(
    "/session/profile/refresh",
    response_model=SessionProfileResponse,
)
def refresh_session_profile(
    access_session: Annotated[
        ActiveAccessSession,
        Depends(require_access_session),
    ],
    database_session: Annotated[
        Session,
        Depends(get_database_session),
    ],
    steam_client: Annotated[
        SteamClient,
        Depends(get_steam_client),
    ],
) -> SessionProfileResponse:
    """Refresh only the profile authorized by the browser cookie."""
    profile = _refresh_profile_or_raise(
        database_session,
        steam_client,
        access_session.profile_id,
    )
    return _session_profile_response(profile)


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
