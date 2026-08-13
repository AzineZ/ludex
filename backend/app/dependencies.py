from collections.abc import Generator

from app.config import settings
from app.steam_client import SteamClient
from app.gemini_client import GeminiClient


def get_steam_client() -> Generator[SteamClient, None, None]:
    """Provide a configured Steam client and close it after use.

    Yields:
        A Steam Web API client configured with the private API key.
    """
    with SteamClient(
        settings.steam_api_key.get_secret_value()
    ) as steam_client:
        yield steam_client


def get_gemini_client() -> Generator[GeminiClient, None, None]:
    """Provide a configured Gemini client and close it after use.

    Yields:
        A backend-only Gemini client configured with the private API key.
    """
    with GeminiClient(
        settings.gemini_api_key.get_secret_value()
    ) as gemini_client:
        yield gemini_client
