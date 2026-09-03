from enum import StrEnum
from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.recommendations.contracts import (
    PositiveIdentifier,
    RecommendationPreference,
)
from app.recommendations.factual_scoring import (
    FacetKind,
    FacetMatchState,
)
from app.recommendations.final_results import (
    FinalRecommendationItem,
    FinalRecommendationResult,
    MatchReason,
    RecommendationOutcome,
    RecommendationTradeoff,
    UnknownCompletionTimeTradeoff,
    UnknownPreferenceMetadataTradeoff,
    UnmatchedPreferenceReason,
    UnmatchedPreferenceTradeoff,
)
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
    DUPLICATE_REJECTED_GAME = "duplicate_rejected_game"
    TOO_MANY_REJECTED_GAMES = "too_many_rejected_games"
    INVALID_QUERY = "invalid_query"
    PROFILE_NOT_FOUND = "profile_not_found"
    REFERENCE_NOT_OWNED = "reference_not_owned"
    REFERENCE_METADATA_UNAVAILABLE = (
        "reference_metadata_unavailable"
    )
    FACET_NOT_ON_REFERENCE = "facet_not_on_reference"
    SERVICE_UNAVAILABLE = "service_unavailable"


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


class KeywordBrowseResponse(RecommendationHTTPModel):
    """Envelope a bounded reference-scoped keyword collection."""

    items: tuple[FacetOptionResponse, ...]
    truncated: bool


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


class FactualContributionResponse(RecommendationHTTPModel):
    """Expose one unchanged factual scoring assertion."""

    reference_steam_app_id: int
    facet_kind: FacetKind
    facet_igdb_id: int
    match_state: FacetMatchState
    points_numerator: int
    points_denominator: int


class FactualScoreEvidenceResponse(RecommendationHTTPModel):
    """Expose the complete factual score evidence for one result."""

    version: str
    score_basis_points: int
    active_budget: int
    contributions: tuple[FactualContributionResponse, ...]


class FacetLabelResponse(RecommendationHTTPModel):
    """Expose one authoritative cached facet label."""

    facet_kind: FacetKind
    facet_igdb_id: int
    name: str


class MatchReasonResponse(RecommendationHTTPModel):
    """Expose one collapsed grounded match reason."""

    facet_kind: FacetKind
    facet_igdb_id: int
    name: str
    reference_steam_app_ids: tuple[int, ...]
    points_numerator: int
    points_denominator: int


class MatchSummaryResponse(RecommendationHTTPModel):
    """Expose bounded reasons and their deterministic rendered text."""

    reasons: tuple[MatchReasonResponse, ...]
    additional_match_count: int
    text: str


class UnmatchedPreferenceReasonResponse(RecommendationHTTPModel):
    """Expose one selected preference a candidate does not match."""

    facet_kind: FacetKind
    facet_igdb_id: int
    name: str
    reference_steam_app_ids: tuple[int, ...]


class UnknownPreferenceMetadataTradeoffResponse(
    RecommendationHTTPModel
):
    """Expose active factual categories with unavailable metadata."""

    type: Literal["unknown_preference_metadata"]
    facet_kinds: tuple[FacetKind, ...]
    text: str


class UnmatchedPreferenceTradeoffResponse(RecommendationHTTPModel):
    """Expose the highest-priority known factual nonmatch."""

    type: Literal["unmatched_preference"]
    reason: UnmatchedPreferenceReasonResponse
    text: str


class UnknownCompletionTimeTradeoffResponse(RecommendationHTTPModel):
    """Expose unavailable cached completion-time metadata."""

    type: Literal["unknown_completion_time"]
    text: str


RecommendationTradeoffResponse: TypeAlias = Annotated[
    UnknownPreferenceMetadataTradeoffResponse
    | UnmatchedPreferenceTradeoffResponse
    | UnknownCompletionTimeTradeoffResponse,
    Field(discriminator="type"),
]


class FinalRecommendationItemResponse(RecommendationHTTPModel):
    """Expose one self-contained final recommendation."""

    rank: int
    steam_app_id: int
    title: str
    cover_url: str | None
    profile_playtime_minutes: int
    normal_completion_seconds: int | None
    factual_evidence: FactualScoreEvidenceResponse
    facet_labels: tuple[FacetLabelResponse, ...]
    match_summary: MatchSummaryResponse
    tradeoff: RecommendationTradeoffResponse | None


class FinalRecommendationResponse(RecommendationHTTPModel):
    """Envelope one successful complete, sparse, or empty result."""

    outcome: RecommendationOutcome
    eligible_count: int
    returned_count: int
    items: tuple[FinalRecommendationItemResponse, ...]


MAX_SESSION_REJECTED_GAMES = 30


class RecommendationRefinementRequest(RecommendationHTTPModel):
    """Carry one canonical preference and bounded session exclusions."""

    preference: RecommendationPreference
    rejected_steam_app_ids: tuple[PositiveIdentifier, ...]

    @field_validator("rejected_steam_app_ids")
    @classmethod
    def validate_rejected_steam_app_ids(
        cls,
        steam_app_ids: tuple[int, ...],
    ) -> tuple[int, ...]:
        """Reject duplicate or unbounded session exclusions."""
        if len(steam_app_ids) > MAX_SESSION_REJECTED_GAMES:
            raise ValueError(
                "A session may exclude at most 30 rejected games."
            )
        if len(set(steam_app_ids)) != len(steam_app_ids):
            raise ValueError("Rejected game IDs must be unique.")
        return steam_app_ids


def _match_reason_response(reason: MatchReason) -> MatchReasonResponse:
    """Convert one domain match reason into its public form."""
    return MatchReasonResponse(
        facet_kind=reason.facet_kind,
        facet_igdb_id=reason.facet_igdb_id,
        name=reason.name,
        reference_steam_app_ids=reason.reference_steam_app_ids,
        points_numerator=reason.points_numerator,
        points_denominator=reason.points_denominator,
    )


def _unmatched_reason_response(
    reason: UnmatchedPreferenceReason,
) -> UnmatchedPreferenceReasonResponse:
    """Convert one domain nonmatch reason into its public form."""
    return UnmatchedPreferenceReasonResponse(
        facet_kind=reason.facet_kind,
        facet_igdb_id=reason.facet_igdb_id,
        name=reason.name,
        reference_steam_app_ids=reason.reference_steam_app_ids,
    )


def _tradeoff_response(
    tradeoff: RecommendationTradeoff | None,
) -> RecommendationTradeoffResponse | None:
    """Convert one strict domain tradeoff without changing its shape."""
    if isinstance(tradeoff, UnknownPreferenceMetadataTradeoff):
        return UnknownPreferenceMetadataTradeoffResponse(
            type="unknown_preference_metadata",
            facet_kinds=tradeoff.facet_kinds,
            text=tradeoff.text,
        )
    if isinstance(tradeoff, UnmatchedPreferenceTradeoff):
        return UnmatchedPreferenceTradeoffResponse(
            type="unmatched_preference",
            reason=_unmatched_reason_response(tradeoff.reason),
            text=tradeoff.text,
        )
    if isinstance(tradeoff, UnknownCompletionTimeTradeoff):
        return UnknownCompletionTimeTradeoffResponse(
            type="unknown_completion_time",
            text=tradeoff.text,
        )
    return None


def _final_item_response(
    item: FinalRecommendationItem,
) -> FinalRecommendationItemResponse:
    """Flatten one domain item into its self-contained public form."""
    presentation = item.presentation
    evidence = item.factual_evidence
    return FinalRecommendationItemResponse(
        rank=item.rank,
        steam_app_id=presentation.steam_app_id,
        title=presentation.title,
        cover_url=presentation.cover_url,
        profile_playtime_minutes=(
            presentation.profile_playtime_minutes
        ),
        normal_completion_seconds=(
            presentation.normal_completion_seconds
        ),
        factual_evidence=FactualScoreEvidenceResponse(
            version=evidence.version,
            score_basis_points=evidence.score_basis_points,
            active_budget=evidence.active_budget,
            contributions=tuple(
                FactualContributionResponse(
                    reference_steam_app_id=(
                        contribution.reference_steam_app_id
                    ),
                    facet_kind=contribution.facet_kind,
                    facet_igdb_id=contribution.facet_igdb_id,
                    match_state=contribution.match_state,
                    points_numerator=contribution.points_numerator,
                    points_denominator=contribution.points_denominator,
                )
                for contribution in evidence.contributions
            ),
        ),
        facet_labels=tuple(
            FacetLabelResponse(
                facet_kind=label.facet_kind,
                facet_igdb_id=label.facet_igdb_id,
                name=label.name,
            )
            for label in item.facet_labels
        ),
        match_summary=MatchSummaryResponse(
            reasons=tuple(
                _match_reason_response(reason)
                for reason in item.match_summary.reasons
            ),
            additional_match_count=(
                item.match_summary.additional_match_count
            ),
            text=item.match_summary.text,
        ),
        tradeoff=_tradeoff_response(item.tradeoff),
    )


def to_final_recommendation_response(
    result: FinalRecommendationResult,
) -> FinalRecommendationResponse:
    """Convert one immutable domain result into its public response."""
    return FinalRecommendationResponse(
        outcome=result.outcome,
        eligible_count=result.eligible_count,
        returned_count=result.returned_count,
        items=tuple(_final_item_response(item) for item in result.items),
    )


class RecommendationErrorDetail(RecommendationHTTPModel):
    """Describe one safe public recommendation failure."""

    code: RecommendationErrorCode
    field: str
    message: str


class RecommendationErrorResponse(RecommendationHTTPModel):
    """Envelope one deterministic recommendation failure."""

    error: RecommendationErrorDetail
