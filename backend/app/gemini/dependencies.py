from collections.abc import Generator

from app.config import settings
from app.gemini.client import GeminiClient


def get_gemini_client() -> Generator[GeminiClient, None, None]:
    """Provide a configured Gemini client and close it after use.

    Yields:
        A backend-only Gemini client configured with the private API key.
    """
    with GeminiClient(
        settings.gemini_api_key.get_secret_value()
    ) as gemini_client:
        yield gemini_client
