from typing import Literal, Self

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Load Ludex configuration from environment variables and `.env`."""

    database_url: str
    migration_database_url: SecretStr | None = None
    deployment_environment: Literal["local", "staging", "production"] = "local"
    frontend_origin: str
    access_session_cookie_secure: bool = True
    steam_rate_limit_hmac_key: SecretStr | None = None
    steam_api_key: SecretStr
    igdb_client_id: str
    igdb_client_secret: SecretStr
    gemini_api_key: SecretStr | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def alembic_database_url(self) -> str:
        """Use an operator-only direct URL when one is explicitly supplied."""
        if self.migration_database_url is not None:
            return self.migration_database_url.get_secret_value()

        return self.database_url

    @model_validator(mode="after")
    def require_hosted_rate_limit_key(self) -> Self:
        """Fail hosted startup without an isolated abuse-control key."""
        if self.deployment_environment != "local" and (
            self.steam_rate_limit_hmac_key is None
            or len(self.steam_rate_limit_hmac_key.get_secret_value()) < 32
        ):
            raise ValueError(
                "Hosted environments require STEAM_RATE_LIMIT_HMAC_KEY."
            )
        return self


settings = Settings()
