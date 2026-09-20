import pytest
from pydantic import ValidationError

from app.gemini.reranking.contracts import (
    MAX_RERANK_CANDIDATES,
    MAX_RERANK_OUTPUT_SUMMARY_CHARACTERS,
    MAX_RERANK_REASONING_CHARACTERS,
    RerankCandidate,
    RerankFilters,
    RerankRequest,
    RerankResponse,
    RerankStatus,
)
from app.recommendations.contracts import PlayStatus


def candidate(steam_app_id: int) -> RerankCandidate:
    return RerankCandidate(
        steam_app_id=steam_app_id,
        title=f"Game {steam_app_id}",
        summary="A compact factual summary.",
        genres=("Adventure",),
        themes=("Fantasy",),
        keywords=("Exploration",),
        game_modes=("Single player",),
        profile_playtime_minutes=0,
        normal_completion_minutes=600,
    )


def request(count: int = 6) -> RerankRequest:
    return RerankRequest(
        prompt="Something relaxing after work",
        selected_genre_id=31,
        selected_genre_name="Adventure",
        filters=RerankFilters(play_status=PlayStatus.EITHER),
        candidates=tuple(candidate(index) for index in range(1, count + 1)),
    )


def test_request_accepts_at_most_four_hundred_unique_candidates() -> None:
    assert MAX_RERANK_CANDIDATES == 400
    assert len(request(MAX_RERANK_CANDIDATES).candidates) == 400

    with pytest.raises(ValidationError):
        request(MAX_RERANK_CANDIDATES + 1)

    duplicated = request()
    with pytest.raises(ValidationError):
        RerankRequest.model_validate(
            {
                **duplicated.model_dump(),
                "candidates": (
                    duplicated.candidates[0].model_dump(),
                    duplicated.candidates[0].model_dump(),
                ),
            }
        )


def test_response_requires_consistent_ranked_or_no_match_shape() -> None:
    ranked = RerankResponse(
        status=RerankStatus.RANKED,
        recommendations=(
            {
                "steam_app_id": 1,
                "summary": "A gentle exploration game.",
                "reasoning": "Its gentle pace fits your request for relaxing play.",
            },
        ),
        no_match_reason=None,
    )
    assert ranked.recommendations[0].steam_app_id == 1
    assert ranked.recommendations[0].summary == "A gentle exploration game."
    assert "relaxing" in ranked.recommendations[0].reasoning

    no_match = RerankResponse(
        status=RerankStatus.NO_MATCH,
        recommendations=(),
        no_match_reason="None of these games plausibly fit that request.",
    )
    assert no_match.status is RerankStatus.NO_MATCH

    with pytest.raises(ValidationError):
        RerankResponse(
            status=RerankStatus.NO_MATCH,
            recommendations=(
                {
                    "steam_app_id": 1,
                    "summary": "A game summary.",
                    "reasoning": "A contradictory match explanation.",
                },
            ),
            no_match_reason="None fit.",
        )


def test_response_requires_distinct_bounded_summary_and_reasoning() -> None:
    base = {
        "status": "ranked",
        "recommendations": [
            {
                "steam_app_id": 1,
                "summary": "  A gentle\n exploration game.  ",
                "reasoning": "  Fits your request\tfor relaxing play.  ",
            }
        ],
        "no_match_reason": None,
    }

    response = RerankResponse.model_validate(base)
    assert response.recommendations[0].summary == "A gentle exploration game."
    assert response.recommendations[0].reasoning == (
        "Fits your request for relaxing play."
    )

    assert MAX_RERANK_OUTPUT_SUMMARY_CHARACTERS == 400
    assert MAX_RERANK_REASONING_CHARACTERS == 240

    for field in ("summary", "reasoning"):
        invalid = {
            **base,
            "recommendations": [
                {
                    **base["recommendations"][0],
                    field: " ",
                }
            ],
        }
        with pytest.raises(ValidationError):
            RerankResponse.model_validate(invalid)

    summary_at_limit = {
        **base,
        "recommendations": [
            {
                **base["recommendations"][0],
                "summary": "x" * MAX_RERANK_OUTPUT_SUMMARY_CHARACTERS,
            }
        ],
    }
    RerankResponse.model_validate(summary_at_limit)

    for field, maximum in (
        ("summary", MAX_RERANK_OUTPUT_SUMMARY_CHARACTERS),
        ("reasoning", MAX_RERANK_REASONING_CHARACTERS),
    ):
        invalid = {
            **base,
            "recommendations": [
                {
                    **base["recommendations"][0],
                    field: "x" * (maximum + 1),
                }
            ],
        }
        with pytest.raises(ValidationError):
            RerankResponse.model_validate(invalid)


def test_candidate_text_is_bounded_and_normalized() -> None:
    normalized = candidate(1).model_copy(
        update={"summary": "  One\n  factual\t summary.  "}
    )
    reparsed = RerankCandidate.model_validate(normalized.model_dump())
    assert reparsed.summary == "One factual summary."

    with pytest.raises(ValidationError):
        RerankCandidate.model_validate(
            {**candidate(1).model_dump(), "summary": "x" * 1201}
        )


def test_request_requires_every_candidate_to_match_selected_genre() -> None:
    mismatched = candidate(1).model_copy(update={"genres": ("Puzzle",)})

    with pytest.raises(ValidationError):
        RerankRequest(
            prompt="Something relaxing",
            selected_genre_id=31,
            selected_genre_name="Adventure",
            filters=RerankFilters(),
            candidates=(mismatched,),
        )
