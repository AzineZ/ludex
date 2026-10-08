"""Share the mechanics common to every bounded reranking evaluation."""

import argparse
from collections.abc import Callable, Iterable, Mapping
from dataclasses import asdict
from json import dumps
from pathlib import Path
from statistics import median
from typing import Protocol

from app.config import settings
from app.gemini.client import (
    GeminiAPIError,
    GeminiRateLimitError,
    GeminiUnavailableError,
)
from app.gemini.reranking.contracts import (
    RerankCandidate,
    RerankFilters,
    RerankResponse,
)
from app.gemini.reranking.reranker import (
    RerankRequestTooLarge,
    RerankResponseError,
)


EVALUATION_GENRE_ID = 31
EVALUATION_GENRE_NAME = "Adventure"

RankedRecommendation = tuple[int, str]


class _TimedResult(Protocol):
    status: str
    latency_ms: int


class _RankedResult(Protocol):
    recommendations: tuple[RankedRecommendation, ...]


class EvaluationReportMixin:
    """Derive the final verdict and JSON form shared by evaluation reports."""

    human_reason_review_pass: bool | None

    @property
    def automated_pass(self) -> bool:
        raise NotImplementedError

    @property
    def overall_pass(self) -> bool:
        return self.automated_pass and self.human_reason_review_pass is True

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["automated_pass"] = self.automated_pass
        value["overall_pass"] = self.overall_pass
        return value


def adventure_candidate(
    steam_app_id: int,
    title: str,
    summary: str,
    *,
    keywords: tuple[str, ...] = (),
    themes: tuple[str, ...] = (),
    game_modes: tuple[str, ...] = ("Single player",),
    completion: int | None = None,
) -> RerankCandidate:
    """Build one synthetic candidate in the fixed evaluation genre."""
    return RerankCandidate(
        steam_app_id=steam_app_id,
        title=title,
        summary=summary,
        genres=(EVALUATION_GENRE_NAME,),
        themes=themes,
        keywords=keywords,
        game_modes=game_modes,
        profile_playtime_minutes=0,
        normal_completion_minutes=completion,
    )


def adventure_request[RequestT](
    request_type: Callable[..., RequestT],
    prompt: str,
    candidates: tuple[RerankCandidate, ...],
) -> RequestT:
    """Build one unfiltered request in the fixed evaluation genre."""
    return request_type(
        prompt=prompt,
        selected_genre_id=EVALUATION_GENRE_ID,
        selected_genre_name=EVALUATION_GENRE_NAME,
        filters=RerankFilters(),
        candidates=candidates,
    )


def wait_for_pacing(
    last_call_started: float | None,
    *,
    requests_per_minute: int,
    clock: Callable[[], float],
    sleeper: Callable[[float], None],
) -> None:
    """Sleep only as long as needed to respect the evaluation call rate."""
    if last_call_started is None:
        return
    delay = 60 / requests_per_minute - (clock() - last_call_started)
    if delay > 0:
        sleeper(delay)


def elapsed_ms(clock: Callable[[], float], started: float) -> int:
    """Return whole milliseconds elapsed since one call started."""
    return round((clock() - started) * 1000)


def evaluation_error_code(error: Exception) -> str:
    """Name one handled provider or contract failure for a report."""
    if isinstance(error, GeminiRateLimitError):
        return "rate_limited"
    if isinstance(error, GeminiUnavailableError):
        return "unavailable"
    if isinstance(error, RerankRequestTooLarge):
        return "payload_too_large"
    if isinstance(error, RerankResponseError):
        return "invalid_response"
    if isinstance(error, GeminiAPIError):
        return error.reason_code or "provider_error"
    raise TypeError("Unsupported evaluation failure.") from error


def ranked_recommendations(
    response: RerankResponse,
) -> tuple[RankedRecommendation, ...]:
    """Reduce a response to the identities and reasons a report keeps."""
    return tuple(
        (item.steam_app_id, item.reasoning)
        for item in response.recommendations
    )


def top_three_ids(
    recommendations: tuple[RankedRecommendation, ...],
) -> tuple[int, ...]:
    """Return the identities of the first three recommendations."""
    return tuple(item[0] for item in recommendations[:3])


def avoids_forbidden_top_choice(
    top_ids: tuple[int, ...],
    forbidden_top_id: int | None,
) -> bool:
    """Report whether an injected instruction failed to take first place."""
    return (
        forbidden_top_id is None
        or not top_ids
        or top_ids[0] != forbidden_top_id
    )


def top_three_overlap(first: _RankedResult, second: _RankedResult) -> int:
    """Count identities shared by the top three of two repeated calls."""
    return len(
        set(top_three_ids(first.recommendations))
        & set(top_three_ids(second.recommendations))
    )


def latency_within_limits(
    results: Iterable[_TimedResult],
    *,
    maximum_ms: int,
    maximum_median_ms: int,
) -> bool:
    """Check every valid call and their median against latency ceilings."""
    latencies = [
        result.latency_ms for result in results if result.status == "valid"
    ]
    return (
        bool(latencies)
        and all(value <= maximum_ms for value in latencies)
        and median(latencies) <= maximum_median_ms
    )


def parse_report_arguments(
    parser: argparse.ArgumentParser,
) -> argparse.Namespace:
    """Parse a command that spends provider calls and writes one new report."""
    parser.add_argument("--report", type=Path, required=True)
    arguments = parser.parse_args()
    if settings.gemini_api_key is None:
        parser.error("GEMINI_API_KEY is not configured.")
    if arguments.report.exists():
        parser.error("The report already exists; refusing to overwrite it.")
    return arguments


def gemini_api_key() -> str:
    """Return the configured key after `parse_report_arguments` checked it."""
    if settings.gemini_api_key is None:
        raise RuntimeError("GEMINI_API_KEY is not configured.")
    return settings.gemini_api_key.get_secret_value()


def write_report(path: Path, report: EvaluationReportMixin) -> None:
    """Persist the complete evaluation report as stable JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        dumps(report.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def print_summary(summary: Mapping[str, object]) -> None:
    """Print one compact machine-readable command summary."""
    print(dumps(summary, sort_keys=True))
