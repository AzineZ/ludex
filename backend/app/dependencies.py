from collections.abc import Generator

from app.config import settings
from app.integrations.steam.client import SteamClient


def get_steam_client() -> Generator[SteamClient, None, None]:
    """Provide a configured Steam client and close it after use.

    Yields:
        A Steam Web API client configured with the private API key.
    """
    with SteamClient(
        settings.steam_api_key.get_secret_value()
    ) as steam_client:
        yield steam_client
