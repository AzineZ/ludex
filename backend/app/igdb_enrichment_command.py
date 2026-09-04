import argparse
from collections.abc import Callable, Sequence
from io import TextIOBase
import json
import sys

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.igdb_coverage import (
    IGDBMetadataCoverage,
    get_igdb_metadata_coverage,
)
from app.igdb_enrichment import get_pending_owned_steam_app_ids


SessionFactory = Callable[[], Session]


def _parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(
        description=(
            "Report pending factual IGDB enrichment without provider calls."
        )
    )


def _report_payload(
    coverage: IGDBMetadataCoverage,
    *,
    selected_pending_game_count: int,
) -> dict[str, object]:
    return {
        "mode": "report-only",
        "total_owned_game_count": coverage.total_games,
        "pending_game_count": coverage.pending_games,
        "ready_game_count": coverage.ready_games,
        "missing_game_count": coverage.missing_games,
        "ambiguous_game_count": coverage.ambiguous_games,
        "attempted_game_count": coverage.attempted_games,
        "error_game_count": coverage.error_games,
        "selected_pending_game_count": selected_pending_game_count,
    }


def run_igdb_enrichment_command(
    arguments: Sequence[str],
    *,
    session_factory: SessionFactory = SessionLocal,
    output: TextIOBase = sys.stdout,
) -> int:
    """Report deterministic pending owned-game coverage without providers."""
    _parser().parse_args(arguments)

    with session_factory() as database_session:
        pending_ids = get_pending_owned_steam_app_ids(database_session)
        coverage = get_igdb_metadata_coverage(database_session)

    json.dump(
        _report_payload(
            coverage,
            selected_pending_game_count=len(pending_ids),
        ),
        output,
        indent=2,
        sort_keys=True,
    )
    output.write("\n")
    return 0


def main() -> None:
    raise SystemExit(run_igdb_enrichment_command(sys.argv[1:]))


if __name__ == "__main__":
    main()
