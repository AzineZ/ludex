import argparse
from json import dumps
from pathlib import Path

from app.config import settings
from app.database import SessionLocal
from app.gemini.client import GeminiClient
from app.gemini.traits.evaluation import (
    TRAIT_EVALUATION_MAX_CALLS,
    load_trait_evaluation_games,
    run_trait_evaluation,
)


APPROVED_MODELS = {
    "gemini-3.5-flash-lite": 10,
    "gemini-3.6-flash": 4,
}
TRAIT_EVALUATION_TIMEOUT_SECONDS = 120.0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run one bounded local trait-model evaluation."
    )
    parser.add_argument("--model", choices=tuple(APPROVED_MODELS), required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument(
        "--call-budget",
        type=int,
        choices=range(1, TRAIT_EVALUATION_MAX_CALLS + 1),
        default=TRAIT_EVALUATION_MAX_CALLS,
        help="Maximum calls for this run; never exceeds the approved ceiling.",
    )
    arguments = parser.parse_args()
    if settings.gemini_api_key is None:
        parser.error("GEMINI_API_KEY is not configured.")

    with SessionLocal() as session:
        games = load_trait_evaluation_games(session)
    with GeminiClient(
        settings.gemini_api_key.get_secret_value(),
        timeout_seconds=TRAIT_EVALUATION_TIMEOUT_SECONDS,
    ) as client:
        report = run_trait_evaluation(
            client,
            model_id=arguments.model,
            games=games,
            requests_per_minute=APPROVED_MODELS[arguments.model],
            maximum_calls=arguments.call_budget,
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
