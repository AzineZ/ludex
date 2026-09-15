from typing import Any

from app.gemini.reranking.contracts import (
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
            "summary": {"type": "string"},
            "reasoning": {"type": "string"},
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
