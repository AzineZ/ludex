"""Expose every ORM model so `Base.metadata` is complete on import."""

from app.models.access import (
    SteamAccessSession,
    SteamUsageEvent,
)
from app.models.games import (
    Game,
)
from app.models.igdb_metadata import (
    GameIGDBMetadataTerm,
    IGDBMetadataTerm,
)
from app.models.legacy_traits import (
    GameCurrentTraitDerivation,
    GameTraitAttempt,
    GameTraitDerivation,
    GameTraitEvidence,
    GameTraitMood,
)
from app.models.profiles import (
    Profile,
    ProfileGame,
)

__all__ = [
    "Game",
    "GameCurrentTraitDerivation",
    "GameIGDBMetadataTerm",
    "GameTraitAttempt",
    "GameTraitDerivation",
    "GameTraitEvidence",
    "GameTraitMood",
    "IGDBMetadataTerm",
    "Profile",
    "ProfileGame",
    "SteamAccessSession",
    "SteamUsageEvent",
]
