from sqlalchemy.orm import Session

from app.recommendations.contracts import RecommendationPreference
from app.recommendations.final_results import (
    FINAL_RECOMMENDATION_LIMIT,
    FinalRecommendationResult,
    assemble_final_recommendations,
)
from app.recommendations.presentation_reads import (
    load_final_result_presentation,
)
from app.recommendations.retrieval import retrieve_factual_candidates


def recommend_cached_games(
    session: Session,
    *,
    profile_id: int,
    preference: RecommendationPreference,
) -> FinalRecommendationResult:
    """Build final recommendations using only one profile's cached facts."""
    candidate_pool = retrieve_factual_candidates(
        session,
        profile_id=profile_id,
        preference=preference,
        session_excluded_steam_app_ids=frozenset(),
    )
    selected_candidates = candidate_pool.candidates[
        :FINAL_RECOMMENDATION_LIMIT
    ]
    selected_steam_app_ids = tuple(
        candidate.steam_app_id for candidate in selected_candidates
    )
    facet_identities = frozenset(
        (
            contribution.facet_kind,
            contribution.facet_igdb_id,
        )
        for candidate in selected_candidates
        for contribution in candidate.evidence.contributions
    )

    projection = load_final_result_presentation(
        session,
        profile_id,
        selected_steam_app_ids=selected_steam_app_ids,
        facet_identities=facet_identities,
    )
    return assemble_final_recommendations(
        candidate_pool,
        projection.presentations,
        projection.facet_labels,
    )
