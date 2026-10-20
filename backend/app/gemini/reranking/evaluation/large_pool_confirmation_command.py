"""Operator command for the Phase F large-pool confirmation run."""

import argparse
from pathlib import Path

from app.config import settings
from app.database import SessionLocal
from app.gemini.client import GeminiClient
from app.gemini.reranking.evaluation.harness import print_summary, write_report
from app.gemini.reranking.evaluation.large_pool_confirmation import (
    load_catalogue,
    load_headline_scores,
    plan_request_sizes,
    run_confirmation,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Measure (--dry-run) or run the approved 8-call confirmation."
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report", type=Path)
    arguments = parser.parse_args()

    with SessionLocal() as session:
        catalogue = load_catalogue(session)
        scores = load_headline_scores(session)
        session.rollback()

    if arguments.dry_run:
        print_summary(
            {
                "mode": "dry-run",
                "real_games": len(catalogue),
                "scored_games": len(scores),
                "request_bytes": plan_request_sizes(catalogue, scores),
            }
        )
        return 0
    if arguments.report is None:
        parser.error("--report is required unless --dry-run is given.")
    if arguments.report.exists():
        parser.error("The report already exists; refusing to overwrite it.")
    if settings.gemini_api_key is None:
        parser.error("GEMINI_API_KEY is not configured.")

    with GeminiClient(settings.gemini_api_key.get_secret_value()) as client:
        report = run_confirmation(client, catalogue, scores)
    write_report(arguments.report, report)
    print_summary(
        {
            "mode": "applied",
            "call_count": report.call_count,
            "statuses": [result.status for result in report.results],
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
