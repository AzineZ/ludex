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
    TradeoffType,
    assemble_final_recommendations,
)
from app.recommendations.retrieval import FactualCandidatePool


_LABELS = (
    FacetLabel(FacetKind.GENRE, 9, "Puzzle"),
    FacetLabel(FacetKind.THEME, 18, "Science fiction"),
    FacetLabel(FacetKind.KEYWORD, 4_928, "Environmental puzzles"),
    FacetLabel(FacetKind.GAME_MODE, 1, "Single player"),
)

_FACETS = (
    (FacetKind.GENRE, 9, 3_000),
    (FacetKind.THEME, 18, 2_500),
    (FacetKind.KEYWORD, 4_928, 2_000),
    (FacetKind.GAME_MODE, 1, 2_500),
)


def _candidate(
    steam_app_id: int,
    states: tuple[FacetMatchState, ...],
) -> FactualScoredCandidate:
    contributions = tuple(
        FactualContribution(
            reference_steam_app_id=400,
            facet_kind=kind,
            facet_igdb_id=igdb_id,
            match_state=state,
            points_numerator=(points if state is FacetMatchState.MATCHED else 0),
            points_denominator=1,
        )
        for (kind, igdb_id, points), state in zip(
            _FACETS,
            states,
            strict=True,
        )
    )
    return FactualScoredCandidate(
        steam_app_id=steam_app_id,
        evidence=FactualScoreEvidence(
            version="factual-overlap-v1",
            score_basis_points=sum(
                contribution.points_numerator
                for contribution in contributions
            ),
            active_budget=100,
            contributions=contributions,
        ),
    )


def _presentation(
    steam_app_id: int,
    *,
    title: str | None = None,
    cover_url: str | None = None,
    playtime_minutes: int = 0,
    completion_seconds: int | None = 28_800,
) -> CandidatePresentationFacts:
    return CandidatePresentationFacts(
        steam_app_id=steam_app_id,
        title=title or f"Game {steam_app_id}",
        cover_url=cover_url,
        profile_playtime_minutes=playtime_minutes,
        normal_completion_seconds=completion_seconds,
    )


def _complete_inputs() -> tuple[
    tuple[FactualScoredCandidate, ...],
    tuple[CandidatePresentationFacts, ...],
]:
    matched = FacetMatchState.MATCHED
    not_matched = FacetMatchState.NOT_MATCHED
    candidates = (
        _candidate(620, (matched, matched, not_matched, matched)),
        _candidate(317_400, (matched, matched, not_matched, matched)),
        _candidate(920_210, (matched, matched, not_matched, matched)),
        _candidate(220, (not_matched, matched, matched, matched)),
        _candidate(736_260, (matched, not_matched, not_matched, matched)),
        _candidate(2_280, (not_matched, matched, not_matched, matched)),
    )
    presentations = (
        _presentation(
            620,
            title="Portal 2",
            cover_url="https://images.example/portal-2.jpg",
            playtime_minutes=42,
        ),
        _presentation(317_400, playtime_minutes=0),
        _presentation(
            920_210,
            cover_url="https://images.example/920210.jpg",
            playtime_minutes=120,
        ),
        _presentation(220, playtime_minutes=600),
        _presentation(
            736_260,
            cover_url="https://images.example/736260.jpg",
        ),
        _presentation(2_280, playtime_minutes=15),
    )
    return candidates, presentations


def test_approved_complete_and_tied_example() -> None:
    candidates, presentations = _complete_inputs()

    result = assemble_final_recommendations(
        FactualCandidatePool(candidates=candidates, eligible_count=92),
        presentations,
        _LABELS,
    )

    assert result.outcome is RecommendationOutcome.COMPLETE
    assert result.eligible_count == 92
    assert result.returned_count == 6
    assert tuple(item.rank for item in result.items) == (1, 2, 3, 4, 5, 6)
    assert tuple(
        item.presentation.steam_app_id for item in result.items
    ) == (620, 317_400, 920_210, 220, 736_260, 2_280)
    assert tuple(
        item.factual_evidence.score_basis_points for item in result.items
    ) == (8_000, 8_000, 8_000, 7_000, 5_500, 5_000)
    assert tuple(item.match_summary.text for item in result.items) == (
        "Matches your Puzzle, Science fiction, and Single player preferences.",
        "Matches your Puzzle, Science fiction, and Single player preferences.",
        "Matches your Puzzle, Science fiction, and Single player preferences.",
        (
            "Matches your Science fiction, Single player, and Environmental "
            "puzzles preferences."
        ),
        "Matches your Puzzle and Single player preferences.",
        "Matches your Science fiction and Single player preferences.",
    )
    assert tuple(
        item.tradeoff.text if item.tradeoff else None for item in result.items
    ) == (
        "Does not match your Environmental puzzles preference.",
        "Does not match your Environmental puzzles preference.",
        "Does not match your Environmental puzzles preference.",
        "Does not match your Puzzle preference.",
        "Does not match your Science fiction preference.",
        "Does not match your Puzzle preference.",
    )
    assert all(item.facet_labels == _LABELS for item in result.items)
    assert all(
        item.factual_evidence is candidate.evidence
        for item, candidate in zip(result.items, candidates, strict=True)
    )


def test_approved_sparse_example_keeps_first_five_items_unchanged() -> None:
    candidates, presentations = _complete_inputs()
    complete = assemble_final_recommendations(
        FactualCandidatePool(candidates=candidates, eligible_count=92),
        presentations,
        _LABELS,
    )

    sparse = assemble_final_recommendations(
        FactualCandidatePool(candidates=candidates[:5], eligible_count=5),
        presentations[:5],
        _LABELS,
    )

    assert sparse.outcome is RecommendationOutcome.SPARSE
    assert sparse.eligible_count == 5
    assert sparse.returned_count == 5
    assert sparse.items == complete.items[:5]


def test_approved_empty_example_has_no_items() -> None:
    result = assemble_final_recommendations(
        FactualCandidatePool(candidates=(), eligible_count=0),
        (),
        (),
    )

    assert result.outcome is RecommendationOutcome.EMPTY
    assert result.eligible_count == 0
    assert result.returned_count == 0
    assert result.items == ()


def test_approved_missing_metadata_example() -> None:
    matched = FacetMatchState.MATCHED
    unknown = FacetMatchState.UNKNOWN
    candidates = (
        _candidate(620, (matched, matched, matched, matched)),
        _candidate(999_001, (unknown, unknown, unknown, unknown)),
    )

    result = assemble_final_recommendations(
        FactualCandidatePool(candidates=candidates, eligible_count=2),
        (
            _presentation(
                620,
                title="Portal 2",
                cover_url="https://images.example/portal-2.jpg",
                playtime_minutes=42,
                completion_seconds=None,
            ),
            _presentation(
                999_001,
                title="Mystery Game",
                cover_url=None,
                playtime_minutes=0,
                completion_seconds=None,
            ),
        ),
        _LABELS,
    )

    first, second = result.items
    assert result.outcome is RecommendationOutcome.SPARSE
    assert result.returned_count == 2
    assert first.factual_evidence.score_basis_points == 10_000
    assert first.match_summary.additional_match_count == 1
    assert first.match_summary.text == (
        "Matches your Puzzle, Science fiction, and Single player preferences, "
        "plus 1 more."
    )
    assert first.tradeoff is not None
    assert first.tradeoff.type is TradeoffType.UNKNOWN_COMPLETION_TIME
    assert first.tradeoff.text == "Completion-time estimate is unavailable."

    assert second.presentation.cover_url is None
    assert second.presentation.normal_completion_seconds is None
    assert second.factual_evidence.score_basis_points == 0
    assert all(
        contribution.match_state is FacetMatchState.UNKNOWN
        for contribution in second.factual_evidence.contributions
    )
    assert second.match_summary.text == (
        "No selected factual preferences matched."
    )
    assert second.tradeoff is not None
    assert second.tradeoff.type is TradeoffType.UNKNOWN_PREFERENCE_METADATA
    assert second.tradeoff.text == (
        "Genre, theme, keyword, and game-mode metadata are unavailable."
    )
