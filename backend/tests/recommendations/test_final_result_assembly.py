import pytest

from app.recommendations.factual_scoring import (
    FacetKind,
    FacetMatchState,
    FactualContribution,
    FactualScoreEvidence,
    FactualScoredCandidate,
)
from app.recommendations.final_results import (
    CandidatePresentationFacts,
    FacetLabel,
    RecommendationOutcome,
    assemble_final_recommendations,
)
from app.recommendations.retrieval import FactualCandidatePool


def _candidate(
    steam_app_id: int,
    score_basis_points: int,
) -> FactualScoredCandidate:
    return FactualScoredCandidate(
        steam_app_id=steam_app_id,
        evidence=FactualScoreEvidence(
            version="factual-overlap-v1",
            score_basis_points=score_basis_points,
            active_budget=30,
            contributions=(
                FactualContribution(
                    reference_steam_app_id=400,
                    facet_kind=FacetKind.GENRE,
                    facet_igdb_id=9,
                    match_state=FacetMatchState.MATCHED,
                    points_numerator=score_basis_points,
                    points_denominator=1,
                ),
            ),
        ),
    )


def _presentation(steam_app_id: int) -> CandidatePresentationFacts:
    return CandidatePresentationFacts(
        steam_app_id=steam_app_id,
        title=f"Game {steam_app_id}",
        cover_url=f"https://images.example/{steam_app_id}.jpg",
        profile_playtime_minutes=steam_app_id,
        normal_completion_seconds=3_600,
    )


def _pool(*candidates: FactualScoredCandidate) -> FactualCandidatePool:
    return FactualCandidatePool(
        candidates=candidates,
        eligible_count=len(candidates),
    )


def test_assembly_selects_first_six_and_preserves_factual_order() -> None:
    candidates = tuple(
        _candidate(100 + index, 10_000 - index)
        for index in range(1, 8)
    )
    pool = FactualCandidatePool(candidates=candidates, eligible_count=92)
    presentations = tuple(
        _presentation(candidate.steam_app_id)
        for candidate in reversed(candidates[:6])
    )

    result = assemble_final_recommendations(
        pool,
        presentations,
        (FacetLabel(FacetKind.GENRE, 9, "Puzzle"),),
    )

    assert result.outcome is RecommendationOutcome.COMPLETE
    assert result.eligible_count == 92
    assert result.returned_count == 6
    assert tuple(item.rank for item in result.items) == (1, 2, 3, 4, 5, 6)
    assert tuple(
        item.presentation.steam_app_id for item in result.items
    ) == tuple(candidate.steam_app_id for candidate in candidates[:6])
    assert all(
        item.factual_evidence is candidate.evidence
        for item, candidate in zip(
            result.items,
            candidates[:6],
            strict=True,
        )
    )
    assert all(
        item.match_summary.text == "Matches your Puzzle preference."
        for item in result.items
    )
    assert all(item.tradeoff is None for item in result.items)


def test_assembly_returns_an_empty_result_without_placeholder_records() -> None:
    result = assemble_final_recommendations(_pool(), (), ())

    assert result.outcome is RecommendationOutcome.EMPTY
    assert result.eligible_count == 0
    assert result.returned_count == 0
    assert result.items == ()


def test_assembly_rejects_duplicate_candidate_ids_anywhere_in_pool() -> None:
    duplicate = _candidate(101, 9_000)

    with pytest.raises(ValueError, match="duplicate candidate Steam App ID 101"):
        assemble_final_recommendations(
            _pool(_candidate(101, 10_000), duplicate),
            (_presentation(101),),
            (FacetLabel(FacetKind.GENRE, 9, "Puzzle"),),
        )


def test_assembly_rejects_missing_selected_presentation_record() -> None:
    with pytest.raises(
        ValueError,
        match="missing presentation facts for Steam App ID 102",
    ):
        assemble_final_recommendations(
            _pool(_candidate(101, 10_000), _candidate(102, 9_000)),
            (_presentation(101),),
            (FacetLabel(FacetKind.GENRE, 9, "Puzzle"),),
        )


def test_assembly_rejects_duplicate_presentation_records() -> None:
    with pytest.raises(
        ValueError,
        match="duplicate presentation facts for Steam App ID 101",
    ):
        assemble_final_recommendations(
            _pool(_candidate(101, 10_000)),
            (_presentation(101), _presentation(101)),
            (FacetLabel(FacetKind.GENRE, 9, "Puzzle"),),
        )


def test_assembly_rejects_presentation_for_unselected_pool_candidate() -> None:
    candidates = tuple(
        _candidate(100 + index, 10_000 - index)
        for index in range(1, 8)
    )

    with pytest.raises(
        ValueError,
        match="unexpected presentation facts for Steam App ID 107",
    ):
        assemble_final_recommendations(
            _pool(*candidates),
            tuple(
                _presentation(candidate.steam_app_id)
                for candidate in candidates
            ),
            (FacetLabel(FacetKind.GENRE, 9, "Puzzle"),),
        )


def test_assembly_rejects_presentation_for_candidate_foreign_to_pool() -> None:
    with pytest.raises(
        ValueError,
        match="unexpected presentation facts for Steam App ID 999",
    ):
        assemble_final_recommendations(
            _pool(_candidate(101, 10_000)),
            (_presentation(101), _presentation(999)),
            (FacetLabel(FacetKind.GENRE, 9, "Puzzle"),),
        )


def test_assembly_rejects_duplicate_or_unexpected_facet_labels() -> None:
    candidate = _candidate(101, 10_000)
    presentation = _presentation(101)

    with pytest.raises(ValueError, match="duplicate facet label for genre:9"):
        assemble_final_recommendations(
            _pool(candidate),
            (presentation,),
            (
                FacetLabel(FacetKind.GENRE, 9, "Puzzle"),
                FacetLabel(FacetKind.GENRE, 9, "Puzzle"),
            ),
        )

    with pytest.raises(ValueError, match="unexpected facet label for theme:18"):
        assemble_final_recommendations(
            _pool(candidate),
            (presentation,),
            (
                FacetLabel(FacetKind.GENRE, 9, "Puzzle"),
                FacetLabel(FacetKind.THEME, 18, "Science fiction"),
            ),
        )
