from app.recommendations.candidate_facts import CandidateFacts
from app.recommendations.contracts import (
    PlayStatus,
    PreferenceConstraints,
    RecommendationPreference,
    ReferencePreference,
    SelectedFacets,
)
from app.recommendations.eligibility import (
    EligibilityExclusionReason,
    evaluate_candidate_eligibility,
)
from app.recommendations.factual_scoring import (
    FactualScoredCandidate,
    order_factual_candidates,
    score_factual_candidate,
)


def _preference(
    reference_steam_app_id: int,
    *,
    genre_ids: tuple[int, ...] = (),
    theme_ids: tuple[int, ...] = (),
    keyword_ids: tuple[int, ...] = (),
    game_mode_ids: tuple[int, ...] = (),
) -> RecommendationPreference:
    return RecommendationPreference(
        references=(
            ReferencePreference(
                steam_app_id=reference_steam_app_id,
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


def _candidate(
    steam_app_id: int,
    *,
    genre_ids: tuple[int, ...] = (),
    theme_ids: tuple[int, ...] = (),
    keyword_ids: tuple[int, ...] = (),
    game_mode_ids: tuple[int, ...] = (),
    total_playtime_minutes: int = 0,
    normal_completion_seconds: int | None = None,
) -> CandidateFacts:
    return CandidateFacts(
        steam_app_id=steam_app_id,
        owned_by_selected_profile=True,
        total_playtime_minutes=total_playtime_minutes,
        normal_completion_seconds=normal_completion_seconds,
        genre_ids=genre_ids,
        theme_ids=theme_ids,
        keyword_ids=keyword_ids,
        game_mode_ids=game_mode_ids,
    )


def _score_candidates(
    preference: RecommendationPreference,
    *candidates: CandidateFacts,
) -> tuple[FactualScoredCandidate, ...]:
    return order_factual_candidates(
        score_factual_candidate(candidate, preference)
        for candidate in candidates
    )


def test_balatro_profile_separates_card_matches_from_mode_only_matches() -> None:
    preference = _preference(
        2_379_780,
        genre_ids=(35,),
        keyword_ids=(25_688,),
        game_mode_ids=(1,),
    )

    results = _score_candidates(
        preference,
        _candidate(286_160, genre_ids=(35,), game_mode_ids=(1,)),
        _candidate(2_141_910, genre_ids=(35,), keyword_ids=(25_688,)),
        _candidate(436_150, genre_ids=(35,)),
        _candidate(220, game_mode_ids=(1,)),
        _candidate(999_001),
    )

    assert tuple(
        (candidate.steam_app_id, candidate.evidence.score_basis_points)
        for candidate in results
    ) == (
        (286_160, 7_333),  # Tabletop Simulator
        (2_141_910, 6_667),  # Magic: The Gathering Arena
        (436_150, 4_000),  # Governor of Poker 3
        (220, 3_333),  # Half-Life 2: game-mode-only match
        (999_001, 0),
    )


def test_portal_profile_records_strong_matches_and_broad_factual_ties() -> None:
    preference = _preference(
        400,
        genre_ids=(9,),
        theme_ids=(18,),
        keyword_ids=(4_928,),
        game_mode_ids=(1,),
    )

    results = _score_candidates(
        preference,
        _candidate(620, genre_ids=(9,), theme_ids=(18,), game_mode_ids=(1,)),
        _candidate(
            317_400,
            genre_ids=(9,),
            theme_ids=(18,),
            game_mode_ids=(1,),
        ),
        _candidate(
            920_210,
            genre_ids=(9,),
            theme_ids=(18,),
            game_mode_ids=(1,),
        ),
        _candidate(
            220,
            theme_ids=(18,),
            keyword_ids=(4_928,),
            game_mode_ids=(1,),
        ),
        _candidate(736_260, genre_ids=(9,), game_mode_ids=(1,)),
        _candidate(2_280, theme_ids=(18,), game_mode_ids=(1,)),
    )

    assert tuple(
        (candidate.steam_app_id, candidate.evidence.score_basis_points)
        for candidate in results
    ) == (
        (620, 8_000),  # Portal 2
        (317_400, 8_000),  # Portal Stories: Mel
        (920_210, 8_000),  # Accepted broad-facet tie
        (220, 7_000),  # Half-Life 2
        (736_260, 5_500),  # Baba Is You
        (2_280, 5_000),  # Theme-and-mode-only match
    )


def test_civilization_profile_places_direct_sequel_above_partial_matches() -> None:
    preference = _preference(
        8_930,
        genre_ids=(16,),
        theme_ids=(41,),
        keyword_ids=(415,),
        game_mode_ids=(1, 2),
    )

    results = _score_candidates(
        preference,
        _candidate(
            289_070,
            genre_ids=(16,),
            theme_ids=(41,),
            keyword_ids=(415,),
            game_mode_ids=(1, 2),
        ),
        _candidate(
            1_086_940,
            genre_ids=(16,),
            keyword_ids=(415,),
            game_mode_ids=(1, 2),
        ),
        _candidate(9_050, keyword_ids=(415,), game_mode_ids=(1, 2)),
        _candidate(436_150, genre_ids=(16,), game_mode_ids=(2,)),
        _candidate(550, game_mode_ids=(1, 2)),
    )

    assert tuple(
        (candidate.steam_app_id, candidate.evidence.score_basis_points)
        for candidate in results
    ) == (
        (289_070, 10_000),  # Civilization VI
        (1_086_940, 7_500),  # Baldur's Gate 3
        (9_050, 4_500),  # Accepted cached-keyword surprise
        (436_150, 4_250),
        (550, 2_500),
    )


def test_hades_profile_places_direct_predecessor_above_broad_fantasy() -> None:
    preference = _preference(
        1_145_350,
        genre_ids=(25,),
        theme_ids=(17,),
        keyword_ids=(17_292,),
        game_mode_ids=(1,),
    )

    results = _score_candidates(
        preference,
        _candidate(
            1_145_360,
            genre_ids=(25,),
            theme_ids=(17,),
            keyword_ids=(17_292,),
            game_mode_ids=(1,),
        ),
        _candidate(204_360, genre_ids=(25,), game_mode_ids=(1,)),
        _candidate(8_930, theme_ids=(17,), game_mode_ids=(1,)),
        _candidate(220, game_mode_ids=(1,)),
    )

    assert tuple(
        (candidate.steam_app_id, candidate.evidence.score_basis_points)
        for candidate in results
    ) == (
        (1_145_360, 10_000),  # Hades
        (204_360, 5_500),  # Castle Crashers
        (8_930, 5_000),  # Broad fantasy-and-mode match
        (220, 2_500),  # Mode-only match
    )


def test_hard_constraints_override_an_otherwise_perfect_quality_match() -> None:
    candidate = _candidate(
        1_145_360,
        genre_ids=(25,),
        theme_ids=(17,),
        keyword_ids=(17_292,),
        game_mode_ids=(1,),
        total_playtime_minutes=1,
        normal_completion_seconds=None,
    )
    preference = _preference(
        1_145_350,
        genre_ids=(25,),
        theme_ids=(17,),
        keyword_ids=(17_292,),
        game_mode_ids=(1,),
    )
    score = score_factual_candidate(candidate, preference)

    decision = evaluate_candidate_eligibility(
        candidate,
        reference_steam_app_ids=frozenset({1_145_350}),
        session_excluded_steam_app_ids=frozenset({1_145_360}),
        play_status=PlayStatus.UNPLAYED,
        maximum_completion_minutes=60,
    )

    assert score.evidence.score_basis_points == 10_000
    assert decision.eligible is False
    assert decision.exclusion_reasons == (
        EligibilityExclusionReason.SESSION_EXCLUDED,
        EligibilityExclusionReason.PLAY_STATUS_MISMATCH,
        EligibilityExclusionReason.COMPLETION_TIME_UNKNOWN,
    )
