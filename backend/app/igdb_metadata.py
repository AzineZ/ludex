from dataclasses import dataclass
from datetime import datetime
from typing import Any
from app.igdb_client import IGDBResponseError


@dataclass(frozen=True)
class IGDBNamedEntity:
    """Represent a named IGDB genre, theme, keyword, or game mode."""

    igdb_id: int
    name: str


@dataclass(frozen=True)
class IGDBTimeToBeat:
    """Represent IGDB completion estimates in seconds."""

    hastily_seconds: int | None
    normally_seconds: int | None
    completely_seconds: int | None
    submission_count: int
    updated_at: datetime


@dataclass(frozen=True)
class IGDBGameMetadata:
    igdb_game_id: int
    name: str
    summary: str | None
    first_release_at: datetime | None
    cover_image_id: str | None
    genres: tuple[IGDBNamedEntity, ...]
    themes: tuple[IGDBNamedEntity, ...]
    keywords: tuple[IGDBNamedEntity, ...]
    game_modes: tuple[IGDBNamedEntity, ...]
    updated_at: datetime
    time_to_beat: IGDBTimeToBeat | None = None


def _normalize_named_entities(
    value: object,
    field_name: str,
) -> tuple[IGDBNamedEntity, ...]:
    """Validate and normalize an IGDB list of named entities."""
    if value is None:
        return ()

    if not isinstance(value, list):
        raise IGDBResponseError(f"IGDB returned an invalid {field_name} list.")

    entities: dict[int, str] = {}

    for entry in value:
        if not isinstance(entry, dict):
            raise IGDBResponseError(
                f"IGDB returned an invalid {field_name} entry."
            )

        igdb_id = entry.get("id")
        name = entry.get("name")

        if (
            not isinstance(igdb_id, int)
            or isinstance(igdb_id, bool)
            or igdb_id <= 0
            or not isinstance(name, str)
            or not name.strip()
        ):
            raise IGDBResponseError(
                f"IGDB returned an invalid {field_name} entry."
            )

        if igdb_id in entities and entities[igdb_id] != name:
            raise IGDBResponseError(
                f"IGDB returned conflicting {field_name} entries."
            )

        entities[igdb_id] = name

    return tuple(
        IGDBNamedEntity(igdb_id=igdb_id, name=name)
        for igdb_id, name in sorted(entities.items())
    )
