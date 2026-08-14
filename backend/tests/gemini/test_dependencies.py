from types import TracebackType
from typing import Self

import pytest

import app.gemini.dependencies as dependencies
from app.gemini.dependencies import (
    GeminiConfigurationError,
    get_gemini_client,
)


class FakeGeminiClient:
    """Track Gemini dependency construction and cleanup."""

    instances: list[Self] = []

    def __init__(self, api_key: str) -> None:
        """Record the configured API key.

        Args:
            api_key: Secret value unwrapped by the dependency.
        """
        self.api_key = api_key
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
