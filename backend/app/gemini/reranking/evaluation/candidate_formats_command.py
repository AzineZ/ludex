"""Operator command for the Checkpoint 15 E3 candidate-format evaluation."""

import argparse
from collections import Counter
from pathlib import Path

from app.config import settings
from app.database import SessionLocal
from app.gemini.client import GeminiClient
from app.gemini.reranking.evaluation.candidate_formats import (
    FORMAT_EVALUATION_MODEL,
    load_catalogue,
    plan_calls,
    run_format_evaluation,
)
from app.gemini.reranking.evaluation.harness import print_summary, write_report


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Measure (--dry-run) or explicitly run the approved 28-call "
            "candidate-format evaluation."
        )
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report", type=Path)
    arguments = parser.parse_args()

    with SessionLocal() as session:
        catalogue = load_catalogue(session)
        session.rollback()

    plans = plan_calls(catalogue)
    if arguments.dry_run:
        print_summary(
            {
                "mode": "dry-run",
                "real_catalogue_size": len(catalogue),
                "sendable_calls": sum(plan.sendable for plan in plans),
                "too_large": sum(not plan.sendable for plan in plans),
                "max_bytes_by_format_and_size": {
                    f"{plan.candidate_format}@{plan.size}": plan.request_bytes
                    for plan in plans
                    if plan.prompt_id == "horror"
                },
                "max_estimated_input_tokens": max(
                    plan.estimated_input_tokens
                    for plan in plans
                    if plan.sendable
                ),
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
        report = run_format_evaluation(
            client,
            catalogue,
            model_id=FORMAT_EVALUATION_MODEL,
        )

    write_report(arguments.report, report)
    print_summary(
        {
            "mode": "applied",
            "call_count": report.call_count,
            "statuses": dict(Counter(result.status for result in report.results)),
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
