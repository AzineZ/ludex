from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from app.recommendations.reference_reads import MetadataStatus


class RecommendationHTTPModel(BaseModel):
    """Provide strict immutable behavior for public HTTP schemas."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )


class RecommendationErrorCode(StrEnum):
    """Identify one public recommendation API failure."""

    MISSING_FIELD = "missing_field"
    UNEXPECTED_FIELD = "unexpected_field"
    INVALID_TYPE = "invalid_type"
    INVALID_VALUE = "invalid_value"
    INVALID_REFERENCE_COUNT = "invalid_reference_count"
    DUPLICATE_REFERENCE = "duplicate_reference"
    DUPLICATE_FACET = "duplicate_facet"
    EMPTY_REFERENCE_FACETS = "empty_reference_facets"
    TOO_MANY_KEYWORDS = "too_many_keywords"
    INVALID_QUERY = "invalid_query"
    PROFILE_NOT_FOUND = "profile_not_found"
    REFERENCE_NOT_OWNED = "reference_not_owned"
    REFERENCE_METADATA_UNAVAILABLE = (
        "reference_metadata_unavailable"
    )
    FACET_NOT_ON_REFERENCE = "facet_not_on_reference"


class OwnedGameSuggestionResponse(RecommendationHTTPModel):
    """Describe one owned game returned by reference search."""

    steam_app_id: int
    name: str
    cover_url: str | None
    metadata_status: MetadataStatus


class OwnedGameSearchResponse(RecommendationHTTPModel):
    """Envelope owned-game reference search results."""

    items: tuple[OwnedGameSuggestionResponse, ...]


class FacetOptionResponse(RecommendationHTTPModel):
    """Describe one selectable stored IGDB facet."""

    id: int
    name: str


class KeywordSearchResponse(RecommendationHTTPModel):
    """Envelope reference-scoped keyword search results."""

    items: tuple[FacetOptionResponse, ...]


class ReferenceFacetsResponse(RecommendationHTTPModel):
    """Describe the directly displayed facets for a reference."""

    genres: tuple[FacetOptionResponse, ...]
    themes: tuple[FacetOptionResponse, ...]
    game_modes: tuple[FacetOptionResponse, ...]


class ReferenceDetailsResponse(RecommendationHTTPModel):
    """Describe one selectable ready owned reference."""

    steam_app_id: int
    name: str
    cover_url: str | None
    metadata_status: MetadataStatus
    facets: ReferenceFacetsResponse


class RecommendationErrorDetail(RecommendationHTTPModel):
    """Describe one safe public recommendation failure."""

    code: RecommendationErrorCode
    field: str
    message: str


class RecommendationErrorResponse(RecommendationHTTPModel):
    """Envelope one deterministic recommendation failure."""

    error: RecommendationErrorDetail
