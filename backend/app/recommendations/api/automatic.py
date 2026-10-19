from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.database import get_database_session
from app.recommendations.api.common import (
    STANDARD_ERROR_RESPONSES,
    create_recommendation_api_router,
)
from app.recommendations.api.errors import (
    raise_preference_validation_error,
    raise_reference_read_error,
)
from app.recommendations.api.schemas import (
    AutomaticRecommendationRequest,
    AutomaticRecommendationResponse,
    AutomaticRecommendationRowResponse,
    MoreLikeThisRequest,
    to_automatic_recommendation_response,
    to_automatic_row_response,
)
from app.recommendations.automatic import (
    recommend_automatic_rows,
    recommend_more_like_game,
)
from app.recommendations.preference_validation import PreferenceValidationError
from app.recommendations.reference_reads import (
    ReferenceMetadataUnavailableError,
    ReferenceNotOwnedError,
)
from app.sessions.http import require_access_session
from app.sessions.service import ActiveAccessSession


router = create_recommendation_api_router()


@router.post(
    "/automatic",
    response_model=AutomaticRecommendationResponse,
    responses=STANDARD_ERROR_RESPONSES,
)
def create_automatic_recommendations(
    request: AutomaticRecommendationRequest,
    access_session: Annotated[
        ActiveAccessSession,
        Depends(require_access_session),
    ],
    database_session: Annotated[
        Session,
        Depends(get_database_session),
    ],
) -> AutomaticRecommendationResponse:
    """Return one cached recommendation row per top played game."""
    try:
        recommendations = recommend_automatic_rows(
            database_session,
            profile_id=access_session.profile_id,
            constraints=request.constraints,
            rejected_steam_app_ids=frozenset(
                request.rejected_steam_app_ids
            ),
            wait_for_pending=request.wait_for_pending,
        )
    except PreferenceValidationError as error:
        raise_preference_validation_error(error)

    return to_automatic_recommendation_response(recommendations)


@router.post(
    "/automatic/more-like-this",
    response_model=AutomaticRecommendationRowResponse,
    responses=STANDARD_ERROR_RESPONSES,
)
def create_more_like_this_recommendations(
    request: MoreLikeThisRequest,
    access_session: Annotated[
        ActiveAccessSession,
        Depends(require_access_session),
    ],
    database_session: Annotated[
        Session,
        Depends(get_database_session),
    ],
) -> AutomaticRecommendationRowResponse:
    """Return one cached row using a shown game as the reference."""
    try:
        row = recommend_more_like_game(
            database_session,
            profile_id=access_session.profile_id,
            steam_app_id=request.steam_app_id,
            constraints=request.constraints,
            excluded_steam_app_ids=frozenset(
                request.excluded_steam_app_ids
            ),
        )
    except (
        ReferenceNotOwnedError,
        ReferenceMetadataUnavailableError,
    ) as error:
        raise_reference_read_error(error)
    except PreferenceValidationError as error:
        raise_preference_validation_error(error)

    return to_automatic_row_response(row)
