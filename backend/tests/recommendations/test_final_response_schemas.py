import pytest
from pydantic import ValidationError

from app.recommendations.api_schemas import (
    FinalRecommendationResponse,
    to_final_recommendation_response,
)
from app.recommendations.factual_scoring import (
    FacetKind,
    FacetMatchState,
    FactualContribution,
    FactualScoreEvidence,
)
from app.recommendations.final_results import (
    CandidatePresentationFacts,
    FacetLabel,
    FinalRecommendationItem,
    FinalRecommendationResult,
    MatchReason,
    MatchSummary,
    TradeoffType,
    UnknownCompletionTimeTradeoff,
    UnknownPreferenceMetadataTradeoff,
    UnmatchedPreferenceReason,
    UnmatchedPreferenceTradeoff,
)


def _evidence() -> FactualScoreEvidence:
    return FactualScoreEvidence(
        version="factual-overlap-v1",
        score_basis_points=3_000,
        active_budget=50,
        contributions=(
            FactualContribution(
                reference_steam_app_id=400,
                facet_kind=FacetKind.GENRE,
                facet_igdb_id=9,
                match_state=FacetMatchState.MATCHED,
                points_numerator=3_000,
                points_denominator=1,
            ),
            FactualContribution(
                reference_steam_app_id=400,
                facet_kind=FacetKind.KEYWORD,
                facet_igdb_id=4_928,
                match_state=FacetMatchState.NOT_MATCHED,
                points_numerator=0,
                points_denominator=1,
            ),
        ),
    )


def _item(
    tradeoff: (
        UnknownCompletionTimeTradeoff
        | UnknownPreferenceMetadataTradeoff
        | UnmatchedPreferenceTradeoff
        | None
    ),
) -> FinalRecommendationItem:
    return FinalRecommendationItem(
        rank=1,
        presentation=CandidatePresentationFacts(
            steam_app_id=620,
            title="Portal 2",
            cover_url="https://images.example/portal-2.jpg",
            profile_playtime_minutes=42,
            normal_completion_seconds=None,
        ),
        factual_evidence=_evidence(),
        facet_labels=(
            FacetLabel(FacetKind.GENRE, 9, "Puzzle"),
            FacetLabel(
                FacetKind.KEYWORD,
                4_928,
                "Environmental puzzles",
            ),
        ),
        match_summary=MatchSummary(
            reasons=(
                MatchReason(
                    facet_kind=FacetKind.GENRE,
                    facet_igdb_id=9,
                    name="Puzzle",
                    reference_steam_app_ids=(400,),
                    points_numerator=3_000,
                    points_denominator=1,
                ),
            ),
            additional_match_count=0,
            text="Matches your Puzzle preference.",
        ),
        tradeoff=tradeoff,
    )


def test_empty_domain_result_serializes_to_exact_success_envelope() -> None:
    response = to_final_recommendation_response(
        FinalRecommendationResult(eligible_count=0, items=())
    )

    assert response.model_dump(mode="json") == {
        "outcome": "empty",
        "eligible_count": 0,
        "returned_count": 0,
        "items": [],
    }


def test_item_serializes_flat_presentation_and_unchanged_evidence() -> None:
    tradeoff = UnmatchedPreferenceTradeoff(
        reason=UnmatchedPreferenceReason(
            facet_kind=FacetKind.KEYWORD,
            facet_igdb_id=4_928,
            name="Environmental puzzles",
            reference_steam_app_ids=(400,),
        ),
        text="Does not match your Environmental puzzles preference.",
    )
    response = to_final_recommendation_response(
        FinalRecommendationResult(
            eligible_count=1,
            items=(_item(tradeoff),),
        )
    )

    assert response.model_dump(mode="json") == {
        "outcome": "sparse",
        "eligible_count": 1,
        "returned_count": 1,
        "items": [
            {
                "rank": 1,
                "steam_app_id": 620,
                "title": "Portal 2",
                "cover_url": "https://images.example/portal-2.jpg",
                "profile_playtime_minutes": 42,
                "normal_completion_seconds": None,
                "factual_evidence": {
                    "version": "factual-overlap-v1",
                    "score_basis_points": 3_000,
                    "active_budget": 50,
                    "contributions": [
                        {
                            "reference_steam_app_id": 400,
                            "facet_kind": "genre",
                            "facet_igdb_id": 9,
                            "match_state": "matched",
                            "points_numerator": 3_000,
                            "points_denominator": 1,
                        },
                        {
                            "reference_steam_app_id": 400,
                            "facet_kind": "keyword",
                            "facet_igdb_id": 4_928,
                            "match_state": "not_matched",
                            "points_numerator": 0,
                            "points_denominator": 1,
                        },
                    ],
                },
                "facet_labels": [
                    {
                        "facet_kind": "genre",
                        "facet_igdb_id": 9,
                        "name": "Puzzle",
                    },
                    {
                        "facet_kind": "keyword",
                        "facet_igdb_id": 4_928,
                        "name": "Environmental puzzles",
                    },
                ],
                "match_summary": {
                    "reasons": [
                        {
                            "facet_kind": "genre",
                            "facet_igdb_id": 9,
                            "name": "Puzzle",
                            "reference_steam_app_ids": [400],
                            "points_numerator": 3_000,
                            "points_denominator": 1,
                        }
                    ],
                    "additional_match_count": 0,
                    "text": "Matches your Puzzle preference.",
                },
                "tradeoff": {
                    "type": "unmatched_preference",
                    "reason": {
                        "facet_kind": "keyword",
                        "facet_igdb_id": 4_928,
                        "name": "Environmental puzzles",
                        "reference_steam_app_ids": [400],
                    },
                    "text": (
                        "Does not match your Environmental puzzles "
                        "preference."
                    ),
                },
            }
        ],
    }


@pytest.mark.parametrize(
    ("tradeoff", "expected"),
    [
        (
            UnknownPreferenceMetadataTradeoff(
                facet_kinds=(FacetKind.GENRE, FacetKind.THEME),
                text="Genre and theme metadata are unavailable.",
            ),
            {
                "type": "unknown_preference_metadata",
                "facet_kinds": ["genre", "theme"],
                "text": "Genre and theme metadata are unavailable.",
            },
        ),
        (
            UnknownCompletionTimeTradeoff(
                text="Completion-time estimate is unavailable."
            ),
            {
                "type": "unknown_completion_time",
                "text": "Completion-time estimate is unavailable.",
            },
        ),
        (None, None),
    ],
)
def test_other_tradeoff_shapes_serialize_exactly(
    tradeoff: object,
    expected: object,
) -> None:
    response = to_final_recommendation_response(
        FinalRecommendationResult(
            eligible_count=1,
            items=(_item(tradeoff),),  # type: ignore[arg-type]
        )
    )

    assert response.model_dump(mode="json")["items"][0]["tradeoff"] == expected


def test_response_contract_is_frozen_and_forbids_extra_fields() -> None:
    response = to_final_recommendation_response(
        FinalRecommendationResult(eligible_count=0, items=())
    )

    with pytest.raises(ValidationError):
        FinalRecommendationResponse.model_validate(
            {
                **response.model_dump(mode="json"),
                "has_more": False,
            }
        )
    with pytest.raises(ValidationError):
        response.eligible_count = 1
