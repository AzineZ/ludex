from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database import get_database_session
from app.dependencies import get_steam_client
from app.models import Profile, ProfileGame
from app.profile_schemas import (
    OwnedGameResponse,
    ProfileCreateRequest,
    ProfileDetailResponse,
    ProfileSummaryResponse,
)
from app.profile_service import sync_profile
from app.steam_client import (
    SteamAPIError,
    SteamAPIUnavailableError,
    SteamClient,
    SteamLibraryUnavailableError,
    SteamProfileNotFoundError,
)
from app.steam_identifiers import InvalidSteamIdentifierError


router = APIRouter(
    prefix="/profiles",
    tags=["profiles"],
)


@router.post(
    "",
    response_model=ProfileDetailResponse,
)
def create_profile(
    request: ProfileCreateRequest,
    database_session: Session = Depends(
        get_database_session
    ),
    steam_client: SteamClient = Depends(
        get_steam_client
    ),
) -> ProfileDetailResponse:
    """Create or re-import a profile from its Steam identifier.

    Args:
        request: The submitted Steam ID or Steam Community profile URL.
        database_session: The request-scoped database session.
        steam_client: The client used to fetch the current Steam profile.

    Returns:
        The synchronized profile and its owned-game library.

    Raises:
        HTTPException: If the identifier or Steam response cannot be processed.
    """
    profile = _sync_profile_or_raise(
        database_session,
        steam_client,
        request.identifier,
    )

    return _profile_detail_response(profile)


@router.get(
    "",
    response_model=list[ProfileSummaryResponse],
)
def list_profiles(
    database_session: Session = Depends(
        get_database_session
    ),
) -> list[ProfileSummaryResponse]:
    """List locally saved profiles in display-name order.

    Args:
        database_session: The request-scoped database session.

    Returns:
        Profile summaries without their owned-game libraries.
    """
    profiles = database_session.scalars(
        select(Profile).order_by(
            Profile.display_name,
            Profile.id,
        )
    ).all()

    return [
        _profile_summary_response(profile)
        for profile in profiles
    ]


@router.get(
    "/{profile_id}",
    response_model=ProfileDetailResponse,
)
def get_profile(
    profile_id: int,
    database_session: Session = Depends(
        get_database_session
    ),
) -> ProfileDetailResponse:
    """Return a saved profile and its cached owned-game library.

    Args:
        profile_id: The local Ludex profile identifier.
        database_session: The request-scoped database session.

    Returns:
        The cached profile and its alphabetically sorted games.

    Raises:
        HTTPException: If the local profile does not exist.
    """
    profile = database_session.scalar(
        select(Profile)
        .options(
            selectinload(Profile.owned_games).selectinload(
                ProfileGame.game
            )
        )
        .where(Profile.id == profile_id)
    )

    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found.",
        )

    return _profile_detail_response(profile)


@router.post(
    "/{profile_id}/refresh",
    response_model=ProfileDetailResponse,
)
def refresh_profile(
    profile_id: int,
    database_session: Session = Depends(
        get_database_session
    ),
    steam_client: SteamClient = Depends(
        get_steam_client
    ),
) -> ProfileDetailResponse:
    """Refresh a saved profile and library from Steam.

    The initial lookup transaction is ended before the Steam request so slow
    network work does not keep a database transaction open.

    Args:
        profile_id: The local Ludex profile identifier.
        database_session: The request-scoped database session.
        steam_client: The client used to fetch the current Steam profile.

    Returns:
        The refreshed profile and its owned-game library.

    Raises:
        HTTPException: If the profile is missing or Steam cannot be processed.
    """
    steam_id = database_session.scalar(
        select(Profile.steam_id).where(
            Profile.id == profile_id
        )
    )

    if steam_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found.",
        )

    # End the read-only transaction before making network calls.
    database_session.rollback()

    profile = _sync_profile_or_raise(
        database_session,
        steam_client,
        steam_id,
    )

    return _profile_detail_response(profile)


def _sync_profile_or_raise(
    database_session: Session,
    steam_client: SteamClient,
    identifier: str,
) -> Profile:
    """Synchronize a profile and translate domain errors into HTTP errors.

    Args:
        database_session: The session used to persist synchronized data.
        steam_client: The client used to fetch Steam data.
        identifier: A raw or previously normalized Steam identifier.

    Returns:
        The newly created or refreshed profile.

    Raises:
        HTTPException: With the API status corresponding to the domain error.
    """
    try:
        return sync_profile(
            database_session,
            steam_client,
            identifier,
        )
    except InvalidSteamIdentifierError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error
    except SteamProfileNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error
    except SteamLibraryUnavailableError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error
    except SteamAPIUnavailableError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error
    except SteamAPIError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(error),
        ) from error


def _profile_summary_response(
    profile: Profile,
) -> ProfileSummaryResponse:
    """Convert a profile model into its summary response."""
    return ProfileSummaryResponse(
        id=profile.id,
        steam_id=profile.steam_id,
        display_name=profile.display_name,
        profile_url=profile.profile_url,
        avatar_url=profile.avatar_url,
        created_at=profile.created_at,
        last_synced_at=profile.last_synced_at,
    )


def _profile_detail_response(
    profile: Profile,
) -> ProfileDetailResponse:
    """Convert a profile and its ownerships into a sorted detail response."""
    summary = _profile_summary_response(profile)

    sorted_ownerships = sorted(
        profile.owned_games,
        key=lambda ownership: (
            ownership.game.name.casefold(),
            ownership.steam_app_id,
        ),
    )

    games = [
        OwnedGameResponse(
            steam_app_id=ownership.steam_app_id,
            name=ownership.game.name,
            icon_url=ownership.game.icon_url,
            playtime_minutes=ownership.playtime_minutes,
            recent_playtime_minutes=(
                ownership.recent_playtime_minutes
            ),
            last_played_at=ownership.last_played_at,
        )
        for ownership in sorted_ownerships
    ]

    return ProfileDetailResponse(
        **summary.model_dump(),
        games=games,
    )
