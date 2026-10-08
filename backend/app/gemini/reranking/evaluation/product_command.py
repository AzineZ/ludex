"""Operator command for the ten-call product-contract evaluation."""

import argparse

from app.gemini.client import GeminiClient
from app.gemini.reranking.evaluation.harness import (
    gemini_api_key,
    parse_report_arguments,
    print_summary,
    write_report,
)
from app.gemini.reranking.evaluation.product import run_rerank_evaluation


MODEL_PACING_LIMITS = {
    "gemini-3.5-flash-lite": 10,
    "gemini-3.6-flash": 4,
}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run one explicitly approved bounded reranking evaluation."
    )
    parser.add_argument(
        "--model",
        choices=tuple(MODEL_PACING_LIMITS),
        required=True,
    )
    arguments = parse_report_arguments(parser)

    with GeminiClient(gemini_api_key()) as client:
        report = run_rerank_evaluation(
            client,
            model_id=arguments.model,
            requests_per_minute=MODEL_PACING_LIMITS[arguments.model],
        )

    write_report(arguments.report, report)
    print_summary(
        {
            "model_id": report.model_id,
            "call_count": report.call_count,
            "automated_pass": report.automated_pass,
            "human_reason_review_pass": report.human_reason_review_pass,
            "overall_pass": report.overall_pass,
            "stopped_early": report.stopped_early,
        }
    )
    return 0 if not report.stopped_early else 1


if __name__ == "__main__":
    raise SystemExit(main())
