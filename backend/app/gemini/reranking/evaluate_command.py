import argparse
from json import dumps
from pathlib import Path

from app.config import settings
from app.gemini.client import GeminiClient
from app.gemini.reranking.evaluation import run_rerank_evaluation


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
    parser.add_argument("--report", type=Path, required=True)
    arguments = parser.parse_args()
    if settings.gemini_api_key is None:
        parser.error("GEMINI_API_KEY is not configured.")
    if arguments.report.exists():
        parser.error("The report already exists; refusing to overwrite it.")

    with GeminiClient(settings.gemini_api_key.get_secret_value()) as client:
        report = run_rerank_evaluation(
            client,
            model_id=arguments.model,
            requests_per_minute=MODEL_PACING_LIMITS[arguments.model],
        )

    arguments.report.parent.mkdir(parents=True, exist_ok=True)
    arguments.report.write_text(
        dumps(report.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        dumps(
            {
                "model_id": report.model_id,
                "call_count": report.call_count,
                "automated_pass": report.automated_pass,
                "human_reason_review_pass": (
                    report.human_reason_review_pass
                ),
                "overall_pass": report.overall_pass,
                "stopped_early": report.stopped_early,
            },
            sort_keys=True,
        )
    )
    return 0 if not report.stopped_early else 1


if __name__ == "__main__":
    raise SystemExit(main())
