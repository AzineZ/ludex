from types import TracebackType
from typing import Self

import pytest

import app.gemini.dependencies as dependencies
from app.gemini.dependencies import (
    GEMINI_RERANK_MODEL_ID,
    get_gemini_rerank_runtime,
)


class FakeGeminiClient:
    """Track Gemini dependency construction and cleanup."""

    instances: list[Self] = []

    def __init__(self, api_key: str, **options: object) -> None:
        """Record the configured API key.

        Args:
            api_key: Secret value unwrapped by the dependency.
        """
        self.api_key = api_key
        self.options = options
        self.entered = False
        self.exited = False
        self.exit_exception_type: type[BaseException] | None = None
        self.instances.append(self)

    def __enter__(self) -> Self:
        """Enter the fake client context."""
        self.entered = True
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Record cleanup and any propagated consumer exception."""
        self.exited = True
        self.exit_exception_type = exception_type


def test_public_reranker_is_disabled_when_feature_flag_is_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(dependencies.settings, "gemini_rerank_enabled", False)

    dependency = get_gemini_rerank_runtime()

    assert next(dependency) is None
    with pytest.raises(StopIteration):
        next(dependency)


def test_public_reranker_is_disabled_without_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(dependencies.settings, "gemini_rerank_enabled", True)
    monkeypatch.setattr(dependencies.settings, "gemini_api_key", None)

    dependency = get_gemini_rerank_runtime()

    assert next(dependency) is None
    with pytest.raises(StopIteration):
        next(dependency)


def test_public_reranker_uses_selected_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    FakeGeminiClient.instances.clear()
    monkeypatch.setattr(dependencies, "GeminiClient", FakeGeminiClient)
    monkeypatch.setattr(dependencies.settings, "gemini_rerank_enabled", True)
    dependency = get_gemini_rerank_runtime()
    runtime = next(dependency)

    assert runtime is not None
    assert (
        runtime.model_id
        == GEMINI_RERANK_MODEL_ID
        == "gemini-3.5-flash-lite"
    )
    assert runtime.client.options == {"timeout_seconds": 20.0}
    dependency.close()
    assert runtime.client.exited is True
