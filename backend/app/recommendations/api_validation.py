from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from sqlalchemy.exc import SQLAlchemyError

from app.recommendations.api_schemas import (
    RecommendationErrorCode,
    RecommendationErrorDetail,
    RecommendationErrorResponse,
)


class RecommendationHTTPError(Exception):
    """Carry one recommendation error through the HTTP route layer."""

    def __init__(
        self,
        status_code: int,
        code: RecommendationErrorCode,
        field: str,
        message: str,
    ) -> None:
        """Store the status and safe public issue."""
        self.status_code = status_code
        self.issue = RecommendationErrorDetail(
            code=code,
            field=field,
            message=message,
        )
        super().__init__(message)


class RecommendationAPIRoute(APIRoute):
    """Translate recommendation request failures into one envelope."""

    def get_route_handler(
        self,
    ) -> Callable[[Request], Awaitable[Response]]:
        """Wrap FastAPI's generated handler with scoped translation."""
        original_handler = super().get_route_handler()

        async def translated_handler(
            request: Request,
        ) -> Response:
            try:
                return await original_handler(request)
            except RecommendationHTTPError as error:
                return _error_response(
                    error.status_code,
                    error.issue,
                )
            except RequestValidationError as error:
                return _error_response(
                    status.HTTP_422_UNPROCESSABLE_CONTENT,
                    _translate_request_validation_error(error),
                )
            except SQLAlchemyError:
                return _error_response(
                    status.HTTP_503_SERVICE_UNAVAILABLE,
                    RecommendationErrorDetail(
                        code=(
                            RecommendationErrorCode
                            .SERVICE_UNAVAILABLE
                        ),
                        field="request",
                        message=(
                            "Recommendations are temporarily "
                            "unavailable."
                        ),
                    ),
                )

        return translated_handler


def _error_response(
    status_code: int,
    issue: RecommendationErrorDetail,
) -> JSONResponse:
    """Serialize one public recommendation error."""
    response = RecommendationErrorResponse(error=issue)

    return JSONResponse(
        status_code=status_code,
        content=response.model_dump(mode="json"),
    )


def _translate_request_validation_error(
    error: RequestValidationError,
) -> RecommendationErrorDetail:
    """Translate the first deterministic FastAPI validation issue."""
    validation_errors = error.errors()

    if not validation_errors:
        return RecommendationErrorDetail(
            code=RecommendationErrorCode.INVALID_VALUE,
            field="body",
            message="This field has an invalid value.",
        )

    return _translate_validation_issue(validation_errors[0])


def _translate_validation_issue(
    error: dict[str, Any],
) -> RecommendationErrorDetail:
    """Translate one Pydantic error without exposing internals."""
    error_type = str(error.get("type", ""))
    message = str(error.get("msg", ""))
    field = _public_field(error.get("loc", ()))

    if error_type == "missing":
        return RecommendationErrorDetail(
            code=RecommendationErrorCode.MISSING_FIELD,
            field=field,
            message="This field is required.",
        )

    if error_type == "extra_forbidden":
        return RecommendationErrorDetail(
            code=RecommendationErrorCode.UNEXPECTED_FIELD,
            field=field,
            message="Unexpected fields are not allowed.",
        )

    if (
        error_type == "json_invalid"
        or (
            field == "body"
            and error_type
            in {
                "dict_type",
                "model_attributes_type",
                "model_type",
            }
        )
    ):
        return RecommendationErrorDetail(
            code=RecommendationErrorCode.INVALID_TYPE,
            field="body",
            message="The request body must be a JSON object.",
        )

    custom_issue = _translate_contract_validator(
        error,
        field,
        message,
    )
    if custom_issue is not None:
        return custom_issue

    if _is_type_failure(error_type):
        return RecommendationErrorDetail(
            code=RecommendationErrorCode.INVALID_TYPE,
            field=field,
            message="This field has an invalid type.",
        )

    if field.endswith("maximum_completion_minutes"):
        return RecommendationErrorDetail(
            code=RecommendationErrorCode.INVALID_VALUE,
            field=field,
            message=(
                "Maximum completion time must be between 30 and "
                "60000 minutes."
            ),
        )

    if field.endswith("play_status"):
        return RecommendationErrorDetail(
            code=RecommendationErrorCode.INVALID_VALUE,
            field=field,
            message=(
                "Play status must be unplayed, previously_played, "
                "or either."
            ),
        )

    if _is_identifier_field(field):
        return RecommendationErrorDetail(
            code=RecommendationErrorCode.INVALID_VALUE,
            field=field,
            message="IDs must be positive integers.",
        )

    return RecommendationErrorDetail(
        code=RecommendationErrorCode.INVALID_VALUE,
        field=field,
        message="This field has an invalid value.",
    )


def _translate_contract_validator(
    error: dict[str, Any],
    field: str,
    message: str,
) -> RecommendationErrorDetail | None:
    """Translate known contract-validator messages and item paths."""
    if "Select between one and three reference games." in message:
        return RecommendationErrorDetail(
            code=(
                RecommendationErrorCode.INVALID_REFERENCE_COUNT
            ),
            field="references",
            message=(
                "Select between one and three reference games."
            ),
        )

    if "Reference games must be unique." in message:
        duplicate_index = _later_duplicate_index(
            error.get("input"),
            key="steam_app_id",
        )
        return RecommendationErrorDetail(
            code=RecommendationErrorCode.DUPLICATE_REFERENCE,
            field=(
                f"references[{duplicate_index}].steam_app_id"
            ),
            message="Reference games must be unique.",
        )

    if (
        "Facet IDs must be unique within their category."
        in message
    ):
        duplicate_index = _later_duplicate_index(
            error.get("input")
        )
        return RecommendationErrorDetail(
            code=RecommendationErrorCode.DUPLICATE_FACET,
            field=f"{field}[{duplicate_index}]",
            message=(
                "Facet IDs must be unique within their category."
            ),
        )

    if (
        "Select at least one facet from this reference game."
        in message
    ):
        return RecommendationErrorDetail(
            code=(
                RecommendationErrorCode.EMPTY_REFERENCE_FACETS
            ),
            field=field,
            message=(
                "Select at least one facet from this reference game."
            ),
        )

    if (
        "Select no more than three keywords per reference game."
        in message
    ):
        return RecommendationErrorDetail(
            code=RecommendationErrorCode.TOO_MANY_KEYWORDS,
            field=field,
            message=(
                "Select no more than three keywords per "
                "reference game."
            ),
        )

    if "Rejected game IDs must be unique." in message:
        duplicate_index = _later_duplicate_index(error.get("input"))
        return RecommendationErrorDetail(
            code=RecommendationErrorCode.DUPLICATE_REJECTED_GAME,
            field=f"{field}[{duplicate_index}]",
            message="Rejected game IDs must be unique.",
        )

    if (
        "A session may exclude at most 30 rejected games."
        in message
    ):
        return RecommendationErrorDetail(
            code=RecommendationErrorCode.TOO_MANY_REJECTED_GAMES,
            field=field,
            message=(
                "A session may exclude at most 30 rejected games."
            ),
        )

    return None


def _later_duplicate_index(
    values: object,
    *,
    key: str | None = None,
) -> int:
    """Return the index of the first later duplicate value."""
    if not isinstance(values, (list, tuple)):
        return 1

    seen: set[object] = set()

    for index, item in enumerate(values):
        value = item

        if key is not None:
            if isinstance(item, dict):
                value = item.get(key)
            else:
                value = getattr(item, key, None)

        try:
            if value in seen:
                return index
            seen.add(value)
        except TypeError:
            continue

    return max(len(values) - 1, 0)


def _public_field(location: object) -> str:
    """Convert a FastAPI location into a public dotted field path."""
    if not isinstance(location, (list, tuple)):
        return "body"

    parts = list(location)

    if (
        parts
        and parts[0] in {"body", "path", "query"}
    ):
        source = str(parts.pop(0))
    else:
        source = "body"

    if not parts:
        return source

    field = ""

    for part in parts:
        if isinstance(part, int):
            field += f"[{part}]"
        else:
            if field:
                field += "."
            field += str(part)

    return field


def _is_type_failure(error_type: str) -> bool:
    """Return whether a Pydantic error represents a type failure."""
    return (
        error_type.endswith("_type")
        or error_type.endswith("_parsing")
        or error_type
        in {
            "bytes_type",
            "dict_type",
            "float_type",
            "int_parsing_size",
            "list_type",
            "mapping_type",
            "model_attributes_type",
            "model_type",
            "string_type",
            "tuple_type",
        }
    )


def _is_identifier_field(field: str) -> bool:
    """Return whether a public field identifies a stored entity."""
    if field in {"profile_id", "steam_app_id"}:
        return True

    if field.endswith(".steam_app_id"):
        return True

    facet_fields = (
        ".genre_ids[",
        ".theme_ids[",
        ".keyword_ids[",
        ".game_mode_ids[",
    )

    if field.startswith("rejected_steam_app_ids["):
        return True

    return any(
        facet_field in field
        for facet_field in facet_fields
    )
