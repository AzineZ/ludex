import argparse
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from io import TextIOBase
import sys

from sqlalchemy.orm import Session

from app.command_output import write_json_payload
from app.database import SessionLocal
from app.integrations.igdb.client import IGDBAPIError, IGDBClient
from app.integrations.igdb.command import _igdb_client_factory
from app.integrations.igdb.locking import igdb_enrichment_lock
from app.integrations.igdb.ratings_backfill import (
    RATINGS_BATCH_SIZE,
    UncheckedRatingGame,
    backfill_game_ratings,
    get_unchecked_rating_games,
)


SessionFactory = Callable[[], Session]
ClientFactory = Callable[[], AbstractContextManager[IGDBClient]]
BackfillService = Callable[
    [Session, IGDBClient, Sequence[UncheckedRatingGame]],
    int,
]
ApplyLock = Callable[[], AbstractContextManager[bool]]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Report or explicitly apply the one-time IGDB ratings backfill "
            "for games enriched before ratings were cached."
        )
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Fetch ratings for the selected ready games through IGDB.",
    )
    return parser


def _batch_count(game_count: int) -> int:
    return (game_count + RATINGS_BATCH_SIZE - 1) // RATINGS_BATCH_SIZE


def _remaining_count(session_factory: SessionFactory) -> int:
    with session_factory() as database_session:
        return len(get_unchecked_rating_games(database_session))


def run_igdb_ratings_backfill_command(
    arguments: Sequence[str],
    *,
    session_factory: SessionFactory = SessionLocal,
    client_factory: ClientFactory = _igdb_client_factory,
    backfill_service: BackfillService = backfill_game_ratings,
    apply_lock: ApplyLock = igdb_enrichment_lock,
    output: TextIOBase = sys.stdout,
    error_output: TextIOBase = sys.stderr,
) -> int:
    """Report unchecked ready games or explicitly fetch their ratings."""
    options = _parser().parse_args(arguments)

    with session_factory() as database_session:
        selected = get_unchecked_rating_games(database_session)

    selection = {
        "selected_game_count": len(selected),
        "selected_batch_count": _batch_count(len(selected)),
    }
    if not options.apply:
        write_json_payload({"mode": "report-only", **selection}, output)
        return 0

    with apply_lock() as lock_acquired:
        if not lock_acquired:
            write_json_payload(
                {
                    "mode": "blocked",
                    "detail": "IGDB enrichment is already running.",
                    **selection,
                },
                error_output,
            )
            return 2

        updated_count = 0
        if selected:
            try:
                with client_factory() as client:
                    with session_factory() as database_session:
                        updated_count = backfill_service(
                            database_session,
                            client,
                            selected,
                        )
            except IGDBAPIError:
                write_json_payload(
                    {
                        "mode": "failed",
                        "detail": "The IGDB ratings backfill did not complete.",
                        **selection,
                        "remaining_game_count": _remaining_count(
                            session_factory
                        ),
                    },
                    error_output,
                )
                return 1

        write_json_payload(
            {
                "mode": "applied",
                **selection,
                "updated_game_count": updated_count,
                "remaining_game_count": _remaining_count(session_factory),
            },
            output,
        )
        return 0


def main() -> None:
    raise SystemExit(run_igdb_ratings_backfill_command(sys.argv[1:]))


if __name__ == "__main__":
    main()
