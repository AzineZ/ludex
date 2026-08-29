import pytest

from app.recommendations.factual_scoring import (
    FacetKind,
    FacetMatchState,
    FactualContribution,
    FactualScoreEvidence,
)
from app.recommendations.final_results import (
    FacetLabel,
    TradeoffType,
    UnknownCompletionTimeTradeoff,
    UnknownPreferenceMetadataTradeoff,
    UnmatchedPreferenceReason,
    UnmatchedPreferenceTradeoff,
    build_tradeoff,
)


def _contribution(
    reference_steam_app_id: int,
    facet_kind: FacetKind,
    facet_igdb_id: int,
    match_state: FacetMatchState,
) -> FactualContribution:
    return FactualContribution(
        reference_steam_app_id=reference_steam_app_id,
        facet_kind=facet_kind,
        facet_igdb_id=facet_igdb_id,
        match_state=match_state,
        points_numerator=(1 if match_state is FacetMatchState.MATCHED else 0),
        points_denominator=1,
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


def _labels(
    *contributions: FactualContribution,
) -> tuple[FacetLabel, ...]:
    names = {
        (FacetKind.GENRE, 9): "Puzzle",
        (FacetKind.GENRE, 10): "Strategy",
        (FacetKind.THEME, 18): "Science fiction",
        (FacetKind.KEYWORD, 4_928): "Environmental puzzles",
        (FacetKind.GAME_MODE, 1): "Single player",
    }
    identities = dict.fromkeys(
        (contribution.facet_kind, contribution.facet_igdb_id)
        for contribution in contributions
    )
    return tuple(
        FacetLabel(kind, igdb_id, names[(kind, igdb_id)])
        for kind, igdb_id in identities
    )


@pytest.mark.parametrize(
    ("unknown_kinds", "expected_text"),
    [
        ((FacetKind.GENRE,), "Genre metadata is unavailable."),
        (
            (FacetKind.GENRE, FacetKind.THEME),
            "Genre and theme metadata are unavailable.",
        ),
        (
            (FacetKind.GENRE, FacetKind.THEME, FacetKind.KEYWORD),
            "Genre, theme, and keyword metadata are unavailable.",
        ),
        (
            (
                FacetKind.GENRE,
                FacetKind.THEME,
                FacetKind.KEYWORD,
                FacetKind.GAME_MODE,
            ),
            (
                "Genre, theme, keyword, and game-mode metadata are "
                "unavailable."
            ),
        ),
    ],
)
def test_unknown_metadata_uses_canonical_kinds_and_exact_wording(
    unknown_kinds: tuple[FacetKind, ...],
    expected_text: str,
) -> None:
    ids = {
        FacetKind.GENRE: 9,
        FacetKind.THEME: 18,
        FacetKind.KEYWORD: 4_928,
        FacetKind.GAME_MODE: 1,
    }
    contributions = tuple(
        _contribution(400, kind, ids[kind], FacetMatchState.UNKNOWN)
        for kind in reversed(unknown_kinds)
    )

    result = build_tradeoff(
        _evidence(*contributions),
        _labels(*contributions),
        normal_completion_seconds=None,
    )

    assert result == UnknownPreferenceMetadataTradeoff(
        facet_kinds=unknown_kinds,
        text=expected_text,
    )
    assert result.type is TradeoffType.UNKNOWN_PREFERENCE_METADATA


def test_unknown_metadata_has_priority_over_nonmatch_and_completion() -> None:
    contributions = (
        _contribution(
            400,
            FacetKind.GENRE,
            9,
            FacetMatchState.MATCHED,
        ),
        _contribution(
            400,
            FacetKind.THEME,
            18,
            FacetMatchState.UNKNOWN,
        ),
        _contribution(
            400,
            FacetKind.KEYWORD,
            4_928,
            FacetMatchState.NOT_MATCHED,
        ),
    )

    result = build_tradeoff(
        _evidence(*contributions),
        _labels(*contributions),
        normal_completion_seconds=None,
    )

    assert isinstance(result, UnknownPreferenceMetadataTradeoff)
    assert result.facet_kinds == (FacetKind.THEME,)


def test_nonmatch_groups_references_before_selecting_a_tradeoff() -> None:
    contributions = (
        _contribution(
            400,
            FacetKind.THEME,
            18,
            FacetMatchState.MATCHED,
        ),
        _contribution(
            400,
            FacetKind.GENRE,
            9,
            FacetMatchState.NOT_MATCHED,
        ),
        _contribution(
            202,
            FacetKind.KEYWORD,
            4_928,
            FacetMatchState.NOT_MATCHED,
        ),
        _contribution(
            101,
            FacetKind.KEYWORD,
            4_928,
            FacetMatchState.NOT_MATCHED,
        ),
    )

    result = build_tradeoff(
        _evidence(*contributions),
        _labels(*contributions),
        normal_completion_seconds=None,
    )

    assert result == UnmatchedPreferenceTradeoff(
        reason=UnmatchedPreferenceReason(
            facet_kind=FacetKind.KEYWORD,
            facet_igdb_id=4_928,
            name="Environmental puzzles",
            reference_steam_app_ids=(202, 101),
        ),
        text="Does not match your Environmental puzzles preference.",
    )
    assert result.type is TradeoffType.UNMATCHED_PREFERENCE


def test_nonmatch_ties_use_budget_then_canonical_kind_then_id() -> None:
    contributions = (
        _contribution(
            400,
            FacetKind.KEYWORD,
            4_928,
            FacetMatchState.MATCHED,
        ),
        _contribution(
            400,
            FacetKind.GAME_MODE,
            1,
            FacetMatchState.NOT_MATCHED,
        ),
        _contribution(
            400,
            FacetKind.THEME,
            18,
            FacetMatchState.NOT_MATCHED,
        ),
        _contribution(
            400,
            FacetKind.GENRE,
            10,
            FacetMatchState.NOT_MATCHED,
        ),
        _contribution(
            400,
            FacetKind.GENRE,
            9,
            FacetMatchState.NOT_MATCHED,
        ),
    )

    result = build_tradeoff(
        _evidence(*contributions),
        _labels(*contributions),
        normal_completion_seconds=3_600,
    )

    assert isinstance(result, UnmatchedPreferenceTradeoff)
    assert result.reason.facet_kind is FacetKind.GENRE
    assert result.reason.facet_igdb_id == 9
    assert result.reason.name == "Puzzle"


def test_equal_budget_nonmatch_tie_uses_canonical_kind_order() -> None:
    contributions = (
        _contribution(
            400,
            FacetKind.KEYWORD,
            4_928,
            FacetMatchState.MATCHED,
        ),
        _contribution(
            400,
            FacetKind.GAME_MODE,
            1,
            FacetMatchState.NOT_MATCHED,
        ),
        _contribution(
            400,
            FacetKind.THEME,
            18,
            FacetMatchState.NOT_MATCHED,
        ),
    )

    result = build_tradeoff(
        _evidence(*contributions),
        _labels(*contributions),
        normal_completion_seconds=3_600,
    )

    assert isinstance(result, UnmatchedPreferenceTradeoff)
    assert result.reason.facet_kind is FacetKind.THEME


def test_zero_matches_do_not_produce_a_redundant_nonmatch_tradeoff() -> None:
    contribution = _contribution(
        400,
        FacetKind.GENRE,
        9,
        FacetMatchState.NOT_MATCHED,
    )

    result = build_tradeoff(
        _evidence(contribution),
        _labels(contribution),
        normal_completion_seconds=3_600,
    )

    assert result is None


def test_unknown_completion_is_the_last_tradeoff_fallback() -> None:
    contribution = _contribution(
        400,
        FacetKind.GENRE,
        9,
        FacetMatchState.MATCHED,
    )

    result = build_tradeoff(
        _evidence(contribution),
        _labels(contribution),
        normal_completion_seconds=None,
    )

    assert result == UnknownCompletionTimeTradeoff(
        text="Completion-time estimate is unavailable."
    )
    assert result.type is TradeoffType.UNKNOWN_COMPLETION_TIME


def test_known_completion_and_no_higher_priority_issue_returns_none() -> None:
    contribution = _contribution(
        400,
        FacetKind.GENRE,
        9,
        FacetMatchState.MATCHED,
    )

    result = build_tradeoff(
        _evidence(contribution),
        _labels(contribution),
        normal_completion_seconds=28_800,
    )

    assert result is None
