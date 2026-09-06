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
)
from app.recommendations.api.schemas import (
    FinalRecommendationResponse,
    RecommendationRefinementRequest,
    to_final_recommendation_response,
)
from app.recommendations.contracts import RecommendationPreference
from app.recommendations.preference_validation import PreferenceValidationError
from app.recommendations.service import recommend_cached_games
from app.sessions.http import require_access_session
from app.sessions.service import ActiveAccessSession


router = create_recommendation_api_router()


def create_final_recommendations(
    preference: RecommendationPreference,
    access_session: Annotated[
        ActiveAccessSession,
        Depends(require_access_session),
    ],
    database_session: Annotated[
        Session,
        Depends(get_database_session),
    ],
) -> FinalRecommendationResponse:
    """Return final recommendations from one cached owned library."""
    try:
        result = recommend_cached_games(
            database_session,
            profile_id=access_session.profile_id,
            preference=preference,
        )
    except PreferenceValidationError as error:
        raise_preference_validation_error(error)

    return to_final_recommendation_response(result)


@router.post(
    "/refine",
    response_model=FinalRecommendationResponse,
    responses=STANDARD_ERROR_RESPONSES,
)
def refine_final_recommendations(
    refinement: RecommendationRefinementRequest,
    access_session: Annotated[
        ActiveAccessSession,
        Depends(require_access_session),
    ],
    database_session: Annotated[
        Session,
        Depends(get_database_session),
    ],
) -> FinalRecommendationResponse:
    """Return a new cached result excluding session-rejected games."""
    try:
        result = recommend_cached_games(
            database_session,
            profile_id=access_session.profile_id,
            preference=refinement.preference,
            session_excluded_steam_app_ids=frozenset(
                refinement.rejected_steam_app_ids
            ),
        )
    except PreferenceValidationError as error:
        raise_preference_validation_error(error)

    return to_final_recommendation_response(result)
