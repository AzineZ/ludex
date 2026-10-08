"""Operator command for the five-call 100-game rich-context evaluation."""

import argparse

from app.gemini.client import GeminiClient
from app.gemini.reranking.evaluation.ceiling import (
    CEILING_EVALUATION_MODEL,
    RICH_CONTEXT_CANDIDATE_COUNT,
    RICH_CONTEXT_MAX_INPUT_TOKENS,
    RICH_CONTEXT_MAX_REQUEST_BYTES,
    audit_rich_context_fixture_payloads,
    run_rich_context_evaluation,
)
from app.gemini.reranking.evaluation.harness import (
    gemini_api_key,
    parse_report_arguments,
    print_summary,
    write_report,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the approved 100-game rich-context evaluation."
    )
    arguments = parse_report_arguments(parser)

    payloads = audit_rich_context_fixture_payloads()
    if not payloads or max(payloads) > RICH_CONTEXT_MAX_REQUEST_BYTES:
        parser.error("The rich-context fixture exceeds its approved byte limit.")

    with GeminiClient(gemini_api_key()) as client:
        report = run_rich_context_evaluation(client)

    write_report(arguments.report, report)
    print_summary(
        {
            "model_id": CEILING_EVALUATION_MODEL,
            "candidate_count": RICH_CONTEXT_CANDIDATE_COUNT,
            "projection": report.projection,
            "call_count": report.call_count,
            "maximum_request_bytes": max(payloads),
            "maximum_input_tokens": RICH_CONTEXT_MAX_INPUT_TOKENS,
            "automated_pass": report.automated_pass,
            "human_reason_review_pass": report.human_reason_review_pass,
            "overall_pass": report.overall_pass,
            "stopped_early": report.stopped_early,
        }
    )
    return 0 if not report.stopped_early else 1


if __name__ == "__main__":
    raise SystemExit(main())
