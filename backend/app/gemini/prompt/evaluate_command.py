import argparse
from json import dumps, loads
from pathlib import Path

from app.config import settings
from app.gemini.client import GeminiClient
from app.gemini.prompt.evaluation import (
    PromptEvaluationReport,
    run_prompt_evaluation,
)


APPROVED_MODELS = {
    "gemini-3.5-flash-lite": 10,
    "gemini-3.6-flash": 4,
}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run one bounded local prompt-model evaluation."
    )
    parser.add_argument("--model", choices=tuple(APPROVED_MODELS), required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Continue the exact prefix already stored in --report.",
    )
    arguments = parser.parse_args()
    if settings.gemini_api_key is None:
        parser.error("GEMINI_API_KEY is not configured.")

    prior_report = None
    if arguments.resume:
        if not arguments.report.is_file():
            parser.error("The report does not exist and cannot be resumed.")
        try:
            raw_report = loads(arguments.report.read_text(encoding="utf-8"))
            if not isinstance(raw_report, dict):
                raise ValueError
            prior_report = PromptEvaluationReport.from_dict(raw_report)
        except (OSError, ValueError):
            parser.error("The report is invalid and cannot be resumed.")

    with GeminiClient(settings.gemini_api_key.get_secret_value()) as client:
        report = run_prompt_evaluation(
            client,
            model_id=arguments.model,
            requests_per_minute=APPROVED_MODELS[arguments.model],
            prior_report=prior_report,
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
                "overall_pass": report.overall_pass,
                "stopped_early": report.stopped_early,
            },
            sort_keys=True,
        )
    )
    return 0 if not report.stopped_early else 1


if __name__ == "__main__":
    raise SystemExit(main())
