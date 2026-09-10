import argparse
from collections.abc import Callable, Iterator, Sequence
from contextlib import AbstractContextManager, contextmanager
from io import TextIOBase
import json
import sys

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal, engine
from app.gemini.client import GeminiClient, GeminiRateLimitError
from app.gemini.dependencies import GeminiConfigurationError
from app.gemini.traits.batch import (
    GameTraitRequestLimiter,
    GameTraitRunResult,
    run_game_trait_batches,
)
from app.gemini.traits.contracts import MAX_GAMES_PER_TRAIT_REQUEST
from app.gemini.traits.planning import (
    OwnedReadyGameTraitInventory,
    load_owned_ready_game_trait_inventory,
)


DEFAULT_MAXIMUM_REQUESTS = 100
DEFAULT_REQUESTS_PER_MINUTE = 10
GEMINI_TRAIT_ADVISORY_LOCK_KEY = 0x4C55444558475452

SessionFactory = Callable[[], AbstractContextManager[Session]]
ClientFactory = Callable[[], AbstractContextManager[GeminiClient]]
ApplyLock = Callable[[], AbstractContextManager[bool]]
BatchRunner = Callable[..., GameTraitRunResult]


@contextmanager
def _gemini_trait_apply_lock() -> Iterator[bool]:
    """Hold one transaction-scoped PostgreSQL lock for an apply run."""
    with engine.connect() as connection:
        with connection.begin():
            acquired = connection.scalar(
                text("SELECT pg_try_advisory_xact_lock(:lock_key)"),
                {"lock_key": GEMINI_TRAIT_ADVISORY_LOCK_KEY},
            )
            yield bool(acquired)


@contextmanager
def _gemini_client_factory() -> Iterator[GeminiClient]:
    """Provide the owner-operated Gemini client for an approved apply."""
    api_key = settings.gemini_api_key
    if api_key is None:
        raise GeminiConfigurationError(
            "Gemini API key is not configured."
        )

    with GeminiClient(api_key.get_secret_value()) as client:
        yield client


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Report or explicitly apply bounded shared game-trait "
            "preparation."
        )
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Call Gemini for pending traits. Requires a separately approved "
            "operator run."
        ),
    )
    parser.add_argument(
        "--max-requests",
        type=int,
        default=DEFAULT_MAXIMUM_REQUESTS,
        help="Provider-attempt ceiling for this process (maximum 100).",
    )
    parser.add_argument(
        "--requests-per-minute",
        type=int,
        default=DEFAULT_REQUESTS_PER_MINUTE,
        help="Start-rate ceiling for this process (maximum 10).",
    )
    return parser


def _validate_options(options: argparse.Namespace) -> None:
    if not 1 <= options.max_requests <= DEFAULT_MAXIMUM_REQUESTS:
        raise ValueError("--max-requests must be between 1 and 100.")
    if not 1 <= options.requests_per_minute <= DEFAULT_REQUESTS_PER_MINUTE:
        raise ValueError(
            "--requests-per-minute must be between 1 and 10."
        )


def _batch_count(game_count: int, batch_size: int) -> int:
    if game_count == 0:
        return 0
    return (game_count + batch_size - 1) // batch_size


def _maximum_request_count(game_count: int) -> int:
    """Return primary plus worst-case smaller-group corrective attempts."""
    total = 0
    for start in range(0, game_count, MAX_GAMES_PER_TRAIT_REQUEST):
        group_size = min(
            MAX_GAMES_PER_TRAIT_REQUEST,
            game_count - start,
        )
        total += 1 + _batch_count(group_size, 2)
    return total


def _inventory_payload(
    inventory: OwnedReadyGameTraitInventory,
) -> dict[str, int]:
    pending_count = len(inventory.pending_steam_app_ids)
    return {
        "ready_owned_game_count": inventory.ready_owned_game_count,
        "current_trait_game_count": len(
            inventory.current_steam_app_ids
        ),
        "pending_trait_game_count": pending_count,
        "primary_request_count": _batch_count(
            pending_count,
            MAX_GAMES_PER_TRAIT_REQUEST,
        ),
        "worst_case_request_count": _maximum_request_count(
            pending_count
        ),
    }


def _write_payload(payload: dict[str, object], output: TextIOBase) -> None:
    json.dump(payload, output, indent=2, sort_keys=True)
    output.write("\n")


def run_gemini_trait_enrichment_command(
    arguments: Sequence[str],
    *,
    session_factory: SessionFactory = SessionLocal,
    client_factory: ClientFactory = _gemini_client_factory,
    apply_lock: ApplyLock = _gemini_trait_apply_lock,
    batch_runner: BatchRunner = run_game_trait_batches,
    output: TextIOBase = sys.stdout,
    error_output: TextIOBase = sys.stderr,
) -> int:
    """Report readiness or run one explicitly bounded resumable apply."""
    options = _parser().parse_args(arguments)
    _validate_options(options)

    with session_factory() as session:
        before = load_owned_ready_game_trait_inventory(session)

    if not options.apply:
        _write_payload(
            {
                "mode": "report-only",
                **_inventory_payload(before),
                "configured_maximum_requests": options.max_requests,
                "configured_requests_per_minute": (
                    options.requests_per_minute
                ),
                "would_fit_primary_request_budget": (
                    _batch_count(
                        len(before.pending_steam_app_ids),
                        MAX_GAMES_PER_TRAIT_REQUEST,
                    )
                    <= options.max_requests
                ),
            },
            output,
        )
        return 0

    with apply_lock() as lock_acquired:
        if not lock_acquired:
            _write_payload(
                {
                    "mode": "blocked",
                    "detail": "Game-trait preparation is already running.",
                    **_inventory_payload(before),
                },
                error_output,
            )
            return 2

        try:
            limiter = GameTraitRequestLimiter(
                maximum_requests=options.max_requests,
                requests_per_minute=options.requests_per_minute,
            )
            if before.pending_steam_app_ids:
                with client_factory() as client:
                    result = batch_runner(
                        session_factory,
                        client,
                        before.pending_steam_app_ids,
                        limiter=limiter,
                    )
            else:
                result = GameTraitRunResult((), (), (), 0, None)
        except GeminiConfigurationError:
            _write_payload(
                {
                    "mode": "failed",
                    "detail": "Gemini is not configured for this operator.",
                    "before": _inventory_payload(before),
                },
                error_output,
            )
            return 1

        with session_factory() as session:
            after = load_owned_ready_game_trait_inventory(session)

        terminal_code = None
        retry_after_seconds = None
        if result.terminal_error is not None:
            terminal_code = type(result.terminal_error).__name__
            if isinstance(result.terminal_error, GeminiRateLimitError):
                retry_after_seconds = (
                    result.terminal_error.retry_after_seconds
                )

        payload: dict[str, object] = {
            "mode": (
                "applied"
                if result.terminal_error is None and not result.failures
                else "incomplete"
            ),
            "request_count": result.request_count,
            "generated_game_count": len(
                result.generated_steam_app_ids
            ),
            "skipped_game_count": len(result.skipped_steam_app_ids),
            "failed_game_count": len(result.failures),
            "terminal_code": terminal_code,
            "retry_after_seconds": retry_after_seconds,
            "before": _inventory_payload(before),
            "after": _inventory_payload(after),
            "resumable": bool(after.pending_steam_app_ids),
        }
        destination = (
            output
            if payload["mode"] == "applied"
            else error_output
        )
        _write_payload(payload, destination)
        return 0 if payload["mode"] == "applied" else 1


def main() -> None:
    raise SystemExit(run_gemini_trait_enrichment_command(sys.argv[1:]))


if __name__ == "__main__":
    main()
