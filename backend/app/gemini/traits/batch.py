from collections.abc import Callable, Sequence
from concurrent.futures import (
    Future,
    ThreadPoolExecutor,
    as_completed,
)
from contextlib import AbstractContextManager
from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy.orm import Session

from app.gemini.traits.service import generate_saved_game_traits
from app.gemini.traits.contracts import GameTraitResponse
from app.gemini.client import GeminiClient


GAME_TRAIT_WORKER_LIMIT = 2


@dataclass(frozen=True)
class GameTraitBatchFailure:
    """Represent one game that could not complete trait generation."""

    steam_app_id: int
    error: Exception


@dataclass(frozen=True)
class GameTraitBatchResult:
    """Summarize generated, skipped, and failed games in request order."""

    generated_steam_app_ids: tuple[int, ...]
    skipped_steam_app_ids: tuple[int, ...]
    failures: tuple[GameTraitBatchFailure, ...]


def _new_operation_id() -> str:
    """Create one classification-operation identifier.

    Returns:
        A standard lowercase UUID string.
    """
    return str(uuid4())


def _unique_steam_app_ids(
    steam_app_ids: Sequence[int],
) -> list[int]:
    """Validate and deduplicate Steam App IDs in request order.

    Args:
        steam_app_ids: Requested shared games.

    Returns:
        Unique positive IDs in first-request order.

    Raises:
        ValueError: If any ID is not a positive integer.
    """
    unique_ids = list(dict.fromkeys(steam_app_ids))

    for steam_app_id in unique_ids:
        if (
            not isinstance(steam_app_id, int)
            or isinstance(steam_app_id, bool)
            or steam_app_id <= 0
        ):
            raise ValueError(
                "Steam App IDs must be positive integers."
            )

    return unique_ids


def _validate_operation_id(operation_id: str) -> None:
    """Validate one backend-generated operation identifier.

    Args:
        operation_id: Identifier that will group model attempts.

    Raises:
        ValueError: If the identifier is blank, padded, or too long.
    """
    if not isinstance(operation_id, str) or not operation_id:
        raise ValueError(
            "Operation IDs must be non-empty strings."
        )

    if operation_id != operation_id.strip():
        raise ValueError(
            "Operation IDs must not contain surrounding whitespace."
        )

    if len(operation_id) > 36:
        raise ValueError(
            "Operation IDs must contain at most 36 characters."
        )


def _generate_one_game(
    session_factory: Callable[
        [],
        AbstractContextManager[Session],
    ],
    client: GeminiClient,
    steam_app_id: int,
    operation_id: str,
) -> bool:
    """Generate or reuse traits for one game in an isolated session.

    Args:
        session_factory: Factory producing one worker-owned session context.
        client: Thread-shareable Gemini transport.
        steam_app_id: Shared game to inspect and possibly classify.
        operation_id: Identifier shared by this game's model attempts.

    Returns:
        True when new traits were generated, or False when current traits were
        reused.
    """
    with session_factory() as session:
        response: GameTraitResponse | None = (
            generate_saved_game_traits(
                session,
                client,
                steam_app_id=steam_app_id,
                operation_id=operation_id,
            )
        )

    return response is not None


def generate_game_trait_batch(
    session_factory: Callable[
        [],
        AbstractContextManager[Session],
    ],
    client: GeminiClient,
    steam_app_ids: Sequence[int],
    operation_id_factory: Callable[[], str] = _new_operation_id,
) -> GameTraitBatchResult:
    """Generate stale traits with at most two simultaneous workers.

    Every game receives an isolated database session and operation identifier.
    One game's exhausted retries are reported without preventing independent
    games from completing.

    Args:
        session_factory: Factory producing one session context per worker task.
        client: Configured Gemini client shared across worker threads.
        steam_app_ids: Games to process in first-request order.
        operation_id_factory: Injectable operation-ID factory used by tests.

    Returns:
        Generated, skipped, and failed outcomes in deduplicated request order.

    Raises:
        ValueError: If a Steam App ID or generated operation ID is invalid.
    """
    requested_ids = _unique_steam_app_ids(steam_app_ids)

    if not requested_ids:
        return GameTraitBatchResult(
            generated_steam_app_ids=(),
            skipped_steam_app_ids=(),
            failures=(),
        )

    jobs: list[tuple[int, str]] = []

    for steam_app_id in requested_ids:
        operation_id = operation_id_factory()
        _validate_operation_id(operation_id)
        jobs.append((steam_app_id, operation_id))

    outcomes: dict[
        int,
        bool | GameTraitBatchFailure,
    ] = {}

    with ThreadPoolExecutor(
        max_workers=GAME_TRAIT_WORKER_LIMIT,
    ) as executor:
        futures: dict[Future[bool], int] = {
            executor.submit(
                _generate_one_game,
                session_factory,
                client,
                steam_app_id,
                operation_id,
            ): steam_app_id
            for steam_app_id, operation_id in jobs
        }

        for future in as_completed(futures):
            steam_app_id = futures[future]

            try:
                outcomes[steam_app_id] = future.result()
            except Exception as error:
                outcomes[steam_app_id] = GameTraitBatchFailure(
                    steam_app_id=steam_app_id,
                    error=error,
                )

    return GameTraitBatchResult(
        generated_steam_app_ids=tuple(
            steam_app_id
            for steam_app_id in requested_ids
            if outcomes[steam_app_id] is True
        ),
        skipped_steam_app_ids=tuple(
            steam_app_id
            for steam_app_id in requested_ids
            if outcomes[steam_app_id] is False
        ),
        failures=tuple(
            outcome
            for steam_app_id in requested_ids
            if isinstance(
                outcome := outcomes[steam_app_id],
                GameTraitBatchFailure,
            )
        ),
    )
