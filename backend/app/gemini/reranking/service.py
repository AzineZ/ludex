from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from pydantic import Field, field_validator
from sqlalchemy.orm import Session

from app.gemini.client import GeminiAPIError, GeminiClient, GeminiRateLimitError
from app.gemini.prompt.quota import (
    PromptQuotaExceeded,
    PromptQuotaPolicy,
    complete_prompt_reservation,
    open_prompt_provider_circuit,
    reserve_prompt_attempt,
    reserve_prompt_message,
)
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
    RerankRequestTooLarge,
    RerankResponseError,
    rerank_with_metadata,
)
from app.recommendations.contracts import PositiveIdentifier


RERANK_RESERVATION_LEASE = timedelta(seconds=90)
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
    quota_policy: PromptQuotaPolicy


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
    reason: str


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


def recommend_with_gemini(
    session: Session,
    *,
    access_session_id: int,
    profile_id: int,
    submission: RerankSubmission,
    runtime: GeminiRerankRuntime | None,
    now: datetime,
    rerank: RerankCall = rerank_with_metadata,
) -> RerankAssistantResult:
    """Run at most one guarded provider call over one immutable snapshot."""
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

    reservation_id: str | None = None
    try:
        reservation = reserve_prompt_message(
            session,
            access_session_id=access_session_id,
            now=now,
            lease_duration=RERANK_RESERVATION_LEASE,
        )
        reservation_id = reservation.reservation_id
        reserve_prompt_attempt(
            session,
            reservation_id=reservation_id,
            policy=runtime.quota_policy,
            now=now,
        )
        response, _metadata = rerank(
            runtime.client,
            model_id=runtime.model_id,
            request=pool.request,
        )
    except GeminiRateLimitError as error:
        if reservation_id is not None:
            open_prompt_provider_circuit(
                session,
                reservation_id=reservation_id,
                now=now,
                retry_after_seconds=error.retry_after_seconds,
            )
        return _unavailable(pool.eligible_count)
    except (
        PromptQuotaExceeded,
        GeminiAPIError,
        RerankRequestTooLarge,
        RerankResponseError,
    ):
        return _unavailable(pool.eligible_count)
    finally:
        if reservation_id is not None:
            complete_prompt_reservation(
                session,
                reservation_id=reservation_id,
                now=now,
            )

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
            reason=recommendation.reason,
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
