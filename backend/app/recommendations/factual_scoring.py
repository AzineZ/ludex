from dataclasses import dataclass
from enum import StrEnum
from fractions import Fraction
from typing import Iterable

from app.recommendations.candidate_facts import CandidateFacts
from app.recommendations.contracts import RecommendationPreference

FACTUAL_SCORING_VERSION = "factual-overlap-v1"


class FacetKind(StrEnum):
    """Identify one factual scoring category."""

    GENRE = "genre"
    THEME = "theme"
    KEYWORD = "keyword"
    GAME_MODE = "game_mode"


class FacetMatchState(StrEnum):
    """Describe candidate knowledge for one selected facet."""

    MATCHED = "matched"
    NOT_MATCHED = "not_matched"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class FactualContribution:
    """Record one selected reference-facet scoring assertion."""

    reference_steam_app_id: int
    facet_kind: FacetKind
    facet_igdb_id: int
    match_state: FacetMatchState
    points_numerator: int
    points_denominator: int


@dataclass(frozen=True)
class FactualScoreEvidence:
    """Record immutable evidence for one factual candidate score."""

    version: str
    score_basis_points: int
    active_budget: int
    contributions: tuple[FactualContribution, ...]


@dataclass(frozen=True)
class FactualScoredCandidate:
    """Associate one candidate identity with its factual evidence."""

    steam_app_id: int
    evidence: FactualScoreEvidence


_FACET_CONFIGURATION = (
    (FacetKind.GENRE, "genre_ids", 30),
    (FacetKind.THEME, "theme_ids", 25),
    (FacetKind.KEYWORD, "keyword_ids", 20),
    (FacetKind.GAME_MODE, "game_mode_ids", 25),
)


def _round_half_up(value: Fraction) -> int:
    """Round one nonnegative exact fraction to its nearest integer."""
    return (2 * value.numerator + value.denominator) // (
        2 * value.denominator
    )


def score_factual_candidate(
    candidate: CandidateFacts,
    preference: RecommendationPreference,
) -> FactualScoredCandidate:
    """Score selected factual overlap using exact rational arithmetic."""
    active_reference_counts: dict[FacetKind, int] = {}
    active_budget = 0

    for facet_kind, facet_field, budget in _FACET_CONFIGURATION:
        active_count = sum(
            bool(getattr(reference.facets, facet_field))
            for reference in preference.references
        )
        active_reference_counts[facet_kind] = active_count
        if active_count:
            active_budget += budget

    contributions: list[FactualContribution] = []
    total_points = Fraction(0)

    for reference in preference.references:
        for facet_kind, facet_field, budget in _FACET_CONFIGURATION:
            selected_ids = getattr(reference.facets, facet_field)
            if not selected_ids:
                continue

            candidate_ids = getattr(candidate, facet_field)
            points_per_assertion = Fraction(
                10_000 * budget,
                active_budget
                * active_reference_counts[facet_kind]
                * len(selected_ids),
            )

            for facet_igdb_id in selected_ids:
                if candidate_ids is None:
                    match_state = FacetMatchState.UNKNOWN
                    points = Fraction(0)
                elif facet_igdb_id in candidate_ids:
                    match_state = FacetMatchState.MATCHED
                    points = points_per_assertion
                else:
                    match_state = FacetMatchState.NOT_MATCHED
                    points = Fraction(0)

                total_points += points
                contributions.append(
                    FactualContribution(
                        reference_steam_app_id=(
                            reference.steam_app_id
                        ),
                        facet_kind=facet_kind,
                        facet_igdb_id=facet_igdb_id,
                        match_state=match_state,
                        points_numerator=points.numerator,
                        points_denominator=points.denominator,
                    )
                )

    evidence = FactualScoreEvidence(
        version=FACTUAL_SCORING_VERSION,
        score_basis_points=_round_half_up(total_points),
        active_budget=active_budget,
        contributions=tuple(contributions),
    )
    return FactualScoredCandidate(
        steam_app_id=candidate.steam_app_id,
        evidence=evidence,
    )


def order_factual_candidates(
    candidates: Iterable[FactualScoredCandidate],
) -> tuple[FactualScoredCandidate, ...]:
    """Return factual candidates in their canonical deterministic order."""
    return tuple(
        sorted(
            candidates,
            key=lambda candidate: (
                -candidate.evidence.score_basis_points,
                candidate.steam_app_id,
            ),
        )
    )
