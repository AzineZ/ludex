from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any
from app.integrations.igdb.client import IGDBClient, IGDBResponseError
from collections.abc import Sequence


METADATA_BATCH_SIZE = 100
METADATA_QUERY_LIMIT = 500

GAME_METADATA_FIELDS = (
    "id,name,summary,first_release_date,updated_at,"
    "cover.image_id,genres.name,themes.name,"
    "keywords.name,game_modes.name"
)

TIME_TO_BEAT_FIELDS = (
    "game_id,hastily,normally,completely,count,updated_at"
)


@dataclass(frozen=True)
class IGDBNamedEntity:
    """Represent a named IGDB genre, theme, keyword, or game mode."""

    igdb_id: int
    name: str


@dataclass(frozen=True)
class IGDBTimeToBeat:
    """Represent IGDB completion estimates in seconds."""

    igdb_game_id: int
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


def _unique_game_ids(
    igdb_game_ids: Sequence[int],
) -> list[int]:
    """Validate and deduplicate IGDB game IDs."""

    unique_ids = list(dict.fromkeys(igdb_game_ids))

    for igdb_game_id in unique_ids:
        if (
            not isinstance(igdb_game_id, int)
            or isinstance(igdb_game_id, bool)
            or igdb_game_id <= 0
        ):
            raise ValueError("IGDB game IDs must be positive integers.")

    return unique_ids


def fetch_game_metadata(
    client: IGDBClient,
    igdb_game_ids: Sequence[int],
) -> list[IGDBGameMetadata]:
    """Fetch and merge factual metadata in bounded batches."""
    requested_ids = _unique_game_ids(igdb_game_ids)
    results: list[IGDBGameMetadata] = []

    for start in range(0, len(requested_ids), METADATA_BATCH_SIZE):
        batch = requested_ids[start: start + METADATA_BATCH_SIZE]
        batch_ids = set(batch)
        id_values = ",".join(str(game_id) for game_id in batch)

        raw_games = client.query(
            "games",
            (
                f"fields {GAME_METADATA_FIELDS};"
                f" where id = ({id_values});"
                f" limit {METADATA_QUERY_LIMIT};"
            ),
        )

        if len(raw_games) >= METADATA_QUERY_LIMIT:
            raise IGDBResponseError(
                "IGDB returned a potentially truncated metadata batch."
            )

        games_by_id: dict[int, IGDBGameMetadata] = {}

        for raw_game in raw_games:
            metadata = normalize_game_metadata(raw_game)

            if metadata.igdb_game_id not in batch_ids:
                raise IGDBResponseError(
                    "IGDB returned unexpected game metadata."
                )

            if metadata.igdb_game_id in games_by_id:
                raise IGDBResponseError(
                    "IGDB returned duplicate game metadata."
                )

            games_by_id[metadata.igdb_game_id] = metadata

        if any(game_id not in games_by_id for game_id in batch):
            raise IGDBResponseError(
                "IGDB omitted requested game metadata."
            )

        raw_times = client.query(
            "game_time_to_beats",
            (
                f"fields {TIME_TO_BEAT_FIELDS};"
                f" where game_id = ({id_values});"
                f" limit {METADATA_QUERY_LIMIT};"
            ),
        )

        if len(raw_times) >= METADATA_QUERY_LIMIT:
            raise IGDBResponseError(
                "IGDB returned a potentially truncated time-to-beat batch."
            )

        times_by_id: dict[int, IGDBTimeToBeat] = {}

        for raw_time in raw_times:
            time_to_beat = normalize_time_to_beat(raw_time)

            if time_to_beat.igdb_game_id not in batch_ids:
                raise IGDBResponseError(
                    "IGDB returned unexpected time-to-beat data."
                )

            if time_to_beat.igdb_game_id in times_by_id:
                raise IGDBResponseError(
                    "IGDB returned duplicate time-to-beat data."
                )

            times_by_id[time_to_beat.igdb_game_id] = time_to_beat

        results.extend(
            replace(
                games_by_id[game_id],
                time_to_beat=times_by_id.get(game_id),
            )
            for game_id in batch
        )

    return results


def _normalize_optional_seconds(
    value: object,
    field_name: str,
) -> int | None:
    """Validate an optional non-negative duration."""

    if value is None:
        return None

    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < 0
    ):
        raise IGDBResponseError(
            f"IGDB returned an invalid {field_name}."
        )

    return value


def _normalize_timestamp(
    value: object,
    field_name: str,
) -> datetime | None:
    """Convert an optional Unix timestamp into a UTC datetime."""
    if value is None:
        return None

    if not isinstance(value, int) or isinstance(value, bool):
        raise IGDBResponseError(
            f"IGDB returned an invalid {field_name}."
        )

    try:
        return datetime.fromtimestamp(value, tz=UTC)
    except (OverflowError, OSError, ValueError):
        raise IGDBResponseError(
            f"IGDB returned an invalid {field_name}."
        ) from None


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


def normalize_game_metadata(
    game: dict[str, Any],
) -> IGDBGameMetadata:
    """Normalize one IGDB game response."""

    igdb_game_id = game.get("id")
    name = game.get("name")
    summary = game.get("summary")

    if (
        not isinstance(igdb_game_id, int)
        or isinstance(igdb_game_id, bool)
        or igdb_game_id <= 0
    ):
        raise IGDBResponseError("IGDB returned an invalid game ID.")

    if not isinstance(name, str) or not name.strip():
        raise IGDBResponseError("IGDB returned an invalid game name.")

    if summary is not None and not isinstance(summary, str):
        raise IGDBResponseError("IGDB returned an invalid game summary.")

    if isinstance(summary, str) and not summary.strip():
        summary = None

    cover = game.get("cover")
    cover_image_id: str | None = None

    if cover is not None:
        if not isinstance(cover, dict):
            raise IGDBResponseError("IGDB returned an invalid game cover.")

        image_id = cover.get("image_id")

        if image_id is not None:
            if not isinstance(image_id, str) or not image_id.strip():
                raise IGDBResponseError(
                    "IGDB returned an invalid cover image ID."
                )

            cover_image_id = image_id

    updated_at = _normalize_timestamp(
        game.get("updated_at"),
        "game update timestamp",
    )

    if updated_at is None:
        raise IGDBResponseError(
            "IGDB returned a missing game update timestamp."
        )

    return IGDBGameMetadata(
        igdb_game_id=igdb_game_id,
        name=name,
        summary=summary,
        first_release_at=_normalize_timestamp(
            game.get("first_release_date"),
            "first release timestamp",
        ),
        cover_image_id=cover_image_id,
        genres=_normalize_named_entities(game.get("genres"), "genre"),
        themes=_normalize_named_entities(game.get("themes"), "theme"),
        keywords=_normalize_named_entities(game.get("keywords"), "keyword"),
        game_modes=_normalize_named_entities(
            game.get("game_modes"),
            "game mode",
        ),
        updated_at=updated_at,
    )


def normalize_time_to_beat(
    record: dict[str, Any],
) -> IGDBTimeToBeat:
    """Normalize one IGDB time-to-beat response."""

    igdb_game_id = record.get("game_id")
    submission_count = record.get("count")

    if (
        not isinstance(igdb_game_id, int)
        or isinstance(igdb_game_id, bool)
        or igdb_game_id <= 0
    ):
        raise IGDBResponseError(
            "IGDB returned an invalid time-to-beat game ID."
        )

    if (
        not isinstance(submission_count, int)
        or isinstance(submission_count, bool)
        or submission_count < 0
    ):
        raise IGDBResponseError(
            "IGDB returned an invalid time-to-beat submission count."
        )

    updated_at = _normalize_timestamp(
        record.get("updated_at"),
        "time-to-beat update timestamp",
    )

    if updated_at is None:
        raise IGDBResponseError(
            "IGDB returned a missing time-to-beat update timestamp."
        )

    return IGDBTimeToBeat(
        igdb_game_id=igdb_game_id,
        hastily_seconds=_normalize_optional_seconds(
            record.get("hastily"),
            "hastily time",
        ),
        normally_seconds=_normalize_optional_seconds(
            record.get("normally"),
            "normally time",
        ),
        completely_seconds=_normalize_optional_seconds(
            record.get("completely"),
            "completionist time",
        ),
        submission_count=submission_count,
        updated_at=updated_at,
    )
