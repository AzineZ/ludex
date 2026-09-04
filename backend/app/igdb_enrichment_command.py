import argparse
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from io import TextIOBase
import json
import sys

from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.igdb_client import IGDBAPIError, IGDBClient
from app.igdb_coverage import (
    IGDBMetadataCoverage,
    get_igdb_metadata_coverage,
)
from app.igdb_enrichment import (
    enrich_game_metadata,
    get_pending_owned_steam_app_ids,
)
from app.igdb_matching import IGDBMatchResult


SessionFactory = Callable[[], Session]
ClientFactory = Callable[[], AbstractContextManager[IGDBClient]]
EnrichmentService = Callable[
    [Session, IGDBClient, Sequence[int]],
    list[IGDBMatchResult],
]


def _igdb_client_factory() -> IGDBClient:
    """Build the backend-only client used by an explicit apply run."""
    return IGDBClient(
        settings.igdb_client_id,
        settings.igdb_client_secret.get_secret_value(),
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Report or explicitly apply pending factual IGDB enrichment."
        )
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Enrich the selected owned pending games through IGDB.",
    )
    return parser


def _coverage_payload(
    coverage: IGDBMetadataCoverage,
) -> dict[str, int]:
    return {
        "total_owned_game_count": coverage.total_games,
        "pending_game_count": coverage.pending_games,
        "ready_game_count": coverage.ready_games,
        "missing_game_count": coverage.missing_games,
        "ambiguous_game_count": coverage.ambiguous_games,
        "attempted_game_count": coverage.attempted_games,
        "error_game_count": coverage.error_games,
    }


def _report_payload(
    coverage: IGDBMetadataCoverage,
    *,
    selected_pending_game_count: int,
) -> dict[str, object]:
    return {
        "mode": "report-only",
        **_coverage_payload(coverage),
        "selected_pending_game_count": selected_pending_game_count,
    }


def _write_payload(payload: dict[str, object], output: TextIOBase) -> None:
    json.dump(payload, output, indent=2, sort_keys=True)
    output.write("\n")


def run_igdb_enrichment_command(
    arguments: Sequence[str],
    *,
    session_factory: SessionFactory = SessionLocal,
    client_factory: ClientFactory = _igdb_client_factory,
    enrichment_service: EnrichmentService = enrich_game_metadata,
    output: TextIOBase = sys.stdout,
    error_output: TextIOBase = sys.stderr,
) -> int:
    """Report coverage or explicitly enrich deterministic pending games."""
    options = _parser().parse_args(arguments)

    with session_factory() as database_session:
        pending_ids = get_pending_owned_steam_app_ids(database_session)
        before = get_igdb_metadata_coverage(database_session)

    if not options.apply:
        _write_payload(
            _report_payload(
                before,
                selected_pending_game_count=len(pending_ids),
            ),
            output,
        )
        return 0

    processed_game_count = 0

    if pending_ids:
        try:
            with client_factory() as client:
                with session_factory() as database_session:
                    results = enrichment_service(
                        database_session,
                        client,
                        pending_ids,
                    )
            processed_game_count = len(results)
        except IGDBAPIError:
            with session_factory() as database_session:
                after = get_igdb_metadata_coverage(database_session)

            _write_payload(
                {
                    "mode": "failed",
                    "detail": "IGDB enrichment did not complete.",
                    "selected_pending_game_count": len(pending_ids),
                    "before": _coverage_payload(before),
                    "after": _coverage_payload(after),
                },
                error_output,
            )
            return 1

    with session_factory() as database_session:
        after = get_igdb_metadata_coverage(database_session)

    _write_payload(
        {
            "mode": "applied",
            "selected_pending_game_count": len(pending_ids),
            "processed_game_count": processed_game_count,
            "before": _coverage_payload(before),
            "after": _coverage_payload(after),
        },
        output,
    )
    return 0


def main() -> None:
    raise SystemExit(run_igdb_enrichment_command(sys.argv[1:]))


if __name__ == "__main__":
    main()
