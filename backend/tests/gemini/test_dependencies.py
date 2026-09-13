from types import TracebackType
from typing import Self

import pytest

import app.gemini.dependencies as dependencies
from app.gemini.dependencies import (
    GEMINI_RERANK_MODEL_ID,
    GeminiConfigurationError,
    get_gemini_client,
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


def test_gemini_dependency_rejects_missing_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fail clearly when the deferred integration is manually invoked."""
    FakeGeminiClient.instances.clear()
    monkeypatch.setattr(
        dependencies.settings,
        "gemini_api_key",
        None,
    )

    with pytest.raises(
        GeminiConfigurationError,
        match="Gemini API key is not configured.",
    ):
        next(get_gemini_client())

    assert FakeGeminiClient.instances == []


def test_gemini_dependency_yields_configured_client_and_closes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unwrap the backend secret only while constructing the client."""
    FakeGeminiClient.instances.clear()
    monkeypatch.setattr(
        dependencies,
        "GeminiClient",
        FakeGeminiClient,
        raising=False,
    )

    dependency = get_gemini_client()
    client = next(dependency)

    assert client is FakeGeminiClient.instances[0]
    assert client.api_key == "test-gemini-api-key"
    assert client.entered is True
    assert client.exited is False

    dependency.close()

    assert client.exited is True
    assert client.exit_exception_type is GeneratorExit


def test_gemini_dependency_closes_after_consumer_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Release the client when downstream route logic raises."""
    FakeGeminiClient.instances.clear()
    monkeypatch.setattr(
        dependencies,
        "GeminiClient",
        FakeGeminiClient,
        raising=False,
    )

    dependency = get_gemini_client()
    client = next(dependency)

    with pytest.raises(RuntimeError, match="Route failed"):
        dependency.throw(RuntimeError("Route failed"))

    assert client.exited is True
    assert client.exit_exception_type is RuntimeError


def test_public_reranker_is_disabled_unless_every_guard_is_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(dependencies.settings, "gemini_rerank_enabled", False)

    dependency = get_gemini_rerank_runtime()

    assert next(dependency) is None
    with pytest.raises(StopIteration):
        next(dependency)


def test_public_reranker_uses_selected_model_and_configured_budgets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    FakeGeminiClient.instances.clear()
    monkeypatch.setattr(dependencies, "GeminiClient", FakeGeminiClient)
    monkeypatch.setattr(dependencies.settings, "gemini_rerank_enabled", True)
    monkeypatch.setattr(
        dependencies.settings,
        "gemini_public_requests_per_minute",
        5,
    )
    monkeypatch.setattr(
        dependencies.settings,
        "gemini_public_requests_per_day",
        20,
    )
    monkeypatch.setattr(
        dependencies.settings,
        "gemini_public_daily_ceiling",
        10,
    )

    dependency = get_gemini_rerank_runtime()
    runtime = next(dependency)

    assert runtime is not None
    assert runtime.model_id == GEMINI_RERANK_MODEL_ID == "gemini-3.6-flash"
    assert runtime.quota_policy.minute_budget == 4
    assert runtime.quota_policy.daily_budget == 10
    assert runtime.client.options == {"timeout_seconds": 20.0}
    dependency.close()
    assert runtime.client.exited is True
