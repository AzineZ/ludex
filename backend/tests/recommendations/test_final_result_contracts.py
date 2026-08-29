from dataclasses import FrozenInstanceError

import pytest

from app.recommendations.factual_scoring import (
    FacetKind,
    FactualScoreEvidence,
)
from app.recommendations.final_results import (
    CandidatePresentationFacts,
    FacetLabel,
    FinalRecommendationItem,
    FinalRecommendationResult,
    MatchSummary,
    RecommendationOutcome,
)


def _item(rank: int, steam_app_id: int) -> FinalRecommendationItem:
    return FinalRecommendationItem(
        rank=rank,
        presentation=CandidatePresentationFacts(
            steam_app_id=steam_app_id,
            title=f"Game {steam_app_id}",
            cover_url=None,
            profile_playtime_minutes=0,
            normal_completion_seconds=None,
        ),
        factual_evidence=FactualScoreEvidence(
            version="factual-overlap-v1",
            score_basis_points=0,
            active_budget=100,
            contributions=(),
        ),
        facet_labels=(),
        match_summary=MatchSummary(
            reasons=(),
            additional_match_count=0,
            text="No selected factual preferences matched.",
        ),
        tradeoff=None,
    )


def test_result_outcomes_use_the_frozen_wire_values() -> None:
    assert RecommendationOutcome.COMPLETE == "complete"
    assert RecommendationOutcome.SPARSE == "sparse"
    assert RecommendationOutcome.EMPTY == "empty"


def test_presentation_facts_preserve_known_and_unknown_cached_values() -> None:
    known = CandidatePresentationFacts(
        steam_app_id=620,
        title="Portal 2",
        cover_url="https://images.example/portal-2.jpg",
        profile_playtime_minutes=42,
        normal_completion_seconds=28_800,
    )
    unknown = CandidatePresentationFacts(
        steam_app_id=999_001,
        title="Mystery Game",
        cover_url=None,
        profile_playtime_minutes=0,
        normal_completion_seconds=None,
    )

    assert known.cover_url == "https://images.example/portal-2.jpg"
    assert known.profile_playtime_minutes == 42
    assert known.normal_completion_seconds == 28_800
    assert unknown.cover_url is None
    assert unknown.profile_playtime_minutes == 0
    assert unknown.normal_completion_seconds is None


def test_facet_label_keeps_authoritative_identity_separate_from_scoring() -> None:
    label = FacetLabel(
        facet_kind=FacetKind.GENRE,
        facet_igdb_id=9,
        name="Puzzle",
    )

    assert label == FacetLabel(FacetKind.GENRE, 9, "Puzzle")
    assert not hasattr(label, "points")
    assert not hasattr(label, "match_state")


@pytest.mark.parametrize(
    ("count", "eligible_count", "expected_outcome"),
    [
        (0, 0, RecommendationOutcome.EMPTY),
        (1, 1, RecommendationOutcome.SPARSE),
        (5, 5, RecommendationOutcome.SPARSE),
        (6, 92, RecommendationOutcome.COMPLETE),
    ],
)
def test_result_derives_count_and_outcome_from_ordered_items(
    count: int,
    eligible_count: int,
    expected_outcome: RecommendationOutcome,
) -> None:
    items = tuple(_item(rank, 1_000 + rank) for rank in range(1, count + 1))

    result = FinalRecommendationResult(
        eligible_count=eligible_count,
        items=items,
    )

    assert result.returned_count == count
    assert result.outcome is expected_outcome
    assert result.items == items


def test_result_rejects_more_than_six_items() -> None:
    items = tuple(_item(rank, 1_000 + rank) for rank in range(1, 8))

    with pytest.raises(ValueError, match="at most 6"):
        FinalRecommendationResult(eligible_count=7, items=items)


def test_result_rejects_nonordinal_item_ranks() -> None:
    with pytest.raises(ValueError, match="ordinal ranks"):
        FinalRecommendationResult(
            eligible_count=2,
            items=(_item(1, 101), _item(3, 102)),
        )


def test_result_rejects_an_eligible_count_below_returned_count() -> None:
    with pytest.raises(ValueError, match="eligible_count"):
        FinalRecommendationResult(
            eligible_count=1,
            items=(_item(1, 101), _item(2, 102)),
        )


def test_final_result_contracts_are_immutable() -> None:
    facts = CandidatePresentationFacts(
        steam_app_id=620,
        title="Portal 2",
        cover_url=None,
        profile_playtime_minutes=42,
        normal_completion_seconds=None,
    )
    label = FacetLabel(FacetKind.GENRE, 9, "Puzzle")
    result = FinalRecommendationResult(eligible_count=0, items=())

    with pytest.raises(FrozenInstanceError):
        facts.title = "Changed"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        label.name = "Changed"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        result.eligible_count = 1  # type: ignore[misc]
