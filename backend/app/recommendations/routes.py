from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.orm import Session

from app.database import get_database_session
from app.recommendations.api_schemas import (
    FacetOptionResponse,
    KeywordSearchResponse,
    OwnedGameSearchResponse,
    OwnedGameSuggestionResponse,
    RecommendationErrorCode,
    RecommendationErrorResponse,
    ReferenceDetailsResponse,
    ReferenceFacetsResponse,
)
from app.recommendations.api_validation import (
    RecommendationAPIRoute,
    RecommendationHTTPError,
)
from app.recommendations.contracts import RecommendationPreference
from app.recommendations.preference_validation import (
    PreferenceValidationCode,
    PreferenceValidationError,
    validate_preference,
)
from app.recommendations.reference_reads import (
    FacetOption,
    InvalidSearchQueryError,
    OwnedGameSuggestion,
    ProfileNotFoundError,
    ReferenceDetails,
    ReferenceMetadataUnavailableError,
    ReferenceNotOwnedError,
    load_reference_details,
    search_owned_games,
    search_reference_keywords,
)


PositivePathIdentifier = Annotated[int, Path(gt=0)]
RequiredSearchQuery = Annotated[str, Query()]


def _error_documentation(
    description: str,
) -> dict[str, object]:
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


router = APIRouter(
    prefix="/profiles/{profile_id}/recommendations",
    tags=["recommendations"],
    route_class=RecommendationAPIRoute,
)


@router.get(
    "/references",
    response_model=OwnedGameSearchResponse,
    responses={
        status.HTTP_404_NOT_FOUND: NOT_FOUND_RESPONSE,
        status.HTTP_422_UNPROCESSABLE_CONTENT: (
            UNPROCESSABLE_RESPONSE
        ),
    },
)
def search_references(
    profile_id: PositivePathIdentifier,
    query: RequiredSearchQuery,
    database_session: Annotated[
        Session,
        Depends(get_database_session),
    ],
) -> OwnedGameSearchResponse:
    """Search cached games owned by one selected profile."""
    try:
        suggestions = search_owned_games(
            database_session,
            profile_id,
            query,
        )
    except (
        InvalidSearchQueryError,
        ProfileNotFoundError,
    ) as error:
        _raise_reference_read_error(error)

    return OwnedGameSearchResponse(
        items=tuple(
            _owned_game_suggestion_response(suggestion)
            for suggestion in suggestions
        )
    )


@router.get(
    "/references/{steam_app_id}",
    response_model=ReferenceDetailsResponse,
    responses={
        status.HTTP_404_NOT_FOUND: NOT_FOUND_RESPONSE,
        status.HTTP_409_CONFLICT: CONFLICT_RESPONSE,
        status.HTTP_422_UNPROCESSABLE_CONTENT: (
            UNPROCESSABLE_RESPONSE
        ),
    },
)
def read_reference_details(
    profile_id: PositivePathIdentifier,
    steam_app_id: PositivePathIdentifier,
    database_session: Annotated[
        Session,
        Depends(get_database_session),
    ],
) -> ReferenceDetailsResponse:
    """Return cached factual details for one ready owned reference."""
    try:
        details = load_reference_details(
            database_session,
            profile_id,
            steam_app_id,
        )
    except (
        ProfileNotFoundError,
        ReferenceNotOwnedError,
        ReferenceMetadataUnavailableError,
    ) as error:
        _raise_reference_read_error(error)

    return _reference_details_response(details)


@router.get(
    "/references/{steam_app_id}/keywords",
    response_model=KeywordSearchResponse,
    responses={
        status.HTTP_404_NOT_FOUND: NOT_FOUND_RESPONSE,
        status.HTTP_409_CONFLICT: CONFLICT_RESPONSE,
        status.HTTP_422_UNPROCESSABLE_CONTENT: (
            UNPROCESSABLE_RESPONSE
        ),
    },
)
def search_keywords(
    profile_id: PositivePathIdentifier,
    steam_app_id: PositivePathIdentifier,
    query: RequiredSearchQuery,
    database_session: Annotated[
        Session,
        Depends(get_database_session),
    ],
) -> KeywordSearchResponse:
    """Search cached keywords linked to one ready owned reference."""
    try:
        keywords = search_reference_keywords(
            database_session,
            profile_id,
            steam_app_id,
            query,
        )
    except (
        InvalidSearchQueryError,
        ProfileNotFoundError,
        ReferenceNotOwnedError,
        ReferenceMetadataUnavailableError,
    ) as error:
        _raise_reference_read_error(error)

    return KeywordSearchResponse(
        items=tuple(
            _facet_option_response(keyword)
            for keyword in keywords
        )
    )


@router.post(
    "/preferences/validate",
    response_model=RecommendationPreference,
    responses={
        status.HTTP_404_NOT_FOUND: NOT_FOUND_RESPONSE,
        status.HTTP_409_CONFLICT: CONFLICT_RESPONSE,
        status.HTTP_422_UNPROCESSABLE_CONTENT: (
            UNPROCESSABLE_RESPONSE
        ),
    },
)
def validate_submitted_preference(
    profile_id: PositivePathIdentifier,
    preference: RecommendationPreference,
    database_session: Annotated[
        Session,
        Depends(get_database_session),
    ],
) -> RecommendationPreference:
    """Validate and return one canonical recommendation preference."""
    try:
        validated = validate_preference(
            database_session,
            profile_id,
            preference,
        )
    except PreferenceValidationError as error:
        _raise_preference_validation_error(error)

    return validated.preference


def _owned_game_suggestion_response(
    suggestion: OwnedGameSuggestion,
) -> OwnedGameSuggestionResponse:
    """Convert one domain suggestion into its public response."""
    return OwnedGameSuggestionResponse(
        steam_app_id=suggestion.steam_app_id,
        name=suggestion.name,
        cover_url=suggestion.cover_url,
        metadata_status=suggestion.metadata_status,
    )


def _facet_option_response(
    option: FacetOption,
) -> FacetOptionResponse:
    """Convert one domain facet option into its public response."""
    return FacetOptionResponse(
        id=option.id,
        name=option.name,
    )


def _reference_details_response(
    details: ReferenceDetails,
) -> ReferenceDetailsResponse:
    """Convert domain reference details into their public response."""
    return ReferenceDetailsResponse(
        steam_app_id=details.steam_app_id,
        name=details.name,
        cover_url=details.cover_url,
        metadata_status=details.metadata_status,
        facets=ReferenceFacetsResponse(
            genres=tuple(
                _facet_option_response(option)
                for option in details.facets.genres
            ),
            themes=tuple(
                _facet_option_response(option)
                for option in details.facets.themes
            ),
            game_modes=tuple(
                _facet_option_response(option)
                for option in details.facets.game_modes
            ),
        ),
    )


def _raise_reference_read_error(
    error: (
        InvalidSearchQueryError
        | ProfileNotFoundError
        | ReferenceNotOwnedError
        | ReferenceMetadataUnavailableError
    ),
) -> NoReturn:
    """Translate one reference-read failure into its HTTP form."""
    if isinstance(error, InvalidSearchQueryError):
        status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
        code = RecommendationErrorCode.INVALID_QUERY
    elif isinstance(error, ProfileNotFoundError):
        status_code = status.HTTP_404_NOT_FOUND
        code = RecommendationErrorCode.PROFILE_NOT_FOUND
    elif isinstance(error, ReferenceNotOwnedError):
        status_code = status.HTTP_404_NOT_FOUND
        code = RecommendationErrorCode.REFERENCE_NOT_OWNED
    else:
        status_code = status.HTTP_409_CONFLICT
        code = (
            RecommendationErrorCode
            .REFERENCE_METADATA_UNAVAILABLE
        )

    raise RecommendationHTTPError(
        status_code=status_code,
        code=code,
        field=error.field,
        message=str(error),
    ) from error


def _raise_preference_validation_error(
    error: PreferenceValidationError,
) -> NoReturn:
    """Translate one preference-validation failure into HTTP."""
    if (
        error.issue.code
        is PreferenceValidationCode.PROFILE_NOT_FOUND
    ):
        status_code = status.HTTP_404_NOT_FOUND
    elif (
        error.issue.code
        is PreferenceValidationCode.REFERENCE_NOT_OWNED
    ):
        status_code = status.HTTP_404_NOT_FOUND
    elif (
        error.issue.code
        is (
            PreferenceValidationCode
            .REFERENCE_METADATA_UNAVAILABLE
        )
    ):
        status_code = status.HTTP_409_CONFLICT
    else:
        status_code = status.HTTP_422_UNPROCESSABLE_CONTENT

    raise RecommendationHTTPError(
        status_code=status_code,
        code=RecommendationErrorCode(error.issue.code.value),
        field=error.issue.field,
        message=error.issue.message,
    ) from error
