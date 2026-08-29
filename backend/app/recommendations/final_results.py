from dataclasses import dataclass
from enum import StrEnum
from typing import TypeAlias

from app.recommendations.factual_scoring import (
    FacetKind,
    FactualScoreEvidence,
)

FINAL_RECOMMENDATION_LIMIT = 6


class RecommendationOutcome(StrEnum):
    """Describe the number of final recommendations returned."""

    COMPLETE = "complete"
    SPARSE = "sparse"
    EMPTY = "empty"


@dataclass(frozen=True)
class CandidatePresentationFacts:
    """Hold cache-only display facts for one owned candidate."""

    steam_app_id: int
    title: str
    cover_url: str | None
    profile_playtime_minutes: int
    normal_completion_seconds: int | None


@dataclass(frozen=True)
class FacetLabel:
    """Map one factual facet identity to its authoritative cached name."""

    facet_kind: FacetKind
    facet_igdb_id: int
    name: str


@dataclass(frozen=True)
class MatchReason:
    """Describe one collapsed, grounded reason for a factual match."""

    facet_kind: FacetKind
    facet_igdb_id: int
    name: str
    reference_steam_app_ids: tuple[int, ...]
    points_numerator: int
    points_denominator: int


@dataclass(frozen=True)
class MatchSummary:
    """Provide bounded structured reasons and deterministic card copy."""

    reasons: tuple[MatchReason, ...]
    additional_match_count: int
    text: str


class TradeoffType(StrEnum):
    """Identify the strict shape of one result tradeoff."""

    UNKNOWN_PREFERENCE_METADATA = "unknown_preference_metadata"
    UNMATCHED_PREFERENCE = "unmatched_preference"
    UNKNOWN_COMPLETION_TIME = "unknown_completion_time"


@dataclass(frozen=True)
class UnknownPreferenceMetadataTradeoff:
    """Report active factual categories whose candidate facts are unknown."""

    facet_kinds: tuple[FacetKind, ...]
    text: str
    type: TradeoffType = TradeoffType.UNKNOWN_PREFERENCE_METADATA


@dataclass(frozen=True)
class UnmatchedPreferenceReason:
    """Identify one selected factual preference a candidate does not match."""

    facet_kind: FacetKind
    facet_igdb_id: int
    name: str
    reference_steam_app_ids: tuple[int, ...]


@dataclass(frozen=True)
class UnmatchedPreferenceTradeoff:
    """Report the highest-priority known factual nonmatch."""

    reason: UnmatchedPreferenceReason
    text: str
    type: TradeoffType = TradeoffType.UNMATCHED_PREFERENCE


@dataclass(frozen=True)
class UnknownCompletionTimeTradeoff:
    """Report that cached completion-time metadata is unavailable."""

    text: str
    type: TradeoffType = TradeoffType.UNKNOWN_COMPLETION_TIME


RecommendationTradeoff: TypeAlias = (
    UnknownPreferenceMetadataTradeoff
    | UnmatchedPreferenceTradeoff
    | UnknownCompletionTimeTradeoff
)


@dataclass(frozen=True)
class FinalRecommendationItem:
    """Combine immutable scoring evidence with grounded presentation data."""

    rank: int
    presentation: CandidatePresentationFacts
    factual_evidence: FactualScoreEvidence
    facet_labels: tuple[FacetLabel, ...]
    match_summary: MatchSummary
    tradeoff: RecommendationTradeoff | None


@dataclass(frozen=True)
class FinalRecommendationResult:
    """Return one bounded, ordered final recommendation collection."""

    eligible_count: int
    items: tuple[FinalRecommendationItem, ...]

    def __post_init__(self) -> None:
        if len(self.items) > FINAL_RECOMMENDATION_LIMIT:
            raise ValueError("final results contain at most 6 items")
        if self.eligible_count < len(self.items):
            raise ValueError(
                "eligible_count cannot be below returned_count"
            )
        if tuple(item.rank for item in self.items) != tuple(
            range(1, len(self.items) + 1)
        ):
            raise ValueError("final results require ordinal ranks 1..N")

    @property
    def returned_count(self) -> int:
        """Derive the serialized count from the immutable item tuple."""
        return len(self.items)

    @property
    def outcome(self) -> RecommendationOutcome:
        """Derive the stable result outcome from returned cardinality."""
        if self.returned_count == 0:
            return RecommendationOutcome.EMPTY
        if self.returned_count < FINAL_RECOMMENDATION_LIMIT:
            return RecommendationOutcome.SPARSE
        return RecommendationOutcome.COMPLETE
