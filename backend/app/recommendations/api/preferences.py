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
from app.recommendations.contracts import RecommendationPreference
from app.recommendations.preference_validation import (
    PreferenceValidationError,
    validate_preference,
)
from app.sessions.http import require_access_session
from app.sessions.service import ActiveAccessSession


router = create_recommendation_api_router()


@router.post(
    "/preferences/validate",
    response_model=RecommendationPreference,
    responses=STANDARD_ERROR_RESPONSES,
)
def validate_submitted_preference(
    preference: RecommendationPreference,
    access_session: Annotated[
        ActiveAccessSession,
        Depends(require_access_session),
    ],
    database_session: Annotated[
        Session,
        Depends(get_database_session),
    ],
) -> RecommendationPreference:
    """Validate and return one canonical recommendation preference."""
    try:
        validated = validate_preference(
            database_session,
            access_session.profile_id,
            preference,
        )
    except PreferenceValidationError as error:
        raise_preference_validation_error(error)

    return validated.preference
