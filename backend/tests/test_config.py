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


def test_allows_missing_gemini_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Allow the active MVP to start without a Gemini credential."""
    values = _valid_settings()
    del values["gemini_api_key"]
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    settings = Settings(
        _env_file=None,
        **values,
    )

    assert settings.gemini_api_key is None


def test_access_session_cookie_is_secure_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ACCESS_SESSION_COOKIE_SECURE", raising=False)
    settings = Settings(
        _env_file=None,
        **_valid_settings(),
    )

    assert settings.access_session_cookie_secure is True


def test_allows_local_development_to_disable_secure_cookie() -> None:
    settings = Settings(
        _env_file=None,
        **_valid_settings(),
        access_session_cookie_secure=False,
    )

    assert settings.access_session_cookie_secure is False


def test_alembic_falls_back_to_runtime_database_url_locally(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MIGRATION_DATABASE_URL", raising=False)
    settings = Settings(
        _env_file=None,
        **_valid_settings(),
    )

    assert settings.alembic_database_url == (
        "postgresql+psycopg://test:test@localhost/test"
    )


def test_alembic_prefers_separate_direct_migration_url() -> None:
    settings = Settings(
        _env_file=None,
        **_valid_settings(),
        migration_database_url=(
            "postgresql+psycopg://migrator:secret@direct.example/test"
        ),
    )

    assert settings.alembic_database_url == (
        "postgresql+psycopg://migrator:secret@direct.example/test"
    )
    assert "migrator:secret" not in repr(settings)


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_hosted_environment_requires_rate_limit_hmac_secret(
    environment: str,
) -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            **_valid_settings(),
            deployment_environment=environment,
        )


def test_hosted_rate_limit_hmac_secret_is_masked() -> None:
    settings = Settings(
        _env_file=None,
        **_valid_settings(),
        deployment_environment="staging",
        steam_rate_limit_hmac_key="a" * 32,
    )

    assert isinstance(settings.steam_rate_limit_hmac_key, SecretStr)
    assert "a" * 32 not in repr(settings)
