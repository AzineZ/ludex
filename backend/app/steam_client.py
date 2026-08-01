from dataclasses import dataclass
from datetime import UTC, datetime
from types import TracebackType
from typing import Any, Self

import httpx

from app.steam_identifiers import SteamIdentifier


STEAM_API_BASE_URL = "https://api.steampowered.com"
STEAM_ICON_BASE_URL = (
    "https://media.steampowered.com/"
    "steamcommunity/public/images/apps"
)


class SteamAPIError(RuntimeError):
    pass


class SteamAPIUnavailableError(SteamAPIError):
    pass


class SteamProfileNotFoundError(SteamAPIError):
    pass


class SteamLibraryUnavailableError(SteamAPIError):
    pass


@dataclass(frozen=True)
class SteamProfile:
    steam_id: str
    display_name: str
    profile_url: str | None
    avatar_url: str | None


@dataclass(frozen=True)
class SteamOwnedGame:
    steam_app_id: int
    name: str
    icon_url: str | None
    playtime_minutes: int
    recent_playtime_minutes: int | None
    last_played_at: datetime | None


class SteamClient:
    def __init__(
        self,
        api_key: str,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._http_client = httpx.Client(
            base_url=STEAM_API_BASE_URL,
            timeout=10.0,
            transport=transport,
        )

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        self._http_client.close()

    def resolve_steam_id(
        self,
        identifier: SteamIdentifier,
    ) -> str:
        if identifier.kind == "steam_id":
            return identifier.value

        payload = self._get(
            "/ISteamUser/ResolveVanityURL/v1/",
            {
                "vanityurl": identifier.value,
                "url_type": 1,
            },
        )
        response = self._response_object(payload)

        if response.get("success") != 1:
            raise SteamProfileNotFoundError(
                "The Steam profile could not be found."
            )

        steam_id = response.get("steamid")
        if not isinstance(steam_id, str):
            raise SteamAPIError(
                "Steam returned an unexpected vanity URL response."
            )

        return steam_id

    def get_profile(self, steam_id: str) -> SteamProfile:
        payload = self._get(
            "/ISteamUser/GetPlayerSummaries/v2/",
            {"steamids": steam_id},
        )
        response = self._response_object(payload)
        players = response.get("players")

        if not isinstance(players, list) or not players:
            raise SteamProfileNotFoundError(
                "The Steam profile could not be found."
            )

        player = players[0]
        if not isinstance(player, dict):
            raise SteamAPIError(
                "Steam returned an unexpected profile response."
            )

        returned_steam_id = player.get("steamid")
        display_name = player.get("personaname")

        if not isinstance(returned_steam_id, str):
            raise SteamAPIError(
                "Steam returned an invalid profile identifier."
            )

        if not isinstance(display_name, str):
            raise SteamAPIError(
                "Steam returned an invalid profile name."
            )

        return SteamProfile(
            steam_id=returned_steam_id,
            display_name=display_name,
            profile_url=self._optional_string(
                player.get("profileurl")
            ),
            avatar_url=self._optional_string(
                player.get("avatarfull")
            ),
        )

    def get_owned_games(
        self,
        steam_id: str,
    ) -> list[SteamOwnedGame]:
        payload = self._get(
            "/IPlayerService/GetOwnedGames/v1/",
            {
                "steamid": steam_id,
                "include_appinfo": "true",
                "include_played_free_games": "true",
            },
        )
        response = self._response_object(payload)

        if "game_count" not in response:
            raise SteamLibraryUnavailableError(
                "This Steam library is private or unavailable."
            )

        games = response.get("games", [])
        if not isinstance(games, list):
            raise SteamAPIError(
                "Steam returned an unexpected library response."
            )

        return [
            self._parse_owned_game(game)
            for game in games
        ]

    def _get(
        self,
        path: str,
        params: dict[str, object],
    ) -> dict[str, Any]:
        request_params = {
            "key": self._api_key,
            "format": "json",
            **params,
        }

        try:
            response = self._http_client.get(
                path,
                params=request_params,
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.RequestError:
            raise SteamAPIUnavailableError(
                "Steam is currently unavailable."
            ) from None
        except httpx.HTTPStatusError:
            raise SteamAPIError(
                "Steam rejected the API request."
            ) from None
        except ValueError:
            raise SteamAPIError(
                "Steam returned invalid response data."
            ) from None

        if not isinstance(payload, dict):
            raise SteamAPIError(
                "Steam returned invalid response data."
            )

        return payload

    @staticmethod
    def _response_object(
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        response = payload.get("response")

        if not isinstance(response, dict):
            raise SteamAPIError(
                "Steam returned an unexpected response."
            )

        return response

    @staticmethod
    def _parse_owned_game(
        game: object,
    ) -> SteamOwnedGame:
        if not isinstance(game, dict):
            raise SteamAPIError(
                "Steam returned an invalid game entry."
            )

        steam_app_id = SteamClient._nonnegative_integer(
            game.get("appid"),
            "Steam App ID",
        )
        name = game.get("name")

        if not isinstance(name, str):
            raise SteamAPIError(
                "Steam returned an invalid game name."
            )

        icon_hash = SteamClient._optional_string(
            game.get("img_icon_url")
        )
        icon_url = None

        if icon_hash:
            icon_url = (
                f"{STEAM_ICON_BASE_URL}/"
                f"{steam_app_id}/{icon_hash}.jpg"
            )

        return SteamOwnedGame(
            steam_app_id=steam_app_id,
            name=name,
            icon_url=icon_url,
            playtime_minutes=SteamClient._nonnegative_integer(
                game.get("playtime_forever", 0),
                "total playtime",
            ),
            recent_playtime_minutes=(
                SteamClient._optional_nonnegative_integer(
                    game.get("playtime_2weeks"),
                    "recent playtime",
                )
            ),
            last_played_at=SteamClient._optional_timestamp(
                game.get("rtime_last_played")
            ),
        )

    @staticmethod
    def _nonnegative_integer(
        value: object,
        field_name: str,
    ) -> int:
        if (
            not isinstance(value, int)
            or isinstance(value, bool)
            or value < 0
        ):
            raise SteamAPIError(
                f"Steam returned an invalid {field_name}."
            )

        return value

    @staticmethod
    def _optional_nonnegative_integer(
        value: object,
        field_name: str,
    ) -> int | None:
        if value is None:
            return None

        return SteamClient._nonnegative_integer(
            value,
            field_name,
        )

    @staticmethod
    def _optional_timestamp(
        value: object,
    ) -> datetime | None:
        if value is None or value == 0:
            return None

        timestamp = SteamClient._nonnegative_integer(
            value,
            "last-played timestamp",
        )

        try:
            return datetime.fromtimestamp(timestamp, tz=UTC)
        except (OverflowError, OSError, ValueError):
            raise SteamAPIError(
                "Steam returned an invalid last-played timestamp."
            ) from None

    @staticmethod
    def _optional_string(value: object) -> str | None:
        return value if isinstance(value, str) and value else None
