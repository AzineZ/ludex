from datetime import UTC, datetime
from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database import get_database_session
from app.dependencies import (
    BudgetedSteamClient,
    get_steam_client,
    get_steam_rate_limit_hmac_key,
)
from app.abuse.steam import (
    RateLimitExceeded,
    SteamAbuseController,
    fingerprint_subject,
    reserve_refresh,
    reserve_session_creation,
    resolve_client_address,
)
from app.config import settings
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
_STEAM_ABUSE_CONTROLLER = SteamAbuseController()


def get_steam_abuse_controller() -> SteamAbuseController:
    """Provide bounded process-local abuse state and a test seam."""
    return _STEAM_ABUSE_CONTROLLER


def get_steam_abuse_clock() -> datetime:
    """Provide one replaceable UTC clock for request-level controls."""
    return datetime.now(UTC)


def _raise_rate_limit(error: RateLimitExceeded) -> NoReturn:
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Too many Steam requests. Try again later.",
        headers={"Retry-After": str(error.retry_after)},
    ) from error


def enforce_session_attempt_limit(
    request: Request,
    controller: Annotated[
        SteamAbuseController,
        Depends(get_steam_abuse_controller),
    ],
) -> None:
    """Count every session-creation attempt using memory-only client state."""
    try:
        client_address = resolve_client_address(
            deployment_environment=settings.deployment_environment,
            socket_host=(request.client.host if request.client else None),
            forwarded_for=request.headers.get("x-forwarded-for"),
        )
        controller.record_session_attempt(
            client_address,
            now=get_steam_abuse_clock(),
        )
    except (RateLimitExceeded, ValueError) as error:
        if isinstance(error, RateLimitExceeded):
            _raise_rate_limit(error)
        _raise_rate_limit(RateLimitExceeded(60))


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
    steam_client: SteamClient | BudgetedSteamClient,
    raw_identifier: str,
    *,
    controller: SteamAbuseController,
    hmac_key: bytes,
    now: datetime,
) -> int:
    try:
        identifier = normalize_steam_identifier(raw_identifier)
        if identifier.kind == "steam_id":
            steam_id = identifier.value
            cached_profile = _load_profile_by_steam_id(
                database_session,
                steam_id,
            )
            if cached_profile is not None:
                profile_id = cached_profile.id
                database_session.rollback()
                return profile_id
            database_session.rollback()
        else:
            database_session.rollback()

        identifier_digest = fingerprint_subject(
            hmac_key,
            "identifier",
            f"{identifier.kind}:{identifier.value}",
        )
        reserve_session_creation(
            database_session,
            identifier_digest,
            now=now,
        )

        if identifier.kind != "steam_id":
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

        with controller.steam_sync(steam_id):
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
    except RateLimitExceeded as error:
        database_session.rollback()
        _raise_rate_limit(error)


def _refresh_profile_or_raise(
    database_session: Session,
    steam_client: SteamClient | BudgetedSteamClient,
    profile_id: int,
    *,
    current_token: str,
    controller: SteamAbuseController,
    hmac_key: bytes,
    now: datetime,
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
        refresh_digest = fingerprint_subject(
            hmac_key,
            "refresh",
            f"{current_token}\0{steam_id}",
        )
        reserve_refresh(database_session, refresh_digest, now=now)
        with controller.steam_sync(steam_id):
            return sync_profile_by_steam_id(
                database_session,
                steam_client,
                steam_id,
            )
    except SteamAPIError as error:
        _raise_profile_error(error)
    except RateLimitExceeded as error:
        database_session.rollback()
        _raise_rate_limit(error)


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
    """Reuse or import one profile and authorize this browser to access it."""
    profile_id = _resolve_profile_for_session(
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
    profile = _refresh_profile_or_raise(
        database_session,
        steam_client,
        access_session.profile_id,
        current_token=request.cookies[ACCESS_SESSION_COOKIE_NAME],
        controller=controller,
        hmac_key=hmac_key,
        now=get_steam_abuse_clock(),
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
