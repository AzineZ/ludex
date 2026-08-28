from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.recommendations.candidate_reads import load_candidate_facts
from app.recommendations.contracts import RecommendationPreference
from app.recommendations.eligibility import evaluate_candidate_eligibility
from app.recommendations.factual_scoring import (
    FacetKind,
    FactualScoredCandidate,
    order_factual_candidates,
    score_factual_candidate,
)
from app.recommendations.preference_validation import validate_preference

FACTUAL_CANDIDATE_POOL_SIZE = 15

_FACET_FIELD_BY_KIND = {
    FacetKind.GENRE: "genre_ids",
    FacetKind.THEME: "theme_ids",
    FacetKind.KEYWORD: "keyword_ids",
    FacetKind.GAME_MODE: "game_mode_ids",
}


@dataclass(frozen=True)
class FactualCandidatePool:
    """Return one bounded factual ranking and its eligible population."""

    candidates: tuple[FactualScoredCandidate, ...]
    eligible_count: int

    @property
    def returned_count(self) -> int:
        """Derive the number of candidates retained in the pool."""
        return len(self.candidates)

    @property
    def is_truncated(self) -> bool:
        """Report whether eligible candidates exist beyond this pool."""
        return self.eligible_count > self.returned_count


def _active_facet_kinds(
    preference: RecommendationPreference,
) -> frozenset[FacetKind]:
    """Identify kinds selected by at least one reference."""
    return frozenset(
        kind
        for kind, field in _FACET_FIELD_BY_KIND.items()
        if any(
            getattr(reference.facets, field)
            for reference in preference.references
        )
    )


def retrieve_factual_candidates(
    session: Session,
    *,
    profile_id: int,
    preference: RecommendationPreference,
    session_excluded_steam_app_ids: frozenset[int],
) -> FactualCandidatePool:
    """Build one deterministic factual pool from cached owned games."""
    validated = validate_preference(
        session,
        profile_id,
        preference,
    )
    validated_preference = validated.preference
    candidates = load_candidate_facts(
        session,
        profile_id,
        active_facet_kinds=_active_facet_kinds(
            validated_preference
        ),
    )
    reference_steam_app_ids = frozenset(
        reference.steam_app_id
        for reference in validated_preference.references
    )
    constraints = validated_preference.constraints

    scored_candidates: list[FactualScoredCandidate] = []
    for candidate in candidates:
        eligibility = evaluate_candidate_eligibility(
            candidate,
            reference_steam_app_ids=reference_steam_app_ids,
            session_excluded_steam_app_ids=(
                session_excluded_steam_app_ids
            ),
            play_status=constraints.play_status,
            maximum_completion_minutes=(
                constraints.maximum_completion_minutes
            ),
        )
        if not eligibility.eligible:
            continue

        scored_candidates.append(
            score_factual_candidate(
                candidate,
                validated_preference,
            )
        )

    ordered_candidates = order_factual_candidates(scored_candidates)
    eligible_count = len(ordered_candidates)
    return FactualCandidatePool(
        candidates=ordered_candidates[:FACTUAL_CANDIDATE_POOL_SIZE],
        eligible_count=eligible_count,
    )
