from collections.abc import Generator

from app.config import settings
from app.gemini.client import GeminiClient
from app.gemini.prompt.quota import PromptQuotaPolicy
from app.gemini.reranking.service import GeminiRerankRuntime


GEMINI_RERANK_MODEL_ID = "gemini-3.6-flash"


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


def get_gemini_rerank_runtime(
) -> Generator[GeminiRerankRuntime | None, None, None]:
    """Provide the selected public reranker only when fully configured."""
    if (
        not settings.gemini_rerank_enabled
        or settings.gemini_api_key is None
        or settings.gemini_public_requests_per_minute is None
        or settings.gemini_public_requests_per_day is None
    ):
        yield None
        return

    try:
        policy = PromptQuotaPolicy(
            provider_requests_per_minute=(
                settings.gemini_public_requests_per_minute
            ),
            provider_requests_per_day=(
                settings.gemini_public_requests_per_day
            ),
            global_daily_ceiling=settings.gemini_public_daily_ceiling,
        )
    except ValueError:
        yield None
        return
    with GeminiClient(
        settings.gemini_api_key.get_secret_value(),
        timeout_seconds=20.0,
    ) as client:
        yield GeminiRerankRuntime(
            client=client,
            model_id=GEMINI_RERANK_MODEL_ID,
            quota_policy=policy,
        )
