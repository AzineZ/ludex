from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProfileCreateRequest(BaseModel):
    """Validate the Steam identifier and authorized-use assertion."""

    model_config = ConfigDict(extra="forbid")

    identifier: str = Field(
        min_length=1,
        max_length=500,
    )
    authorized_use_acknowledged: bool = Field(strict=True)

    @field_validator("authorized_use_acknowledged")
    @classmethod
    def require_authorized_use_acknowledgment(cls, value: bool) -> bool:
        """Accept only an explicit JSON boolean true assertion."""
        if value is not True:
            raise ValueError("Authorized-use acknowledgment is required.")
        return value


class OwnedGameResponse(BaseModel):
    """Describe one owned game and its profile-specific playtime."""

    steam_app_id: int
    name: str
    icon_url: str | None
    cover_url: str | None
    playtime_minutes: int
    recent_playtime_minutes: int | None
    last_played_at: datetime | None


class SessionProfileResponse(BaseModel):
    """Describe the cookie-authorized profile without its internal ID."""

    steam_id: str
    display_name: str
    profile_url: str | None
    avatar_url: str | None
    created_at: datetime
    last_synced_at: datetime | None
    games: list[OwnedGameResponse]
