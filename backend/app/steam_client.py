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
    """Indicate that Steam rejected a request or returned invalid data."""

    pass


class SteamAPIUnavailableError(SteamAPIError):
    """Indicate that a Steam request failed at the network layer."""

    pass


class SteamProfileNotFoundError(SteamAPIError):
    """Indicate that Steam could not resolve or find a profile."""

    pass


class SteamLibraryUnavailableError(SteamAPIError):
    """Indicate that an owned-game library is private or unavailable."""

    pass


@dataclass(frozen=True)
class SteamProfile:
    """Represent normalized profile metadata returned by Steam."""

    steam_id: str
    display_name: str
    profile_url: str | None
    avatar_url: str | None


@dataclass(frozen=True)
class SteamOwnedGame:
    """Represent one normalized owned-game record returned by Steam."""

    steam_app_id: int
    name: str
    icon_url: str | None
    playtime_minutes: int
    recent_playtime_minutes: int | None
    last_played_at: datetime | None


class SteamClient:
    """Retrieve and validate profile and library data from the Steam Web API."""

    def __init__(
        self,
        api_key: str,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        """Initialize a synchronous Steam Web API client.

        Args:
            api_key: The private Steam Web API key added to every request.
            transport: An optional HTTPX transport, primarily for isolated
                tests.
        """
        self._api_key = api_key
        self._http_client = httpx.Client(
            base_url=STEAM_API_BASE_URL,
            timeout=10.0,
            transport=transport,
        )

    def __enter__(self) -> Self:
        """Enter a context and return this client."""
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Exit a context and release the underlying HTTP connection."""
        self.close()

    def close(self) -> None:
        """Close the underlying HTTP client and its network resources."""
        self._http_client.close()

    def resolve_steam_id(
        self,
        identifier: SteamIdentifier,
    ) -> str:
        """Resolve a normalized identifier to a numeric Steam ID.

        Numeric identifiers are returned without a network request. Vanity
        identifiers are resolved through Steam.

        Args:
            identifier: The normalized numeric or vanity identifier.

        Returns:
            The resolved 17-digit Steam ID.

        Raises:
            SteamProfileNotFoundError: If Steam cannot resolve the vanity name.
            SteamAPIUnavailableError: If Steam cannot be reached.
            SteamAPIError: If Steam rejects the request or returns invalid data.
        """
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
        """Fetch and normalize public metadata for a Steam profile.

        Args:
            steam_id: The profile's numeric Steam ID.

        Returns:
            The validated Steam profile metadata.

        Raises:
            SteamProfileNotFoundError: If Steam does not return the profile.
            SteamAPIUnavailableError: If Steam cannot be reached.
            SteamAPIError: If Steam rejects the request or returns invalid data.
        """
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
        """Fetch and normalize a profile's publicly visible owned games.

        Args:
            steam_id: The profile's numeric Steam ID.

        Returns:
            The complete owned-game library returned by Steam.

        Raises:
            SteamLibraryUnavailableError: If the library is not public.
            SteamAPIUnavailableError: If Steam cannot be reached.
            SteamAPIError: If Steam rejects the request or returns invalid data.
        """
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
        """Send an authenticated GET request and return a JSON object.

        Args:
            path: The Steam Web API endpoint path.
            params: Endpoint-specific query parameters.

        Returns:
            The decoded top-level JSON object.

        Raises:
            SteamAPIUnavailableError: If the network request fails.
            SteamAPIError: If the response is rejected or cannot be decoded.
        """
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
        """Extract and validate Steam's nested response object.

        Args:
            payload: The decoded top-level Steam payload.

        Returns:
            The nested response mapping.

        Raises:
            SteamAPIError: If the response field is missing or invalid.
        """
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
        """Validate and normalize one raw owned-game entry.

        Args:
            game: An untrusted game value from Steam's response.

        Returns:
            A normalized owned-game record.

        Raises:
            SteamAPIError: If a required game field is invalid.
        """
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
        """Validate a required nonnegative integer from Steam.

        Args:
            value: The untrusted field value.
            field_name: The human-readable field name used in errors.

        Returns:
            The validated integer.

        Raises:
            SteamAPIError: If the value is not a nonnegative integer.
        """
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
        """Validate an optional nonnegative integer from Steam.

        Args:
            value: The untrusted field value or `None`.
            field_name: The human-readable field name used in errors.

        Returns:
            The validated integer, or `None` when absent.

        Raises:
            SteamAPIError: If a present value is not a nonnegative integer.
        """
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
        """Convert an optional Unix timestamp to a UTC datetime.

        Args:
            value: The untrusted timestamp, zero, or `None`.

        Returns:
            A timezone-aware datetime, or `None` when the timestamp is absent.

        Raises:
            SteamAPIError: If the timestamp is negative, invalid, or out of
                range.
        """
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
        """Return a nonempty string value, or `None` when absent or invalid."""
        return value if isinstance(value, str) and value else None
