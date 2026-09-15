from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from pydantic import Field, field_validator
from sqlalchemy.orm import Session

from app.gemini.client import GeminiAPIError, GeminiClient, GeminiRateLimitError
from app.gemini.reranking.candidate_pool import (
    RerankCandidatePoolState,
    build_rerank_candidate_pool,
)
from app.gemini.reranking.contracts import (
    MAX_RERANK_SESSION_EXCLUSIONS,
    FrozenContract,
    RerankFilters,
)
from app.gemini.reranking.reranker import (
    MAX_RERANK_REQUEST_BYTES,
    RerankRequestTooLarge,
    RerankResponseError,
    rerank_user_prompt_size_bytes,
    rerank_with_metadata,
)
from app.recommendations.contracts import PositiveIdentifier


RerankCall = Callable[..., object]


class RerankSubmission(FrozenContract):
    """Carry one browser submission into the guarded runtime path."""

    prompt: str = Field(min_length=1, max_length=500)
    selected_genre_id: int = Field(strict=True, gt=0)
    filters: RerankFilters
    rejected_steam_app_ids: tuple[PositiveIdentifier, ...] = ()

    @field_validator("prompt")
    @classmethod
    def normalize_prompt(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Prompt text must not be blank.")
        return normalized

    @field_validator("rejected_steam_app_ids")
    @classmethod
    def validate_rejections(cls, values: tuple[int, ...]) -> tuple[int, ...]:
        if len(values) > MAX_RERANK_SESSION_EXCLUSIONS:
            raise ValueError(
                "A session may exclude at most 30 rejected games."
            )
        if len(values) != len(set(values)):
            raise ValueError("Rejected game IDs must be unique.")
        return values


@dataclass(frozen=True)
class GeminiRerankRuntime:
    client: GeminiClient
    model_id: str


class RerankAssistantStatus(StrEnum):
    RANKED = "ranked"
    NO_MATCH = "no_match"
    EMPTY = "empty"
    NEEDS_REFINEMENT = "needs_refinement"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class RerankAssistantItem:
    rank: int
    steam_app_id: int
    title: str
    cover_url: str | None
    profile_playtime_minutes: int
    normal_completion_seconds: int | None
    summary: str
    reasoning: str


@dataclass(frozen=True)
class RerankAssistantResult:
    status: RerankAssistantStatus
    eligible_count: int
    items: tuple[RerankAssistantItem, ...] = ()
    message: str | None = None


def _unavailable(eligible_count: int) -> RerankAssistantResult:
    return RerankAssistantResult(
        status=RerankAssistantStatus.UNAVAILABLE,
        eligible_count=eligible_count,
        message=(
            "AI recommendations are temporarily unavailable. "
            "Try guided recommendations instead."
        ),
    )


def _rate_limited(eligible_count: int) -> RerankAssistantResult:
    return RerankAssistantResult(
        status=RerankAssistantStatus.UNAVAILABLE,
        eligible_count=eligible_count,
        message=(
            "Ludex AI has reached Gemini's current usage limit. "
            "Please try again tomorrow, or use guided recommendations now."
        ),
    )


def recommend_with_gemini(
    session: Session,
    *,
    profile_id: int,
    submission: RerankSubmission,
    runtime: GeminiRerankRuntime | None,
    rerank: RerankCall = rerank_with_metadata,
) -> RerankAssistantResult:
    """Run one provider-enforced call over one immutable candidate snapshot."""
    pool = build_rerank_candidate_pool(
        session,
        profile_id=profile_id,
        prompt=submission.prompt,
        selected_genre_id=submission.selected_genre_id,
        filters=submission.filters,
        session_excluded_steam_app_ids=frozenset(
            submission.rejected_steam_app_ids
        ),
    )
    if pool.state is RerankCandidatePoolState.EMPTY:
        return RerankAssistantResult(
            status=RerankAssistantStatus.EMPTY,
            eligible_count=0,
            message=(
                "No games match those filters. Adjust a filter or try guided "
                "recommendations."
            ),
        )
    if pool.state is RerankCandidatePoolState.NEEDS_REFINEMENT:
        return RerankAssistantResult(
            status=RerankAssistantStatus.NEEDS_REFINEMENT,
            eligible_count=pool.eligible_count,
            message=(
                "Choose another factual filter so every eligible game can be "
                "considered."
            ),
        )
    if runtime is None:
        return _unavailable(pool.eligible_count)
    if pool.request is None:
        raise RuntimeError("A ready candidate pool requires a request snapshot.")
    if rerank_user_prompt_size_bytes(pool.request) > MAX_RERANK_REQUEST_BYTES:
        return _unavailable(pool.eligible_count)

    try:
        response, _metadata = rerank(
            runtime.client,
            model_id=runtime.model_id,
            request=pool.request,
        )
    except GeminiRateLimitError:
        return _rate_limited(pool.eligible_count)
    except (
        GeminiAPIError,
        RerankRequestTooLarge,
        RerankResponseError,
    ):
        return _unavailable(pool.eligible_count)

    if response.status.value == "no_match":
        return RerankAssistantResult(
            status=RerankAssistantStatus.NO_MATCH,
            eligible_count=pool.eligible_count,
            message=response.no_match_reason,
        )

    presentations = {
        item.steam_app_id: item for item in pool.presentations
    }
    items = tuple(
        RerankAssistantItem(
            rank=rank,
            steam_app_id=recommendation.steam_app_id,
            title=presentations[recommendation.steam_app_id].title,
            cover_url=presentations[recommendation.steam_app_id].cover_url,
            profile_playtime_minutes=presentations[
                recommendation.steam_app_id
            ].profile_playtime_minutes,
            normal_completion_seconds=presentations[
                recommendation.steam_app_id
            ].normal_completion_seconds,
            summary=recommendation.summary,
            reasoning=recommendation.reasoning,
        )
        for rank, recommendation in enumerate(
            response.recommendations, start=1
        )
    )
    return RerankAssistantResult(
        status=RerankAssistantStatus.RANKED,
        eligible_count=pool.eligible_count,
        items=items,
    )
