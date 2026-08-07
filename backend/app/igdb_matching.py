from dataclasses import dataclass
from enum import StrEnum
from collections.abc import Sequence
from typing import Any
from app.igdb_client import IGDBClient, IGDBResponseError

STEAM_EXTERNAL_GAME_SOURCE_ID = 1
STEAM_MATCH_BATCH_SIZE = 100
EXTERNAL_GAME_QUERY_LIMIT = 500


class IGDBMatchStatus(StrEnum):
    """Describe the outcome of matching one Steam game."""

    MATCHED = "matched"
    MISSING = "missing"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True)
class IGDBMatchResult:
    """Represent the normalized IGDB match for one Steam App ID."""

    steam_app_id: int
    status: IGDBMatchStatus
    igdb_game_id: int | None = None
    candidate_game_ids: tuple[int, ...] = ()


def _unique_steam_app_ids(
    steam_app_ids: Sequence[int],
) -> list[int]:
    """Validate and deduplicate Steam App IDs in their original order."""
    unique_ids = list(dict.fromkeys(steam_app_ids))

    for steam_app_id in unique_ids:
        if (
            not isinstance(steam_app_id, int)
            or isinstance(steam_app_id, bool)
            or steam_app_id <= 0
        ):
            raise ValueError("Steam App IDs must be positive integers.")

    return unique_ids


def normalize_external_game_matches(
    steam_app_ids: Sequence[int],
    external_games: list[dict[str, Any]],
) -> list[IGDBMatchResult]:
    """Normalize IGDB external-game records by Steam App ID."""

    requested_ids = _unique_steam_app_ids(steam_app_ids)
    candidates = {steam_app_id: set() for steam_app_id in requested_ids}

    for steam_app_id in requested_ids:
        if (
            not isinstance(steam_app_id, int)
            or isinstance(steam_app_id, bool)
            or steam_app_id <= 0
        ):
            raise ValueError("Steam App IDs must be positive integers.")

    for external_game in external_games:
        uid = external_game.get("uid")
        igdb_game_id = external_game.get("game")

        if not isinstance(uid, str) or not uid.isdecimal():
            raise IGDBResponseError(
                "IGDB returned an invalid external-game identifier."
            )

        steam_app_id = int(uid)

        if steam_app_id not in candidates:
            continue

        if igdb_game_id is None:
            continue

        if (
            not isinstance(igdb_game_id, int)
            or isinstance(igdb_game_id, bool)
            or igdb_game_id <= 0
        ):
            raise IGDBResponseError(
                "IGDB returned an invalid game reference."
            )

        candidates[steam_app_id].add(igdb_game_id)

    results: list[IGDBMatchResult] = []

    for steam_app_id, game_ids in candidates.items():
        sorted_game_ids = tuple(sorted(game_ids))

        if len(sorted_game_ids) == 1:
            results.append(
                IGDBMatchResult(
                    steam_app_id=steam_app_id,
                    status=IGDBMatchStatus.MATCHED,
                    igdb_game_id=sorted_game_ids[0],
                )
            )
        elif len(sorted_game_ids) > 1:
            results.append(
                IGDBMatchResult(
                    steam_app_id=steam_app_id,
                    status=IGDBMatchStatus.AMBIGUOUS,
                    candidate_game_ids=sorted_game_ids,
                )
            )
        else:
            results.append(
                IGDBMatchResult(
                    steam_app_id=steam_app_id,
                    status=IGDBMatchStatus.MISSING,
                )
            )

    return results


def match_steam_app_ids(
    client: IGDBClient,
    steam_app_ids: Sequence[int],
) -> list[IGDBMatchResult]:
    """Match Steam App IDs to IGDB game IDs in bounded batches."""
    requested_ids = _unique_steam_app_ids(steam_app_ids)
    results: list[IGDBMatchResult] = []

    for start in range(0, len(requested_ids), STEAM_MATCH_BATCH_SIZE):
        batch = requested_ids[start: start + STEAM_MATCH_BATCH_SIZE]
        uid_values = ",".join(
            f'"{steam_app_id}"' for steam_app_id in batch
        )
        query_body = (
            "fields game,uid;"
            f" where external_game_source = "
            f"{STEAM_EXTERNAL_GAME_SOURCE_ID}"
            f" & uid = ({uid_values});"
            f" limit {EXTERNAL_GAME_QUERY_LIMIT};"
        )

        external_games = client.query("external_games", query_body)

        if len(external_games) >= EXTERNAL_GAME_QUERY_LIMIT:
            raise IGDBResponseError(
                "IGDB returned a potentially truncated match batch."
            )

        results.extend(
            normalize_external_game_matches(batch, external_games)
        )

    return results
