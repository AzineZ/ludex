from unittest.mock import Mock

import pytest

from app.gemini.client import GeminiStructuredContent
from app.gemini.reranking.contracts import (
    RerankCandidate,
    RerankFilters,
    RerankRequest,
)
from app.gemini.reranking.reranker import (
    MAX_RERANK_OUTPUT_TOKENS,
    MAX_RERANK_REQUEST_BYTES,
    RerankRequestTooLarge,
    RerankResponseError,
    build_rerank_user_prompt,
    rerank_with_metadata,
)
from app.gemini.reranking.schema import build_rerank_response_schema


def request() -> RerankRequest:
    return RerankRequest(
        prompt="Something relaxing",
        selected_genre_id=31,
        selected_genre_name="Adventure",
        filters=RerankFilters(),
        candidates=tuple(
            RerankCandidate(
                steam_app_id=index,
                title=f"Game {index}",
                summary="A calm adventure about exploration.",
                genres=("Adventure",),
                themes=(),
                keywords=("Exploration",),
                game_modes=("Single player",),
                profile_playtime_minutes=0,
                normal_completion_minutes=None,
            )
            for index in range(1, 7)
        ),
    )


def test_reranker_sends_one_bounded_untrusted_snapshot() -> None:
    client = Mock()
    client.generate_structured_content_with_metadata.return_value = (
        GeminiStructuredContent(
            content={
                "status": "ranked",
                "recommendations": [
                    {
                        "steam_app_id": 2,
                        "summary": "A calm adventure.",
                        "reasoning": "Its calm pace fits your request for relaxing play.",
                    },
                    {
                        "steam_app_id": 1,
                        "summary": "A peaceful exploration game.",
                        "reasoning": "Its peaceful exploration also fits relaxing play.",
                    },
                ],
                "no_match_reason": None,
            },
            input_tokens=500,
            output_tokens=50,
            total_tokens=550,
        )
    )

    response, metadata = rerank_with_metadata(
        client,
        model_id="evaluation-model",
        request=request(),
    )

    assert [item.steam_app_id for item in response.recommendations] == [2, 1]
    assert metadata.total_tokens == 550
    call = client.generate_structured_content_with_metadata.call_args.kwargs
    assert call["max_output_tokens"] == MAX_RERANK_OUTPUT_TOKENS
    assert len(call["user_prompt"].encode("utf-8")) <= MAX_RERANK_REQUEST_BYTES
    assert '"visitor_request":"Something relaxing"' in call["user_prompt"]
    assert "untrusted" in call["system_instruction"].casefold()
    assert "summary" in call["system_instruction"].casefold()
    assert "reasoning must repeat" in call["system_instruction"].casefold()


@pytest.mark.parametrize(
    "recommendations",
    [
        [
            {
                "steam_app_id": 999,
                "summary": "Not allowed.",
                "reasoning": "Not allowed by the candidate boundary.",
            }
        ],
        [
            {
                "steam_app_id": 1,
                "summary": "First.",
                "reasoning": "Fits the visitor request.",
            },
            {
                "steam_app_id": 1,
                "summary": "Duplicate.",
                "reasoning": "Also fits the visitor request.",
            },
        ],
    ],
)
def test_reranker_rejects_foreign_or_duplicate_ids(recommendations) -> None:
    client = Mock()
    client.generate_structured_content_with_metadata.return_value = (
        GeminiStructuredContent(
            content={
                "status": "ranked",
                "recommendations": recommendations,
                "no_match_reason": None,
            },
            input_tokens=None,
            output_tokens=None,
            total_tokens=None,
        )
    )

    with pytest.raises(RerankResponseError):
        rerank_with_metadata(
            client,
            model_id="evaluation-model",
            request=request(),
        )


def test_thirty_candidate_fixture_stays_within_request_budget() -> None:
    base = request()
    large = base.model_copy(
        update={
            "candidates": tuple(
                base.candidates[index % len(base.candidates)].model_copy(
                    update={
                        "steam_app_id": index + 1,
                        "summary": "x" * 1200,
                    }
                )
                for index in range(30)
            )
        }
    )
    prompt = build_rerank_user_prompt(
        RerankRequest.model_validate(large.model_dump())
    )
    assert len(prompt.encode("utf-8")) <= MAX_RERANK_REQUEST_BYTES


def test_explicit_evaluation_limit_does_not_weaken_default_payload_guard() -> None:
    base = request()
    large = RerankRequest.model_validate(
        base.model_copy(
            update={
                "candidates": tuple(
                    base.candidates[index % len(base.candidates)].model_copy(
                        update={
                            "steam_app_id": index + 1,
                            "summary": "x" * 1_200,
                        }
                    )
                    for index in range(100)
                )
            }
        ).model_dump()
    )

    with pytest.raises(RerankRequestTooLarge):
        build_rerank_user_prompt(large)

    prompt = build_rerank_user_prompt(large, max_request_bytes=200_000)
    assert MAX_RERANK_REQUEST_BYTES < len(prompt.encode("utf-8")) <= 200_000


def test_response_schema_uses_supported_shape_and_local_id_validation() -> None:
    schema = build_rerank_response_schema(request())
    recommendation = schema["properties"]["recommendations"]["items"]

    assert recommendation["properties"]["steam_app_id"] == {
        "type": "integer"
    }
    assert recommendation["required"] == [
        "steam_app_id",
        "summary",
        "reasoning",
    ]
    assert "$defs" not in schema
    assert "$ref" not in str(schema)
    assert "minLength" not in str(schema)
    assert "maxLength" not in str(schema)
    assert "default" not in str(schema)
