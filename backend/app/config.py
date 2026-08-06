from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Load Ludex configuration from environment variables and `.env`."""

    database_url: str
    frontend_origin: str
    steam_api_key: SecretStr
    igdb_client_id: str
    igdb_client_secret: SecretStr

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
