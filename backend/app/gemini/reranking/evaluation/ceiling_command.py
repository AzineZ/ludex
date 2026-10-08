"""Operator command for one five-call candidate-count ceiling evaluation."""

import argparse

from app.gemini.client import GeminiClient
from app.gemini.reranking.evaluation.ceiling import (
    CEILING_EVALUATION_MODEL,
    CEILING_EVALUATION_SIZES,
    run_ceiling_evaluation,
)
from app.gemini.reranking.evaluation.harness import (
    gemini_api_key,
    parse_report_arguments,
    print_summary,
    write_report,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run one explicitly approved reranking ceiling evaluation."
    )
    parser.add_argument(
        "--candidate-count",
        type=int,
        choices=CEILING_EVALUATION_SIZES,
        required=True,
    )
    arguments = parse_report_arguments(parser)

    with GeminiClient(gemini_api_key()) as client:
        report = run_ceiling_evaluation(
            client,
            candidate_count=arguments.candidate_count,
        )

    write_report(arguments.report, report)
    print_summary(
        {
            "model_id": CEILING_EVALUATION_MODEL,
            "candidate_count": report.candidate_count,
            "projection": report.projection,
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
