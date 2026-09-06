from fastapi import APIRouter, status

from app.recommendations.api.schemas import RecommendationErrorResponse
from app.recommendations.api.validation import RecommendationAPIRoute


def _error_documentation(description: str) -> dict[str, object]:
    """Build one OpenAPI error-response declaration."""
    return {
        "model": RecommendationErrorResponse,
        "description": description,
    }


NOT_FOUND_RESPONSE = _error_documentation(
    "The selected profile or reference does not exist."
)
CONFLICT_RESPONSE = _error_documentation(
    "The reference's current metadata state prevents the operation."
)
UNPROCESSABLE_RESPONSE = _error_documentation(
    "The submitted path, query, or preference is invalid."
)
SERVICE_UNAVAILABLE_RESPONSE = _error_documentation(
    "The database is temporarily unavailable."
)
SESSION_REQUIRED_RESPONSE = {
    "description": "A valid Steam access session is required.",
}

STANDARD_ERROR_RESPONSES = {
    status.HTTP_401_UNAUTHORIZED: SESSION_REQUIRED_RESPONSE,
    status.HTTP_404_NOT_FOUND: NOT_FOUND_RESPONSE,
    status.HTTP_409_CONFLICT: CONFLICT_RESPONSE,
    status.HTTP_422_UNPROCESSABLE_CONTENT: UNPROCESSABLE_RESPONSE,
    status.HTTP_503_SERVICE_UNAVAILABLE: SERVICE_UNAVAILABLE_RESPONSE,
}

REFERENCE_SEARCH_ERROR_RESPONSES = {
    status_code: response
    for status_code, response in STANDARD_ERROR_RESPONSES.items()
    if status_code != status.HTTP_409_CONFLICT
}


def create_recommendation_api_router() -> APIRouter:
    """Create a router with recommendation-scoped error translation."""
    return APIRouter(route_class=RecommendationAPIRoute)
