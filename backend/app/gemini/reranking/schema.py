from typing import Any

from app.gemini.reranking.contracts import (
    MAX_RERANK_OUTPUT_SUMMARY_CHARACTERS,
    MAX_RERANK_REASONING_CHARACTERS,
    MAX_RERANK_RESULTS,
    RerankRequest,
    RerankStatus,
)


def build_rerank_response_schema(_request: RerankRequest) -> dict[str, Any]:
    """Build a flat provider schema for one reranking response.

    Local Pydantic validation remains the authority for string lengths and the
    mutually exclusive ranked/no-match shape, including exact candidate-ID
    membership. Gemini currently rejects numeric enums in this response shape,
    so the provider schema constrains IDs to integers and the backend applies
    the immutable snapshot allowlist after decoding.
    """
    recommendation = {
        "type": "object",
        "properties": {
            "steam_app_id": {
                "type": "integer",
            },
            "summary": {
                "type": "string",
                "description": (
                    "A newly written one- or two-sentence game overview that "
                    "ends as a complete sentence, never with an ellipsis, and "
                    f"uses at most {MAX_RERANK_OUTPUT_SUMMARY_CHARACTERS} "
                    "characters including spaces and punctuation. Do not copy "
                    "a compacted candidate summary verbatim."
                ),
            },
            "reasoning": {
                "type": "string",
                "description": (
                    "A complete-sentence explanation connecting the visitor's "
                    "exact wording to relevant game facts, never ending with "
                    "an ellipsis, and using at most "
                    f"{MAX_RERANK_REASONING_CHARACTERS} characters including "
                    "spaces and punctuation."
                ),
            },
        },
        "required": ["steam_app_id", "summary", "reasoning"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "enum": [status.value for status in RerankStatus],
            },
            "recommendations": {
                "type": "array",
                "items": recommendation,
                "maxItems": MAX_RERANK_RESULTS,
            },
            "no_match_reason": {
                "anyOf": [{"type": "string"}, {"type": "null"}],
            },
        },
        "required": ["status", "recommendations", "no_match_reason"],
        "additionalProperties": False,
    }
