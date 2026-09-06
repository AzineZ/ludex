from typing import NoReturn

from fastapi import status

from app.recommendations.api.schemas import RecommendationErrorCode
from app.recommendations.api.validation import RecommendationHTTPError
from app.recommendations.preference_validation import (
    PreferenceValidationCode,
    PreferenceValidationError,
)
from app.recommendations.reference_reads import (
    InvalidSearchQueryError,
    ProfileNotFoundError,
    ReferenceMetadataUnavailableError,
    ReferenceNotOwnedError,
)


def raise_reference_read_error(
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
        code = RecommendationErrorCode.REFERENCE_METADATA_UNAVAILABLE

    raise RecommendationHTTPError(
        status_code=status_code,
        code=code,
        field=error.field,
        message=str(error),
    ) from error


def raise_preference_validation_error(
    error: PreferenceValidationError,
) -> NoReturn:
    """Translate one preference-validation failure into HTTP."""
    if error.issue.code in {
        PreferenceValidationCode.PROFILE_NOT_FOUND,
        PreferenceValidationCode.REFERENCE_NOT_OWNED,
    }:
        status_code = status.HTTP_404_NOT_FOUND
    elif (
        error.issue.code
        is PreferenceValidationCode.REFERENCE_METADATA_UNAVAILABLE
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
