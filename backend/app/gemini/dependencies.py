from collections.abc import Generator

from app.config import settings
from app.gemini.client import GeminiClient


class GeminiConfigurationError(RuntimeError):
    """Indicate that the deferred Gemini integration is not configured."""


def get_gemini_client() -> Generator[GeminiClient, None, None]:
    """Provide a configured Gemini client and close it after use.

    Yields:
        A backend-only Gemini client configured with the private API key.

    Raises:
        GeminiConfigurationError: If the deferred integration has no API key.
    """
    api_key = settings.gemini_api_key
    if api_key is None:
        raise GeminiConfigurationError(
            "Gemini API key is not configured."
        )

    with GeminiClient(
        api_key.get_secret_value()
    ) as gemini_client:
        yield gemini_client
