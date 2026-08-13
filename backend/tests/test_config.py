import pytest
from pydantic import SecretStr, ValidationError

from app.config import Settings


def _valid_settings() -> dict[str, str]:
    """Return complete non-secret test configuration values."""
    return {
        "database_url": "postgresql+psycopg://test:test@localhost/test",
        "frontend_origin": "http://localhost:5173",
        "steam_api_key": "test-steam-key",
        "igdb_client_id": "test-igdb-client",
        "igdb_client_secret": "test-igdb-secret",
        "gemini_api_key": "test-gemini-secret",
    }


def test_loads_gemini_api_key_as_secret() -> None:
    """Keep the Gemini credential masked by the settings model."""
    settings = Settings(
        _env_file=None,
        **_valid_settings(),
    )

    assert isinstance(settings.gemini_api_key, SecretStr)
    assert (
        settings.gemini_api_key.get_secret_value()
        == "test-gemini-secret"
    )
    assert "test-gemini-secret" not in repr(settings)


def test_requires_gemini_api_key(
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reject backend configuration without a Gemini credential."""
    values = _valid_settings()
    del values["gemini_api_key"]
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            **values,
        )
