from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Game, Profile, ProfileGame
from app.steam_client import SteamClient
from app.steam_identifiers import normalize_steam_identifier


def sync_profile(
    database_session: Session,
    steam_client: SteamClient,
    raw_identifier: str,
) -> Profile:
    """Import or refresh a Steam profile and its owned-game library.

    Steam data is fetched before the database transaction begins. A successful
    transaction updates profile metadata, shared games, ownerships, playtime,
    and the synchronization timestamp atomically. Ownerships missing from the
    complete Steam response are removed from this profile.

    Args:
        database_session: The session used for all persistence operations.
        steam_client: The client used to retrieve current Steam data.
        raw_identifier: A Steam ID or supported Steam Community profile URL.

    Returns:
        The newly created or refreshed profile with its owned games loaded.

    Raises:
        InvalidSteamIdentifierError: If the identifier format is unsupported.
        SteamProfileNotFoundError: If Steam cannot find the profile.
        SteamLibraryUnavailableError: If the owned library is not public.
        SteamAPIUnavailableError: If Steam cannot be reached.
        SteamAPIError: If Steam rejects the request or returns invalid data.
    """
    identifier = normalize_steam_identifier(raw_identifier)
    steam_id = steam_client.resolve_steam_id(identifier)

    return sync_profile_by_steam_id(
        database_session,
        steam_client,
        steam_id,
    )


def sync_profile_by_steam_id(
    database_session: Session,
    steam_client: SteamClient,
    steam_id: str,
) -> Profile:
    """Synchronize one already-resolved numeric Steam profile identifier."""
    steam_profile = steam_client.get_profile(steam_id)
    steam_games = steam_client.get_owned_games(steam_id)

    synced_at = datetime.now(UTC)
    imported_app_ids = {
        steam_game.steam_app_id
        for steam_game in steam_games
    }

    with database_session.begin():
        profile = database_session.scalar(
            select(Profile).where(
                Profile.steam_id == steam_profile.steam_id
            )
        )

        if profile is None:
            profile = Profile(
                steam_id=steam_profile.steam_id,
                display_name=steam_profile.display_name,
                profile_url=steam_profile.profile_url,
                avatar_url=steam_profile.avatar_url,
            )
            database_session.add(profile)
            database_session.flush()
        else:
            profile.display_name = steam_profile.display_name
            profile.profile_url = steam_profile.profile_url
            profile.avatar_url = steam_profile.avatar_url

        games_by_app_id: dict[int, Game] = {}

        if imported_app_ids:
            existing_games = database_session.scalars(
                select(Game).where(
                    Game.steam_app_id.in_(imported_app_ids)
                )
            ).all()

            games_by_app_id = {
                game.steam_app_id: game
                for game in existing_games
            }

        ownerships_by_app_id = {
            ownership.steam_app_id: ownership
            for ownership in profile.owned_games
        }

        for steam_game in steam_games:
            game = games_by_app_id.get(
                steam_game.steam_app_id
            )

            if game is None:
                game = Game(
                    steam_app_id=steam_game.steam_app_id,
                    name=steam_game.name,
                    icon_url=steam_game.icon_url,
                )
                database_session.add(game)
                games_by_app_id[game.steam_app_id] = game
            else:
                game.name = steam_game.name
                game.icon_url = steam_game.icon_url

            ownership = ownerships_by_app_id.get(
                steam_game.steam_app_id
            )

            if ownership is None:
                ownership = ProfileGame(game=game)
                profile.owned_games.append(ownership)
                ownerships_by_app_id[
                    steam_game.steam_app_id
                ] = ownership

            ownership.playtime_minutes = (
                steam_game.playtime_minutes
            )
            ownership.recent_playtime_minutes = (
                steam_game.recent_playtime_minutes
            )
            ownership.last_played_at = (
                steam_game.last_played_at
            )

        for steam_app_id, ownership in list(
            ownerships_by_app_id.items()
        ):
            if steam_app_id not in imported_app_ids:
                profile.owned_games.remove(ownership)

        profile.last_synced_at = synced_at

    return profile
