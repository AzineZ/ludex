import argparse
from json import dumps
from pathlib import Path

from app.config import settings
from app.gemini.client import GeminiClient
from app.gemini.reranking.ceiling_evaluation import (
    CEILING_EVALUATION_MODEL,
    RICH_CONTEXT_CANDIDATE_COUNT,
    RICH_CONTEXT_MAX_INPUT_TOKENS,
    RICH_CONTEXT_MAX_REQUEST_BYTES,
    audit_rich_context_fixture_payloads,
    run_rich_context_evaluation,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the approved 100-game rich-context evaluation."
    )
    parser.add_argument("--report", type=Path, required=True)
    arguments = parser.parse_args()
    if settings.gemini_api_key is None:
        parser.error("GEMINI_API_KEY is not configured.")
    if arguments.report.exists():
        parser.error("The report already exists; refusing to overwrite it.")

    payloads = audit_rich_context_fixture_payloads()
    if not payloads or max(payloads) > RICH_CONTEXT_MAX_REQUEST_BYTES:
        parser.error("The rich-context fixture exceeds its approved byte limit.")

    with GeminiClient(settings.gemini_api_key.get_secret_value()) as client:
        report = run_rich_context_evaluation(client)

    arguments.report.parent.mkdir(parents=True, exist_ok=True)
    arguments.report.write_text(
        dumps(report.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        dumps(
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
            },
            sort_keys=True,
        )
    )
    return 0 if not report.stopped_early else 1


if __name__ == "__main__":
    raise SystemExit(main())
