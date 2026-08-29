from dataclasses import dataclass
from enum import StrEnum
from fractions import Fraction
from typing import TypeAlias

from app.recommendations.factual_scoring import (
    FacetKind,
    FacetMatchState,
    FactualScoreEvidence,
)
from app.recommendations.retrieval import FactualCandidatePool

FINAL_RECOMMENDATION_LIMIT = 6
MATCH_SUMMARY_REASON_LIMIT = 3

_FACET_KIND_ORDER = {
    FacetKind.GENRE: 0,
    FacetKind.THEME: 1,
    FacetKind.KEYWORD: 2,
    FacetKind.GAME_MODE: 3,
}

_FACET_KIND_BUDGET = {
    FacetKind.GENRE: 30,
    FacetKind.THEME: 25,
    FacetKind.KEYWORD: 20,
    FacetKind.GAME_MODE: 25,
}

_FACET_KIND_DISPLAY_NAME = {
    FacetKind.GENRE: "genre",
    FacetKind.THEME: "theme",
    FacetKind.KEYWORD: "keyword",
    FacetKind.GAME_MODE: "game-mode",
}


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


def _facet_label_map(
    facet_labels: tuple[FacetLabel, ...],
) -> dict[tuple[FacetKind, int], str]:
    """Index authoritative labels and reject ambiguous identities."""
    labels_by_identity: dict[tuple[FacetKind, int], str] = {}
    for label in facet_labels:
        identity = (label.facet_kind, label.facet_igdb_id)
        if identity in labels_by_identity:
            raise ValueError(
                "duplicate facet label for "
                f"{label.facet_kind.value}:{label.facet_igdb_id}"
            )
        labels_by_identity[identity] = label.name
    return labels_by_identity


def _render_match_summary(
    reasons: tuple[MatchReason, ...],
    additional_match_count: int,
) -> str:
    """Render the approved deterministic match-summary wording."""
    names = tuple(reason.name for reason in reasons)
    if not names:
        return "No selected factual preferences matched."
    if len(names) == 1:
        return f"Matches your {names[0]} preference."
    if len(names) == 2:
        return f"Matches your {names[0]} and {names[1]} preferences."

    text = f"Matches your {names[0]}, {names[1]}, and {names[2]} preferences"
    if additional_match_count:
        return f"{text}, plus {additional_match_count} more."
    return f"{text}."


def build_match_summary(
    evidence: FactualScoreEvidence,
    facet_labels: tuple[FacetLabel, ...],
) -> MatchSummary:
    """Build a bounded summary from immutable factual score evidence."""
    labels_by_identity = _facet_label_map(facet_labels)
    for contribution in evidence.contributions:
        identity = (
            contribution.facet_kind,
            contribution.facet_igdb_id,
        )
        if identity not in labels_by_identity:
            raise ValueError(
                "missing facet label for "
                f"{contribution.facet_kind.value}:"
                f"{contribution.facet_igdb_id}"
            )

    grouped_points: dict[tuple[FacetKind, int], Fraction] = {}
    grouped_references: dict[tuple[FacetKind, int], list[int]] = {}
    for contribution in evidence.contributions:
        if contribution.match_state is not FacetMatchState.MATCHED:
            continue

        identity = (
            contribution.facet_kind,
            contribution.facet_igdb_id,
        )
        grouped_points[identity] = grouped_points.get(
            identity,
            Fraction(0),
        ) + Fraction(
            contribution.points_numerator,
            contribution.points_denominator,
        )
        references = grouped_references.setdefault(identity, [])
        if contribution.reference_steam_app_id not in references:
            references.append(contribution.reference_steam_app_id)

    all_reasons = [
        MatchReason(
            facet_kind=facet_kind,
            facet_igdb_id=facet_igdb_id,
            name=labels_by_identity[(facet_kind, facet_igdb_id)],
            reference_steam_app_ids=tuple(
                grouped_references[(facet_kind, facet_igdb_id)]
            ),
            points_numerator=points.numerator,
            points_denominator=points.denominator,
        )
        for (facet_kind, facet_igdb_id), points in grouped_points.items()
    ]
    all_reasons.sort(
        key=lambda reason: (
            -Fraction(
                reason.points_numerator,
                reason.points_denominator,
            ),
            _FACET_KIND_ORDER[reason.facet_kind],
            reason.facet_igdb_id,
        )
    )

    reasons = tuple(all_reasons[:MATCH_SUMMARY_REASON_LIMIT])
    additional_match_count = len(all_reasons) - len(reasons)
    return MatchSummary(
        reasons=reasons,
        additional_match_count=additional_match_count,
        text=_render_match_summary(reasons, additional_match_count),
    )


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


def _render_unknown_metadata_tradeoff(
    facet_kinds: tuple[FacetKind, ...],
) -> str:
    """Render the approved unknown-metadata wording."""
    names = tuple(_FACET_KIND_DISPLAY_NAME[kind] for kind in facet_kinds)
    if len(names) == 1:
        subject = names[0]
        verb = "is"
    elif len(names) == 2:
        subject = f"{names[0]} and {names[1]}"
        verb = "are"
    else:
        subject = f"{', '.join(names[:-1])}, and {names[-1]}"
        verb = "are"
    return f"{subject.capitalize()} metadata {verb} unavailable."


def build_tradeoff(
    evidence: FactualScoreEvidence,
    facet_labels: tuple[FacetLabel, ...],
    *,
    normal_completion_seconds: int | None,
) -> RecommendationTradeoff | None:
    """Choose at most one deterministic, grounded result tradeoff."""
    labels_by_identity = _facet_label_map(facet_labels)
    for contribution in evidence.contributions:
        identity = (
            contribution.facet_kind,
            contribution.facet_igdb_id,
        )
        if identity not in labels_by_identity:
            raise ValueError(
                "missing facet label for "
                f"{contribution.facet_kind.value}:"
                f"{contribution.facet_igdb_id}"
            )

    unknown_kinds = tuple(
        kind
        for kind in _FACET_KIND_ORDER
        if any(
            contribution.facet_kind is kind
            and contribution.match_state is FacetMatchState.UNKNOWN
            for contribution in evidence.contributions
        )
    )
    if unknown_kinds:
        return UnknownPreferenceMetadataTradeoff(
            facet_kinds=unknown_kinds,
            text=_render_unknown_metadata_tradeoff(unknown_kinds),
        )

    has_positive_match = any(
        contribution.match_state is FacetMatchState.MATCHED
        for contribution in evidence.contributions
    )
    if has_positive_match:
        grouped_references: dict[tuple[FacetKind, int], list[int]] = {}
        for contribution in evidence.contributions:
            if contribution.match_state is not FacetMatchState.NOT_MATCHED:
                continue
            identity = (
                contribution.facet_kind,
                contribution.facet_igdb_id,
            )
            references = grouped_references.setdefault(identity, [])
            if contribution.reference_steam_app_id not in references:
                references.append(contribution.reference_steam_app_id)

        if grouped_references:
            facet_kind, facet_igdb_id = min(
                grouped_references,
                key=lambda identity: (
                    -len(grouped_references[identity]),
                    -_FACET_KIND_BUDGET[identity[0]],
                    _FACET_KIND_ORDER[identity[0]],
                    identity[1],
                ),
            )
            name = labels_by_identity[(facet_kind, facet_igdb_id)]
            return UnmatchedPreferenceTradeoff(
                reason=UnmatchedPreferenceReason(
                    facet_kind=facet_kind,
                    facet_igdb_id=facet_igdb_id,
                    name=name,
                    reference_steam_app_ids=tuple(
                        grouped_references[(facet_kind, facet_igdb_id)]
                    ),
                ),
                text=f"Does not match your {name} preference.",
            )

    if normal_completion_seconds is None:
        return UnknownCompletionTimeTradeoff(
            text="Completion-time estimate is unavailable."
        )
    return None


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


def assemble_final_recommendations(
    candidate_pool: FactualCandidatePool,
    presentations: tuple[CandidatePresentationFacts, ...],
    facet_labels: tuple[FacetLabel, ...],
) -> FinalRecommendationResult:
    """Assemble the first six factual candidates into final results."""
    seen_candidate_ids: set[int] = set()
    for candidate in candidate_pool.candidates:
        if candidate.steam_app_id in seen_candidate_ids:
            raise ValueError(
                "duplicate candidate Steam App ID "
                f"{candidate.steam_app_id}"
            )
        seen_candidate_ids.add(candidate.steam_app_id)

    selected_candidates = candidate_pool.candidates[
        :FINAL_RECOMMENDATION_LIMIT
    ]
    selected_ids = {
        candidate.steam_app_id for candidate in selected_candidates
    }

    presentations_by_id: dict[int, CandidatePresentationFacts] = {}
    for presentation in presentations:
        if presentation.steam_app_id in presentations_by_id:
            raise ValueError(
                "duplicate presentation facts for Steam App ID "
                f"{presentation.steam_app_id}"
            )
        presentations_by_id[presentation.steam_app_id] = presentation

    for candidate in selected_candidates:
        if candidate.steam_app_id not in presentations_by_id:
            raise ValueError(
                "missing presentation facts for Steam App ID "
                f"{candidate.steam_app_id}"
            )
    for presentation in presentations:
        if presentation.steam_app_id not in selected_ids:
            raise ValueError(
                "unexpected presentation facts for Steam App ID "
                f"{presentation.steam_app_id}"
            )

    labels_by_identity = _facet_label_map(facet_labels)
    expected_label_identities = {
        (contribution.facet_kind, contribution.facet_igdb_id)
        for candidate in selected_candidates
        for contribution in candidate.evidence.contributions
    }
    for facet_kind, facet_igdb_id in expected_label_identities:
        if (facet_kind, facet_igdb_id) not in labels_by_identity:
            raise ValueError(
                "missing facet label for "
                f"{facet_kind.value}:{facet_igdb_id}"
            )
    for label in facet_labels:
        identity = (label.facet_kind, label.facet_igdb_id)
        if identity not in expected_label_identities:
            raise ValueError(
                "unexpected facet label for "
                f"{label.facet_kind.value}:{label.facet_igdb_id}"
            )

    items = tuple(
        FinalRecommendationItem(
            rank=rank,
            presentation=presentations_by_id[candidate.steam_app_id],
            factual_evidence=candidate.evidence,
            facet_labels=facet_labels,
            match_summary=build_match_summary(
                candidate.evidence,
                facet_labels,
            ),
            tradeoff=build_tradeoff(
                candidate.evidence,
                facet_labels,
                normal_completion_seconds=presentations_by_id[
                    candidate.steam_app_id
                ].normal_completion_seconds,
            ),
        )
        for rank, candidate in enumerate(selected_candidates, start=1)
    )
    return FinalRecommendationResult(
        eligible_count=candidate_pool.eligible_count,
        items=items,
    )
