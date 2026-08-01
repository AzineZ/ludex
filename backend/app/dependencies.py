from collections.abc import Generator

from app.config import settings
from app.steam_client import SteamClient


def get_steam_client() -> Generator[SteamClient, None, None]:
    with SteamClient(
        settings.steam_api_key.get_secret_value()
    ) as steam_client:
        yield steam_client
