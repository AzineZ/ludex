"""Load, synchronize, and present the profile behind an access session."""

from datetime import datetime
from typing import NoReturn

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.abuse.steam import (
    RateLimitExceeded,
    SteamAbuseController,
    fingerprint_subject,
    reserve_refresh,
    reserve_session_creation,
)
from app.dependencies import BudgetedSteamClient
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
from app.profiles.schemas import OwnedGameResponse, SessionProfileResponse
from app.profiles.service import sync_profile_by_steam_id
from app.sessions.rate_limits import raise_rate_limit


def load_profile_by_id(
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


def resolve_profile_for_session(
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
        raise_rate_limit(error)


def refresh_profile_or_raise(
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
        raise_rate_limit(error)


def session_profile_response(profile: Profile) -> SessionProfileResponse:
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
