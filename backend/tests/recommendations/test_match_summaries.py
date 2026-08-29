from app.recommendations.factual_scoring import (
    FacetKind,
    FacetMatchState,
    FactualContribution,
    FactualScoreEvidence,
)
from app.recommendations.final_results import (
    FacetLabel,
    MatchReason,
    MatchSummary,
    build_match_summary,
)


def _contribution(
    reference_steam_app_id: int,
    facet_kind: FacetKind,
    facet_igdb_id: int,
    match_state: FacetMatchState,
    points_numerator: int = 0,
    points_denominator: int = 1,
) -> FactualContribution:
    return FactualContribution(
        reference_steam_app_id=reference_steam_app_id,
        facet_kind=facet_kind,
        facet_igdb_id=facet_igdb_id,
        match_state=match_state,
        points_numerator=points_numerator,
        points_denominator=points_denominator,
    )


def _evidence(
    *contributions: FactualContribution,
) -> FactualScoreEvidence:
    return FactualScoreEvidence(
        version="factual-overlap-v1",
        score_basis_points=0,
        active_budget=100,
        contributions=contributions,
    )


def test_zero_matches_uses_the_exact_empty_summary() -> None:
    evidence = _evidence(
        _contribution(
            400,
            FacetKind.GENRE,
            9,
            FacetMatchState.NOT_MATCHED,
        ),
        _contribution(
            400,
            FacetKind.THEME,
            18,
            FacetMatchState.UNKNOWN,
        ),
    )

    result = build_match_summary(
        evidence,
        (
            FacetLabel(FacetKind.GENRE, 9, "Puzzle"),
            FacetLabel(FacetKind.THEME, 18, "Science fiction"),
        ),
    )

    assert result == MatchSummary(
        reasons=(),
        additional_match_count=0,
        text="No selected factual preferences matched.",
    )


def test_one_match_uses_the_exact_singular_wording() -> None:
    result = build_match_summary(
        _evidence(
            _contribution(
                400,
                FacetKind.GENRE,
                9,
                FacetMatchState.MATCHED,
                3_000,
            )
        ),
        (FacetLabel(FacetKind.GENRE, 9, "Puzzle"),),
    )

    assert result.text == "Matches your Puzzle preference."


def test_two_matches_use_the_exact_joined_wording() -> None:
    result = build_match_summary(
        _evidence(
            _contribution(
                400,
                FacetKind.GENRE,
                9,
                FacetMatchState.MATCHED,
                3_000,
            ),
            _contribution(
                400,
                FacetKind.THEME,
                18,
                FacetMatchState.MATCHED,
                2_500,
            ),
        ),
        (
            FacetLabel(FacetKind.GENRE, 9, "Puzzle"),
            FacetLabel(FacetKind.THEME, 18, "Science fiction"),
        ),
    )

    assert result.text == (
        "Matches your Puzzle and Science fiction preferences."
    )


def test_duplicate_selected_facet_collapses_with_exact_aggregate_points() -> None:
    result = build_match_summary(
        _evidence(
            _contribution(
                202,
                FacetKind.GENRE,
                9,
                FacetMatchState.MATCHED,
                3,
                2,
            ),
            _contribution(
                101,
                FacetKind.GENRE,
                9,
                FacetMatchState.MATCHED,
                5,
                2,
            ),
        ),
        (FacetLabel(FacetKind.GENRE, 9, "Puzzle"),),
    )

    assert result.reasons == (
        MatchReason(
            facet_kind=FacetKind.GENRE,
            facet_igdb_id=9,
            name="Puzzle",
            reference_steam_app_ids=(202, 101),
            points_numerator=4,
            points_denominator=1,
        ),
    )


def test_reasons_sort_exactly_then_cap_at_three() -> None:
    result = build_match_summary(
        _evidence(
            _contribution(
                400,
                FacetKind.GAME_MODE,
                1,
                FacetMatchState.MATCHED,
                3_000,
            ),
            _contribution(
                400,
                FacetKind.GENRE,
                10,
                FacetMatchState.MATCHED,
                3_000,
            ),
            _contribution(
                400,
                FacetKind.KEYWORD,
                4_928,
                FacetMatchState.MATCHED,
                4_000,
            ),
            _contribution(
                400,
                FacetKind.THEME,
                18,
                FacetMatchState.MATCHED,
                3_000,
            ),
            _contribution(
                400,
                FacetKind.GENRE,
                9,
                FacetMatchState.MATCHED,
                3_000,
            ),
        ),
        (
            FacetLabel(FacetKind.GENRE, 9, "Puzzle"),
            FacetLabel(FacetKind.GENRE, 10, "Strategy"),
            FacetLabel(FacetKind.THEME, 18, "Science fiction"),
            FacetLabel(FacetKind.KEYWORD, 4_928, "Environmental puzzles"),
            FacetLabel(FacetKind.GAME_MODE, 1, "Single player"),
        ),
    )

    assert tuple(reason.name for reason in result.reasons) == (
        "Environmental puzzles",
        "Puzzle",
        "Strategy",
    )
    assert result.additional_match_count == 2
    assert result.text == (
        "Matches your Environmental puzzles, Puzzle, and Strategy "
        "preferences, plus 2 more."
    )


def test_exact_fractions_control_order_without_early_rounding() -> None:
    result = build_match_summary(
        _evidence(
            _contribution(
                400,
                FacetKind.GENRE,
                9,
                FacetMatchState.MATCHED,
                1,
                3,
            ),
            _contribution(
                400,
                FacetKind.THEME,
                18,
                FacetMatchState.MATCHED,
                2,
                5,
            ),
        ),
        (
            FacetLabel(FacetKind.GENRE, 9, "Puzzle"),
            FacetLabel(FacetKind.THEME, 18, "Science fiction"),
        ),
    )

    assert tuple(reason.name for reason in result.reasons) == (
        "Science fiction",
        "Puzzle",
    )


def test_missing_label_for_any_evidence_facet_fails() -> None:
    evidence = _evidence(
        _contribution(
            400,
            FacetKind.GENRE,
            9,
            FacetMatchState.MATCHED,
            3_000,
        ),
        _contribution(
            400,
            FacetKind.KEYWORD,
            4_928,
            FacetMatchState.NOT_MATCHED,
        ),
    )

    try:
        build_match_summary(
            evidence,
            (FacetLabel(FacetKind.GENRE, 9, "Puzzle"),),
        )
    except ValueError as error:
        assert str(error) == "missing facet label for keyword:4928"
    else:
        raise AssertionError("missing facet label was accepted")
