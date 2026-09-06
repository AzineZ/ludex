from collections.abc import Callable
from dataclasses import dataclass
import time
from types import TracebackType
from typing import Any, Self

import httpx


TWITCH_TOKEN_URL = "https://id.twitch.tv/oauth2/token"
IGDB_API_BASE_URL = "https://api.igdb.com/v4"
TOKEN_REFRESH_MARGIN_SECONDS = 60.0


class IGDBAPIError(RuntimeError):
    """Indicate that Twitch or IGDB rejected or malformed a request."""

    pass


class IGDBAuthenticationError(IGDBAPIError):
    """Indicate that Twitch or IGDB rejected authentication."""

    pass


class IGDBRateLimitError(IGDBAPIError):
    """Indicate that Twitch or IGDB rate-limited a request."""

    pass


class IGDBUnavailableError(IGDBAPIError):
    """Indicate that Twitch or IGDB is temporarily unavailable."""

    pass


class IGDBResponseError(IGDBAPIError):
    """Indicate that Twitch or IGDB returned invalid response data."""

    pass


@dataclass(frozen=True)
class _CachedToken:
    """Store an access token and its monotonic expiration time."""

    access_token: str
    expires_at: float


class IGDBClient:
    """Send authenticated requests to the IGDB API."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        transport: httpx.BaseTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Initialize a synchronous IGDB client.

        Args:
            client_id: The Twitch application client ID.
            client_secret: The private Twitch application client secret.
            transport: Optional HTTPX transport used by isolated tests.
            clock: Monotonic clock used to calculate token expiration.
        """
        self._client_id = client_id
        self._client_secret = client_secret
        self._clock = clock
        self._cached_token: _CachedToken | None = None
        self._http_client = httpx.Client(
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
        """Exit a context and release the HTTP connection."""
        self.close()

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._http_client.close()

    def query(
        self,
        endpoint: str,
        query_body: str,
    ) -> list[dict[str, Any]]:
        """Send one authenticated Apicalypse query to IGDB.

        Args:
            endpoint: A simple IGDB endpoint name such as ``games``.
            query_body: The raw Apicalypse query body.

        Returns:
            The validated list of objects returned by IGDB.

        Raises:
            ValueError: If the endpoint or query body is invalid.
            IGDBAuthenticationError: If authentication is rejected.
            IGDBRateLimitError: If the request is rate-limited.
            IGDBUnavailableError: If IGDB cannot be reached.
            IGDBResponseError: If IGDB returns invalid response data.
            IGDBAPIError: If IGDB otherwise rejects the request.
        """
        self._validate_endpoint(endpoint)

        if not query_body.strip():
            raise ValueError("The IGDB query body cannot be empty.")

        access_token = self._get_access_token()

        try:
            response = self._http_client.post(
                f"{IGDB_API_BASE_URL}/{endpoint}",
                headers={
                    "Accept": "application/json",
                    "Client-ID": self._client_id,
                    "Authorization": f"Bearer {access_token}",
                },
                content=query_body,
            )
        except httpx.RequestError:
            raise IGDBUnavailableError(
                "IGDB is currently unavailable."
            ) from None

        self._raise_query_error(response)

        try:
            payload: object = response.json()
        except ValueError:
            raise IGDBResponseError(
                "IGDB returned invalid response data."
            ) from None

        if not isinstance(payload, list):
            raise IGDBResponseError(
                "IGDB returned an unexpected response."
            )

        if not all(isinstance(entry, dict) for entry in payload):
            raise IGDBResponseError(
                "IGDB returned an invalid response entry."
            )

        return payload

    def _get_access_token(self) -> str:
        """Return a reusable access token, refreshing it when necessary."""
        current_time = self._clock()

        if (
            self._cached_token is not None
            and current_time < self._cached_token.expires_at
        ):
            return self._cached_token.access_token

        try:
            response = self._http_client.post(
                TWITCH_TOKEN_URL,
                params={
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "grant_type": "client_credentials",
                },
            )
        except httpx.RequestError:
            raise IGDBUnavailableError(
                "IGDB authentication is currently unavailable."
            ) from None

        self._raise_token_error(response)

        try:
            payload: object = response.json()
        except ValueError:
            raise IGDBResponseError(
                "Twitch returned invalid authentication data."
            ) from None

        if not isinstance(payload, dict):
            raise IGDBResponseError(
                "Twitch returned an unexpected authentication response."
            )

        access_token = payload.get("access_token")
        expires_in = payload.get("expires_in")

        if not isinstance(access_token, str) or not access_token:
            raise IGDBResponseError(
                "Twitch returned an invalid access token."
            )

        if (
            not isinstance(expires_in, int)
            or isinstance(expires_in, bool)
            or expires_in <= 0
        ):
            raise IGDBResponseError(
                "Twitch returned an invalid token expiration."
            )

        refresh_margin = min(
            TOKEN_REFRESH_MARGIN_SECONDS,
            expires_in * 0.1,
        )
        expires_at = current_time + expires_in - refresh_margin

        self._cached_token = _CachedToken(
            access_token=access_token,
            expires_at=expires_at,
        )

        return access_token

    @staticmethod
    def _validate_endpoint(endpoint: str) -> None:
        """Require a simple allowlist-friendly IGDB endpoint name."""
        normalized_endpoint = endpoint.replace("_", "")

        if (
            not endpoint
            or not endpoint.isascii()
            or not normalized_endpoint.isalnum()
        ):
            raise ValueError(
                "The IGDB endpoint must be a simple endpoint name."
            )

    @staticmethod
    def _raise_token_error(response: httpx.Response) -> None:
        """Translate an unsuccessful Twitch token response."""
        if response.is_success:
            return

        if response.status_code in {400, 401, 403}:
            raise IGDBAuthenticationError(
                "IGDB authentication was rejected."
            )

        if response.status_code == 429:
            raise IGDBRateLimitError(
                "IGDB authentication was rate-limited."
            )

        if response.status_code >= 500:
            raise IGDBUnavailableError(
                "IGDB authentication is currently unavailable."
            )

        raise IGDBAPIError(
            "Twitch rejected the authentication request."
        )

    @staticmethod
    def _raise_query_error(response: httpx.Response) -> None:
        """Translate an unsuccessful IGDB API response."""
        if response.is_success:
            return

        if response.status_code in {401, 403}:
            raise IGDBAuthenticationError(
                "IGDB authentication was rejected."
            )

        if response.status_code == 429:
            raise IGDBRateLimitError(
                "IGDB rate-limited the API request."
            )

        if response.status_code >= 500:
            raise IGDBUnavailableError(
                "IGDB is currently unavailable."
            )

        raise IGDBAPIError(
            "IGDB rejected the API request."
        )
