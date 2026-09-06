from collections.abc import Callable, Generator
from datetime import UTC, datetime
import secrets
from typing import Annotated, Any

from fastapi import Depends
from sqlalchemy.orm import Session

from app.abuse.steam import reserve_provider_call
from app.config import settings
from app.database import get_database_session
from app.integrations.steam.client import SteamClient


_LOCAL_RATE_LIMIT_KEY = secrets.token_bytes(32)


def get_steam_rate_limit_clock() -> datetime:
    """Provide one replaceable UTC clock for provider-call reservations."""
    return datetime.now(UTC)


def get_steam_rate_limit_hmac_key() -> bytes:
    """Return the hosted secret or a process-local development key."""
    configured_key = settings.steam_rate_limit_hmac_key
    if configured_key is None:
        if settings.deployment_environment != "local":
            raise RuntimeError("The hosted Steam rate-limit key is missing.")
        return _LOCAL_RATE_LIMIT_KEY
    return configured_key.get_secret_value().encode("utf-8")


class BudgetedSteamClient:
    """Construct Steam lazily and reserve every outbound call durably."""

    def __init__(
        self,
        database_session: Session,
        hmac_key: bytes,
        *,
        clock: Callable[[], datetime],
        client_factory: Callable[[], SteamClient],
    ) -> None:
        self._database_session = database_session
        self._hmac_key = hmac_key
        self._clock = clock
        self._client_factory = client_factory
        self._client: SteamClient | None = None

    def _call(self, method_name: str, *arguments: object) -> Any:
        reserve_provider_call(
            self._database_session,
            self._hmac_key,
            now=self._clock(),
        )
        if self._client is None:
            self._client = self._client_factory()
        method = getattr(self._client, method_name)
        return method(*arguments)

    def resolve_steam_id(self, identifier: object) -> str:
        return self._call("resolve_steam_id", identifier)

    def get_profile(self, steam_id: str) -> object:
        return self._call("get_profile", steam_id)

    def get_owned_games(self, steam_id: str) -> object:
        return self._call("get_owned_games", steam_id)

    def close(self) -> None:
        if self._client is not None:
            self._client.close()


def get_steam_client(
    database_session: Annotated[
        Session,
        Depends(get_database_session),
    ],
    hmac_key: Annotated[
        bytes,
        Depends(get_steam_rate_limit_hmac_key),
    ],
) -> Generator[BudgetedSteamClient, None, None]:
    """Provide a lazy Steam client whose real calls consume durable budget.

    Yields:
        A lazy, quota-enforcing client configured with the private API key.
    """
    steam_client = BudgetedSteamClient(
        database_session,
        hmac_key,
        clock=get_steam_rate_limit_clock,
        client_factory=lambda: SteamClient(
            settings.steam_api_key.get_secret_value()
        ),
    )
    try:
        yield steam_client
    finally:
        steam_client.close()
