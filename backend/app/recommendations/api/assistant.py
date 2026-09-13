from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import Depends, status
from pydantic import Field, field_validator
from sqlalchemy.orm import Session

from app.database import get_database_session
from app.gemini.dependencies import get_gemini_rerank_runtime
from app.gemini.reranking.candidate_pool import (
    RerankFacetOption,
    RerankFilterOptions,
    RerankFilterUnavailableError,
    RerankGenreOption,
    RerankGenreUnavailableError,
    list_available_rerank_genres,
    list_rerank_filter_options,
)
from app.gemini.reranking.contracts import (
    MAX_RERANK_CANDIDATES,
    MAX_RERANK_SESSION_EXCLUSIONS,
)
from app.gemini.reranking.service import (
    GeminiRerankRuntime,
    RerankAssistantItem,
    RerankAssistantResult,
    RerankAssistantStatus,
    RerankSubmission,
    recommend_with_gemini,
)
from app.recommendations.api.common import (
    STANDARD_ERROR_RESPONSES,
    create_recommendation_api_router,
)
from app.recommendations.api.schemas import (
    RecommendationErrorCode,
    RecommendationHTTPModel,
)
from app.recommendations.api.validation import RecommendationHTTPError
from app.recommendations.contracts import (
    CompletionMinutes,
    PlayStatus,
    PositiveIdentifier,
)
from app.sessions.http import require_access_session
from app.sessions.service import ActiveAccessSession


router = create_recommendation_api_router()


class RerankOptionResponse(RecommendationHTTPModel):
    igdb_id: int
    name: str
    eligible_count: int


class RerankGenreOptionsResponse(RecommendationHTTPModel):
    items: tuple[RerankOptionResponse, ...]


class RerankFilterContextRequest(RecommendationHTTPModel):
    selected_genre_id: int = Field(strict=True, gt=0)
    play_status: PlayStatus
    maximum_completion_minutes: CompletionMinutes | None
    rejected_steam_app_ids: tuple[PositiveIdentifier, ...] = ()

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


class RerankFilterOptionsResponse(RecommendationHTTPModel):
    themes: tuple[RerankOptionResponse, ...]
    game_modes: tuple[RerankOptionResponse, ...]


class RerankAssistantItemResponse(RecommendationHTTPModel):
    rank: int
    steam_app_id: int
    title: str
    cover_url: str | None
    profile_playtime_minutes: int
    normal_completion_seconds: int | None
    reason: str
    reason_source: Literal["ai_generated"] = "ai_generated"


class RerankAssistantResponse(RecommendationHTTPModel):
    status: RerankAssistantStatus
    eligible_count: int
    candidate_limit: int = MAX_RERANK_CANDIDATES
    items: tuple[RerankAssistantItemResponse, ...]
    message: str | None
    guided_fallback_available: Literal[True] = True


def _option(item: RerankGenreOption | RerankFacetOption) -> RerankOptionResponse:
    return RerankOptionResponse(
        igdb_id=item.igdb_id,
        name=item.name,
        eligible_count=item.eligible_count,
    )


def _filter_response(options: RerankFilterOptions) -> RerankFilterOptionsResponse:
    return RerankFilterOptionsResponse(
        themes=tuple(_option(item) for item in options.themes),
        game_modes=tuple(_option(item) for item in options.game_modes),
    )


def _item(item: RerankAssistantItem) -> RerankAssistantItemResponse:
    return RerankAssistantItemResponse(
        rank=item.rank,
        steam_app_id=item.steam_app_id,
        title=item.title,
        cover_url=item.cover_url,
        profile_playtime_minutes=item.profile_playtime_minutes,
        normal_completion_seconds=item.normal_completion_seconds,
        reason=item.reason,
    )


def _assistant_response(result: RerankAssistantResult) -> RerankAssistantResponse:
    return RerankAssistantResponse(
        status=result.status,
        eligible_count=result.eligible_count,
        items=tuple(_item(item) for item in result.items),
        message=result.message,
    )


def _raise_unavailable_option(
    error: RerankGenreUnavailableError | RerankFilterUnavailableError,
) -> None:
    raise RecommendationHTTPError(
        status_code=status.HTTP_409_CONFLICT,
        code=RecommendationErrorCode.ASSISTANT_OPTION_UNAVAILABLE,
        field=error.field,
        message=str(error),
    ) from error


@router.get(
    "/assistant/genres",
    response_model=RerankGenreOptionsResponse,
    responses=STANDARD_ERROR_RESPONSES,
)
def get_assistant_genres(
    access_session: Annotated[
        ActiveAccessSession, Depends(require_access_session)
    ],
    database_session: Annotated[Session, Depends(get_database_session)],
) -> RerankGenreOptionsResponse:
    genres = list_available_rerank_genres(
        database_session, profile_id=access_session.profile_id
    )
    return RerankGenreOptionsResponse(
        items=tuple(_option(item) for item in genres)
    )


@router.post(
    "/assistant/filters",
    response_model=RerankFilterOptionsResponse,
    responses=STANDARD_ERROR_RESPONSES,
)
def get_assistant_filter_options(
    request: RerankFilterContextRequest,
    access_session: Annotated[
        ActiveAccessSession, Depends(require_access_session)
    ],
    database_session: Annotated[Session, Depends(get_database_session)],
) -> RerankFilterOptionsResponse:
    try:
        options = list_rerank_filter_options(
            database_session,
            profile_id=access_session.profile_id,
            selected_genre_id=request.selected_genre_id,
            play_status=request.play_status,
            maximum_completion_minutes=request.maximum_completion_minutes,
            session_excluded_steam_app_ids=frozenset(
                request.rejected_steam_app_ids
            ),
        )
    except RerankGenreUnavailableError as error:
        _raise_unavailable_option(error)
    return _filter_response(options)


@router.post(
    "/assistant",
    response_model=RerankAssistantResponse,
    responses=STANDARD_ERROR_RESPONSES,
)
def create_assistant_recommendations(
    submission: RerankSubmission,
    access_session: Annotated[
        ActiveAccessSession, Depends(require_access_session)
    ],
    database_session: Annotated[Session, Depends(get_database_session)],
    runtime: Annotated[
        GeminiRerankRuntime | None, Depends(get_gemini_rerank_runtime)
    ],
) -> RerankAssistantResponse:
    try:
        result = recommend_with_gemini(
            database_session,
            access_session_id=access_session.id,
            profile_id=access_session.profile_id,
            submission=submission,
            runtime=runtime,
            now=datetime.now(UTC),
        )
    except (RerankGenreUnavailableError, RerankFilterUnavailableError) as error:
        _raise_unavailable_option(error)
    return _assistant_response(result)
