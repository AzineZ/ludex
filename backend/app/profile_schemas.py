from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProfileCreateRequest(BaseModel):
    """Validate the Steam identifier submitted for profile import."""

    model_config = ConfigDict(extra="forbid")

    identifier: str = Field(
        min_length=1,
        max_length=500,
    )


class OwnedGameResponse(BaseModel):
    """Describe one owned game and its profile-specific playtime."""

    steam_app_id: int
    name: str
    icon_url: str | None
    playtime_minutes: int
    recent_playtime_minutes: int | None
    last_played_at: datetime | None


class ProfileSummaryResponse(BaseModel):
    """Describe a saved profile without its owned-game library."""

    id: int
    steam_id: str
    display_name: str
    profile_url: str | None
    avatar_url: str | None
    created_at: datetime
    last_synced_at: datetime | None


class ProfileDetailResponse(ProfileSummaryResponse):
    """Describe a saved profile together with its owned games."""

    games: list[OwnedGameResponse]
