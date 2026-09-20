from collections.abc import Generator

from app.config import settings
from app.gemini.client import GeminiClient
from app.gemini.reranking.service import GeminiRerankRuntime


GEMINI_RERANK_MODEL_ID = "gemini-3.5-flash-lite"


def get_gemini_rerank_runtime(
) -> Generator[GeminiRerankRuntime | None, None, None]:
    """Provide the selected public reranker only when fully configured."""
    if (
        not settings.gemini_rerank_enabled
        or settings.gemini_api_key is None
    ):
        yield None
        return

    with GeminiClient(
        settings.gemini_api_key.get_secret_value(),
        timeout_seconds=20.0,
    ) as client:
        yield GeminiRerankRuntime(
            client=client,
            model_id=GEMINI_RERANK_MODEL_ID,
        )
