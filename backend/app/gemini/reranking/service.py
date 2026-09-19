from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from time import perf_counter

from pydantic import Field, field_validator
from sqlalchemy.orm import Session

from app.gemini.client import (
    GeminiAPIError,
    GeminiAuthenticationError,
    GeminiClient,
    GeminiConnectionError,
    GeminiRateLimitError,
    GeminiResponseError,
    GeminiTimeoutError,
    GeminiUnavailableError,
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
from app.gemini.reranking.diagnostics import (
    create_diagnostic_reference,
    log_rerank_failure,
    log_rerank_success,
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
    diagnostic_reference: str | None = None


@dataclass(frozen=True)
class _FailureDiagnostic:
    category: str
    provider_status: int | None = None
    reason_code: str | None = None
    retry_after_seconds: int | None = None
    rate_limited: bool = False


def _classify_failure(
    error: GeminiAPIError | RerankRequestTooLarge | RerankResponseError,
) -> _FailureDiagnostic:
    """Map typed failures to a stable, allowlisted diagnostic category."""
    if isinstance(error, GeminiTimeoutError):
        return _FailureDiagnostic("timeout", reason_code=error.reason_code)
    if isinstance(error, GeminiConnectionError):
        return _FailureDiagnostic(
            "connection_error", reason_code=error.reason_code
        )
    if isinstance(error, GeminiAuthenticationError):
        return _FailureDiagnostic(
            "authentication_rejected",
            provider_status=error.status_code,
            reason_code=error.reason_code,
        )
    if isinstance(error, GeminiRateLimitError):
        return _FailureDiagnostic(
            "rate_limited",
            provider_status=error.status_code,
            reason_code=error.reason_code,
            retry_after_seconds=error.retry_after_seconds,
            rate_limited=True,
        )
    if isinstance(error, GeminiResponseError):
        return _FailureDiagnostic(
            "invalid_response",
            provider_status=error.status_code,
            reason_code=error.reason_code,
        )
    if isinstance(error, GeminiUnavailableError):
        return _FailureDiagnostic(
            "provider_unavailable",
            provider_status=error.status_code,
            reason_code=error.reason_code,
        )
    if isinstance(error, GeminiAPIError):
        return _FailureDiagnostic(
            "provider_rejected",
            provider_status=error.status_code,
            reason_code=error.reason_code,
        )
    if isinstance(error, RerankRequestTooLarge):
        return _FailureDiagnostic(
            "request_too_large", reason_code="local_request_byte_limit"
        )
    return _FailureDiagnostic(
        "invalid_response", reason_code="rerank_contract"
    )


def _duration_ms(started_at: float | None) -> int:
    if started_at is None:
        return 0
    return max(0, round((perf_counter() - started_at) * 1_000))


def _failed_result(
    *,
    eligible_count: int,
    failure_category: str,
    model_id: str | None,
    request_bytes: int | None,
    started_at: float | None = None,
    provider_status: int | None = None,
    reason_code: str | None = None,
    retry_after_seconds: int | None = None,
    rate_limited: bool = False,
) -> RerankAssistantResult:
    reference = create_diagnostic_reference()
    log_rerank_failure(
        reference=reference,
        failure_category=failure_category,
        model_id=model_id,
        candidate_count=eligible_count,
        request_bytes=request_bytes,
        duration_ms=_duration_ms(started_at),
        provider_status=provider_status,
        reason_code=reason_code,
        retry_after_seconds=retry_after_seconds,
    )
    message = (
        "Ludex AI has reached Gemini's current usage limit. "
        "Please try again tomorrow, or use guided recommendations now."
        if rate_limited
        else (
            "AI recommendations are temporarily unavailable. "
            "Try guided recommendations instead."
        )
    )
    return RerankAssistantResult(
        status=RerankAssistantStatus.UNAVAILABLE,
        eligible_count=eligible_count,
        message=message,
        diagnostic_reference=reference,
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
    if pool.request is None:
        raise RuntimeError("A ready candidate pool requires a request snapshot.")
    request_bytes = rerank_user_prompt_size_bytes(pool.request)
    if runtime is None:
        return _failed_result(
            eligible_count=pool.eligible_count,
            failure_category="not_configured",
            model_id=None,
            request_bytes=request_bytes,
        )
    if request_bytes > MAX_RERANK_REQUEST_BYTES:
        return _failed_result(
            eligible_count=pool.eligible_count,
            failure_category="request_too_large",
            model_id=runtime.model_id,
            request_bytes=request_bytes,
            reason_code="local_request_byte_limit",
        )

    started_at = perf_counter()
    try:
        response, metadata = rerank(
            runtime.client,
            model_id=runtime.model_id,
            request=pool.request,
        )
    except (
        GeminiAPIError,
        RerankRequestTooLarge,
        RerankResponseError,
    ) as error:
        diagnostic = _classify_failure(error)
        return _failed_result(
            eligible_count=pool.eligible_count,
            failure_category=diagnostic.category,
            model_id=runtime.model_id,
            request_bytes=request_bytes,
            started_at=started_at,
            provider_status=diagnostic.provider_status,
            reason_code=diagnostic.reason_code,
            retry_after_seconds=diagnostic.retry_after_seconds,
            rate_limited=diagnostic.rate_limited,
        )

    log_rerank_success(
        model_id=runtime.model_id,
        candidate_count=pool.eligible_count,
        request_bytes=request_bytes,
        duration_ms=_duration_ms(started_at),
        input_tokens=metadata.input_tokens,
        output_tokens=metadata.output_tokens,
        total_tokens=metadata.total_tokens,
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
