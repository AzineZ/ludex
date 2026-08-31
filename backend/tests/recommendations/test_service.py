from unittest.mock import Mock

import pytest
from sqlalchemy.orm import Session

import app.recommendations.service as service_module
from app.recommendations.contracts import (
    PlayStatus,
    PreferenceConstraints,
    RecommendationPreference,
    ReferencePreference,
    SelectedFacets,
)
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
    FinalRecommendationResult,
    RecommendationOutcome,
)
from app.recommendations.presentation_reads import (
    FinalResultPresentationProjection,
)
from app.recommendations.retrieval import FactualCandidatePool
from app.recommendations.service import recommend_cached_games


def _preference() -> RecommendationPreference:
    return RecommendationPreference(
        references=(
            ReferencePreference(
                steam_app_id=400,
                facets=SelectedFacets(
                    genre_ids=(9,),
                    theme_ids=(),
                    keyword_ids=(),
                    game_mode_ids=(),
                ),
            ),
        ),
        constraints=PreferenceConstraints(
            maximum_completion_minutes=None,
            play_status=PlayStatus.EITHER,
        ),
    )


def _candidate(
    steam_app_id: int,
    facet_kind: FacetKind,
    facet_igdb_id: int,
) -> FactualScoredCandidate:
    return FactualScoredCandidate(
        steam_app_id=steam_app_id,
        evidence=FactualScoreEvidence(
            version="factual-overlap-v1",
            score_basis_points=10_000,
            active_budget=100,
            contributions=(
                FactualContribution(
                    reference_steam_app_id=400,
                    facet_kind=facet_kind,
                    facet_igdb_id=facet_igdb_id,
                    match_state=FacetMatchState.MATCHED,
                    points_numerator=10_000,
                    points_denominator=1,
                ),
            ),
        ),
    )


def _presentation(steam_app_id: int) -> CandidatePresentationFacts:
    return CandidatePresentationFacts(
        steam_app_id=steam_app_id,
        title=f"Game {steam_app_id}",
        cover_url=None,
        profile_playtime_minutes=0,
        normal_completion_seconds=3_600,
    )


def test_service_composes_one_retrieval_projection_and_assembly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = Mock(spec=Session)
    preference = _preference()
    selected_candidates = tuple(
        _candidate(100 + index, FacetKind.GENRE, 9)
        for index in range(1, 7)
    )
    seventh_candidate = _candidate(107, FacetKind.THEME, 18)
    pool = FactualCandidatePool(
        candidates=selected_candidates + (seventh_candidate,),
        eligible_count=92,
    )
    projection = FinalResultPresentationProjection(
        presentations=tuple(
            _presentation(candidate.steam_app_id)
            for candidate in selected_candidates
        ),
        facet_labels=(FacetLabel(FacetKind.GENRE, 9, "Puzzle"),),
    )
    expected = FinalRecommendationResult(eligible_count=0, items=())
    calls: list[tuple[str, object]] = []

    def retrieve(
        received_session: Session,
        *,
        profile_id: int,
        preference: RecommendationPreference,
        session_excluded_steam_app_ids: frozenset[int],
    ) -> FactualCandidatePool:
        calls.append(
            (
                "retrieve",
                (
                    received_session,
                    profile_id,
                    preference,
                    session_excluded_steam_app_ids,
                ),
            )
        )
        return pool

    def project(
        received_session: Session,
        profile_id: int,
        *,
        selected_steam_app_ids: tuple[int, ...],
        facet_identities: frozenset[tuple[FacetKind, int]],
    ) -> FinalResultPresentationProjection:
        calls.append(
            (
                "project",
                (
                    received_session,
                    profile_id,
                    selected_steam_app_ids,
                    facet_identities,
                ),
            )
        )
        return projection

    def assemble(
        received_pool: FactualCandidatePool,
        presentations: tuple[CandidatePresentationFacts, ...],
        facet_labels: tuple[FacetLabel, ...],
    ) -> FinalRecommendationResult:
        calls.append(
            (
                "assemble",
                (received_pool, presentations, facet_labels),
            )
        )
        return expected

    monkeypatch.setattr(service_module, "retrieve_factual_candidates", retrieve)
    monkeypatch.setattr(
        service_module,
        "load_final_result_presentation",
        project,
    )
    monkeypatch.setattr(
        service_module,
        "assemble_final_recommendations",
        assemble,
    )

    result = recommend_cached_games(
        session,
        profile_id=7,
        preference=preference,
    )

    assert result is expected
    assert calls == [
        ("retrieve", (session, 7, preference, frozenset())),
        (
            "project",
            (
                session,
                7,
                (101, 102, 103, 104, 105, 106),
                frozenset({(FacetKind.GENRE, 9)}),
            ),
        ),
        (
            "assemble",
            (pool, projection.presentations, projection.facet_labels),
        ),
    ]


def test_service_passes_session_exclusions_to_retrieval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = Mock(spec=Session)
    exclusions = frozenset({201, 203})
    received_exclusions: list[frozenset[int]] = []
    pool = FactualCandidatePool(candidates=(), eligible_count=0)

    def retrieve(
        received_session: Session,
        *,
        profile_id: int,
        preference: RecommendationPreference,
        session_excluded_steam_app_ids: frozenset[int],
    ) -> FactualCandidatePool:
        received_exclusions.append(session_excluded_steam_app_ids)
        return pool

    monkeypatch.setattr(
        service_module,
        "retrieve_factual_candidates",
        retrieve,
    )
    monkeypatch.setattr(
        service_module,
        "load_final_result_presentation",
        lambda *args, **kwargs: FinalResultPresentationProjection((), ()),
    )

    result = recommend_cached_games(
        session,
        profile_id=7,
        preference=_preference(),
        session_excluded_steam_app_ids=exclusions,
    )

    assert result.outcome is RecommendationOutcome.EMPTY
    assert received_exclusions == [exclusions]


def test_empty_pool_flows_through_zero_input_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = Mock(spec=Session)
    pool = FactualCandidatePool(candidates=(), eligible_count=0)
    projection_arguments: list[
        tuple[tuple[int, ...], frozenset[tuple[FacetKind, int]]]
    ] = []

    monkeypatch.setattr(
        service_module,
        "retrieve_factual_candidates",
        lambda *args, **kwargs: pool,
    )

    def project(
        received_session: Session,
        profile_id: int,
        *,
        selected_steam_app_ids: tuple[int, ...],
        facet_identities: frozenset[tuple[FacetKind, int]],
    ) -> FinalResultPresentationProjection:
        projection_arguments.append(
            (selected_steam_app_ids, facet_identities)
        )
        return FinalResultPresentationProjection((), ())

    monkeypatch.setattr(
        service_module,
        "load_final_result_presentation",
        project,
    )

    result = recommend_cached_games(
        session,
        profile_id=1,
        preference=_preference(),
    )

    assert projection_arguments == [((), frozenset())]
    assert result.outcome is RecommendationOutcome.EMPTY
    assert result.items == ()


def test_retrieval_failure_stops_before_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = Mock(spec=Session)
    projection_called = False

    def fail_retrieval(*args: object, **kwargs: object) -> FactualCandidatePool:
        raise RuntimeError("retrieval failed")

    def record_projection(
        *args: object,
        **kwargs: object,
    ) -> FinalResultPresentationProjection:
        nonlocal projection_called
        projection_called = True
        return FinalResultPresentationProjection((), ())

    monkeypatch.setattr(
        service_module,
        "retrieve_factual_candidates",
        fail_retrieval,
    )
    monkeypatch.setattr(
        service_module,
        "load_final_result_presentation",
        record_projection,
    )

    with pytest.raises(RuntimeError, match="retrieval failed"):
        recommend_cached_games(
            session,
            profile_id=1,
            preference=_preference(),
        )

    assert projection_called is False
