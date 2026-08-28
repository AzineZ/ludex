from dataclasses import FrozenInstanceError
from fractions import Fraction

import pytest

from app.recommendations.candidate_facts import CandidateFacts
from app.recommendations.contracts import (
    PlayStatus,
    PreferenceConstraints,
    RecommendationPreference,
    ReferencePreference,
    SelectedFacets,
)
from app.recommendations.factual_scoring import (
    FACTUAL_SCORING_VERSION,
    FacetKind,
    FacetMatchState,
    FactualContribution,
    order_factual_candidates,
    score_factual_candidate,
)


def _preference(*genre_ids: int) -> RecommendationPreference:
    return RecommendationPreference(
        references=(
            ReferencePreference(
                steam_app_id=101,
                facets=SelectedFacets(
                    genre_ids=genre_ids,
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
    genre_ids: tuple[int, ...] | None = None,
    *,
    steam_app_id: int = 500,
    theme_ids: tuple[int, ...] | None = None,
    keyword_ids: tuple[int, ...] | None = None,
    game_mode_ids: tuple[int, ...] | None = None,
) -> CandidateFacts:
    return CandidateFacts(
        steam_app_id=steam_app_id,
        owned_by_selected_profile=True,
        total_playtime_minutes=0,
        normal_completion_seconds=None,
        genre_ids=genre_ids,
        theme_ids=theme_ids,
        keyword_ids=keyword_ids,
        game_mode_ids=game_mode_ids,
    )


def _custom_preference(
    *,
    genre_ids: tuple[int, ...] = (),
    theme_ids: tuple[int, ...] = (),
    keyword_ids: tuple[int, ...] = (),
    game_mode_ids: tuple[int, ...] = (),
) -> RecommendationPreference:
    return RecommendationPreference(
        references=(
            ReferencePreference(
                steam_app_id=101,
                facets=SelectedFacets(
                    genre_ids=genre_ids,
                    theme_ids=theme_ids,
                    keyword_ids=keyword_ids,
                    game_mode_ids=game_mode_ids,
                ),
            ),
        ),
        constraints=PreferenceConstraints(
            maximum_completion_minutes=None,
            play_status=PlayStatus.EITHER,
        ),
    )


def _reference(
    steam_app_id: int,
    *,
    genre_ids: tuple[int, ...] = (),
    theme_ids: tuple[int, ...] = (),
    keyword_ids: tuple[int, ...] = (),
    game_mode_ids: tuple[int, ...] = (),
) -> ReferencePreference:
    return ReferencePreference(
        steam_app_id=steam_app_id,
        facets=SelectedFacets(
            genre_ids=genre_ids,
            theme_ids=theme_ids,
            keyword_ids=keyword_ids,
            game_mode_ids=game_mode_ids,
        ),
    )


def _multi_reference_preference(
    *references: ReferencePreference,
) -> RecommendationPreference:
    return RecommendationPreference(
        references=references,
        constraints=PreferenceConstraints(
            maximum_completion_minutes=None,
            play_status=PlayStatus.EITHER,
        ),
    )


def _worked_preference() -> RecommendationPreference:
    return _multi_reference_preference(
        _reference(
            101,
            genre_ids=(10, 20),
            theme_ids=(30,),
            keyword_ids=(40, 50, 60),
            game_mode_ids=(70,),
        ),
        _reference(
            202,
            genre_ids=(10,),
            theme_ids=(31,),
            keyword_ids=(50, 51),
            game_mode_ids=(70, 71),
        ),
    )


def test_single_selected_genre_full_match_scores_10000() -> None:
    result = score_factual_candidate(
        _candidate((10, 999)),
        _preference(10),
    )

    assert result.steam_app_id == 500
    assert result.evidence.version == FACTUAL_SCORING_VERSION
    assert result.evidence.score_basis_points == 10_000
    assert result.evidence.active_budget == 30
    assert result.evidence.contributions == (
        FactualContribution(
            reference_steam_app_id=101,
            facet_kind=FacetKind.GENRE,
            facet_igdb_id=10,
            match_state=FacetMatchState.MATCHED,
            points_numerator=10_000,
            points_denominator=1,
        ),
    )


def test_selected_genres_share_the_kind_budget_equally() -> None:
    result = score_factual_candidate(
        _candidate((10,)),
        _preference(10, 20),
    )

    assert result.evidence.score_basis_points == 5_000
    assert result.evidence.contributions == (
        FactualContribution(
            reference_steam_app_id=101,
            facet_kind=FacetKind.GENRE,
            facet_igdb_id=10,
            match_state=FacetMatchState.MATCHED,
            points_numerator=5_000,
            points_denominator=1,
        ),
        FactualContribution(
            reference_steam_app_id=101,
            facet_kind=FacetKind.GENRE,
            facet_igdb_id=20,
            match_state=FacetMatchState.NOT_MATCHED,
            points_numerator=0,
            points_denominator=1,
        ),
    )


@pytest.mark.parametrize(
    ("candidate_genres", "match_state"),
    [
        (None, FacetMatchState.UNKNOWN),
        ((), FacetMatchState.NOT_MATCHED),
        ((999,), FacetMatchState.NOT_MATCHED),
    ],
)
def test_zero_match_distinguishes_unknown_from_known_nonmatch(
    candidate_genres: tuple[int, ...] | None,
    match_state: FacetMatchState,
) -> None:
    result = score_factual_candidate(
        _candidate(candidate_genres),
        _preference(10),
    )

    assert result.evidence.score_basis_points == 0
    assert result.evidence.contributions[0].match_state is match_state
    assert result.evidence.contributions[0].points_numerator == 0
    assert result.evidence.contributions[0].points_denominator == 1


def test_scoring_evidence_is_immutable() -> None:
    result = score_factual_candidate(
        _candidate((10,)),
        _preference(10),
    )

    with pytest.raises(FrozenInstanceError):
        result.evidence.score_basis_points = 0  # type: ignore[misc]


@pytest.mark.parametrize(
    ("facet_kind", "active_budget", "preference", "candidate"),
    [
        (
            FacetKind.THEME,
            25,
            _custom_preference(theme_ids=(20,)),
            _candidate(theme_ids=(20,)),
        ),
        (
            FacetKind.KEYWORD,
            20,
            _custom_preference(keyword_ids=(30,)),
            _candidate(keyword_ids=(30,)),
        ),
        (
            FacetKind.GAME_MODE,
            25,
            _custom_preference(game_mode_ids=(40,)),
            _candidate(game_mode_ids=(40,)),
        ),
    ],
)
def test_each_non_genre_kind_can_independently_score_full_overlap(
    facet_kind: FacetKind,
    active_budget: int,
    preference: RecommendationPreference,
    candidate: CandidateFacts,
) -> None:
    result = score_factual_candidate(candidate, preference)

    assert result.evidence.score_basis_points == 10_000
    assert result.evidence.active_budget == active_budget
    assert result.evidence.contributions[0].facet_kind is facet_kind
    assert result.evidence.contributions[0].points_numerator == 10_000
    assert result.evidence.contributions[0].points_denominator == 1


def test_final_score_normalizes_against_only_active_kind_budgets() -> None:
    preference = _custom_preference(
        genre_ids=(10,),
        theme_ids=(20,),
    )
    candidate = _candidate(
        (10,),
        theme_ids=(),
    )

    result = score_factual_candidate(candidate, preference)

    assert result.evidence.active_budget == 55
    assert result.evidence.score_basis_points == 5_455
    assert result.evidence.contributions[0].points_numerator == 60_000
    assert result.evidence.contributions[0].points_denominator == 11


def test_irrelevant_keyword_volume_does_not_change_score() -> None:
    preference = _custom_preference(keyword_ids=(30, 40, 50))
    concise_candidate = _candidate(keyword_ids=(30,))
    noisy_candidate = _candidate(
        keyword_ids=(30, *range(1_000, 1_200)),
    )

    concise = score_factual_candidate(concise_candidate, preference)
    noisy = score_factual_candidate(noisy_candidate, preference)

    assert concise.evidence.score_basis_points == 3_333
    assert noisy.evidence.score_basis_points == 3_333
    assert noisy.evidence.contributions == concise.evidence.contributions


def test_evidence_uses_canonical_kind_then_facet_order() -> None:
    preference = _custom_preference(
        genre_ids=(20, 10),
        theme_ids=(31, 30),
        keyword_ids=(51, 50),
        game_mode_ids=(71, 70),
    )
    candidate = _candidate(
        (),
        theme_ids=(),
        keyword_ids=(),
        game_mode_ids=(),
    )

    result = score_factual_candidate(candidate, preference)

    assert [
        (row.facet_kind, row.facet_igdb_id)
        for row in result.evidence.contributions
    ] == [
        (FacetKind.GENRE, 10),
        (FacetKind.GENRE, 20),
        (FacetKind.THEME, 30),
        (FacetKind.THEME, 31),
        (FacetKind.KEYWORD, 50),
        (FacetKind.KEYWORD, 51),
        (FacetKind.GAME_MODE, 70),
        (FacetKind.GAME_MODE, 71),
    ]


def test_exact_half_point_rounds_up_once() -> None:
    preference = _custom_preference(
        genre_ids=(10,),
        theme_ids=tuple(range(20, 28)),
        keyword_ids=(30,),
        game_mode_ids=(40,),
    )
    candidate = _candidate(
        (),
        theme_ids=(20,),
        keyword_ids=(),
        game_mode_ids=(),
    )

    result = score_factual_candidate(candidate, preference)

    assert result.evidence.active_budget == 100
    assert result.evidence.score_basis_points == 313
    matched_row = next(
        row
        for row in result.evidence.contributions
        if row.match_state is FacetMatchState.MATCHED
    )
    assert matched_row.points_numerator == 625
    assert matched_row.points_denominator == 2


@pytest.mark.parametrize(
    ("candidate", "expected_score"),
    [
        (
            _candidate(
                (10, 20),
                steam_app_id=3_500,
                theme_ids=(30, 31),
                keyword_ids=(40, 50, 51, 60),
                game_mode_ids=(70, 71),
            ),
            10_000,
        ),
        (
            _candidate(
                (10,),
                steam_app_id=3_001,
                theme_ids=(30,),
                keyword_ids=(50,),
                game_mode_ids=(70,),
            ),
            6_208,
        ),
        (
            _candidate(
                (10,),
                steam_app_id=3_002,
                theme_ids=(30,),
                keyword_ids=(50, *range(1_000, 1_200)),
                game_mode_ids=(70,),
            ),
            6_208,
        ),
        (
            _candidate(
                (20,),
                steam_app_id=2_500,
                theme_ids=(31,),
                keyword_ids=(51,),
                game_mode_ids=(71,),
            ),
            3_125,
        ),
        (_candidate(steam_app_id=1_000), 0),
        (
            _candidate(
                (),
                steam_app_id=4_000,
                theme_ids=(),
                keyword_ids=(),
                game_mode_ids=(),
            ),
            0,
        ),
    ],
)
def test_approved_worked_candidates_match_hand_calculation(
    candidate: CandidateFacts,
    expected_score: int,
) -> None:
    result = score_factual_candidate(candidate, _worked_preference())

    assert result.evidence.score_basis_points == expected_score


def test_repeated_facets_remain_one_assertion_per_reference() -> None:
    result = score_factual_candidate(
        _candidate(
            (10,),
            theme_ids=(),
            keyword_ids=(),
            game_mode_ids=(),
        ),
        _worked_preference(),
    )

    repeated_genre_rows = tuple(
        row
        for row in result.evidence.contributions
        if row.facet_kind is FacetKind.GENRE
        and row.facet_igdb_id == 10
    )
    assert [
        row.reference_steam_app_id for row in repeated_genre_rows
    ] == [101, 202]
    assert all(
        row.match_state is FacetMatchState.MATCHED
        for row in repeated_genre_rows
    )


def test_worked_partial_match_evidence_sums_to_exact_total() -> None:
    result = score_factual_candidate(
        _candidate(
            (10,),
            theme_ids=(30,),
            keyword_ids=(50,),
            game_mode_ids=(70,),
        ),
        _worked_preference(),
    )

    exact_total = sum(
        (
            Fraction(row.points_numerator, row.points_denominator)
            for row in result.evidence.contributions
        ),
        start=Fraction(0),
    )
    assert exact_total == Fraction(18_625, 3)
    assert result.evidence.score_basis_points == 6_208


def test_reference_inactive_in_kind_is_absent_from_kind_denominator() -> None:
    preference = _multi_reference_preference(
        _reference(101, genre_ids=(10,)),
        _reference(202, theme_ids=(20,)),
    )
    candidate = _candidate((10,), theme_ids=())

    result = score_factual_candidate(candidate, preference)

    assert result.evidence.score_basis_points == 5_455
    genre_row = result.evidence.contributions[0]
    assert genre_row.points_numerator == 60_000
    assert genre_row.points_denominator == 11


def test_multi_reference_scoring_does_not_require_intersection() -> None:
    preference = _multi_reference_preference(
        _reference(101, genre_ids=(10,)),
        _reference(202, genre_ids=(20,)),
    )

    result = score_factual_candidate(_candidate((10,)), preference)

    assert result.evidence.score_basis_points == 5_000
    assert tuple(
        row.match_state for row in result.evidence.contributions
    ) == (
        FacetMatchState.MATCHED,
        FacetMatchState.NOT_MATCHED,
    )


def test_reference_permutation_preserves_score_but_orders_its_evidence() -> None:
    preference = _worked_preference()
    reversed_preference = _multi_reference_preference(
        *reversed(preference.references)
    )
    candidate = _candidate(
        (10,),
        theme_ids=(30,),
        keyword_ids=(50,),
        game_mode_ids=(70,),
    )

    original = score_factual_candidate(candidate, preference)
    reversed_result = score_factual_candidate(
        candidate,
        reversed_preference,
    )

    assert original.evidence.score_basis_points == 6_208
    assert reversed_result.evidence.score_basis_points == 6_208
    assert original.evidence.contributions[0].reference_steam_app_id == 101
    assert (
        reversed_result.evidence.contributions[0].reference_steam_app_id
        == 202
    )


def test_candidates_order_by_score_then_steam_app_id() -> None:
    preference = _worked_preference()
    candidates = (
        _candidate(
            (),
            steam_app_id=4_000,
            theme_ids=(),
            keyword_ids=(),
            game_mode_ids=(),
        ),
        _candidate(
            (10,),
            steam_app_id=3_002,
            theme_ids=(30,),
            keyword_ids=(50, *range(1_000, 1_200)),
            game_mode_ids=(70,),
        ),
        _candidate(steam_app_id=1_000),
        _candidate(
            (10,),
            steam_app_id=3_001,
            theme_ids=(30,),
            keyword_ids=(50,),
            game_mode_ids=(70,),
        ),
        _candidate(
            (20,),
            steam_app_id=2_500,
            theme_ids=(31,),
            keyword_ids=(51,),
            game_mode_ids=(71,),
        ),
        _candidate(
            (10, 20),
            steam_app_id=3_500,
            theme_ids=(30, 31),
            keyword_ids=(40, 50, 51, 60),
            game_mode_ids=(70, 71),
        ),
    )
    scored = tuple(
        score_factual_candidate(candidate, preference)
        for candidate in candidates
    )

    ordered = order_factual_candidates(scored)

    assert tuple(item.steam_app_id for item in ordered) == (
        3_500,
        3_001,
        3_002,
        2_500,
        1_000,
        4_000,
    )
