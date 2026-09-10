from typing import Any

from app.gemini.prompt.contracts import (
    MAX_PROMPT_CONCEPTS,
    MAX_UNMATCHED_PHRASES,
    PROMPT_INTERPRETATION_VERSION,
    PromptVocabulary,
)
from app.recommendations.contracts import (
    PlayStatus,
)


MIN_COMPLETION_MINUTES = 30
MAX_COMPLETION_MINUTES = 60_000


def build_prompt_interpretation_response_schema(
    vocabulary: PromptVocabulary,
) -> dict[str, Any]:
    """Build a closed provider schema scoped to one exact vocabulary."""
    concept_ids = [entry.concept_id for entry in vocabulary.entries]
    if not concept_ids:
        raise ValueError("Prompt interpretation requires a vocabulary.")

    preference_schema = {
        "type": "object",
        "properties": {
            "concept_id": {
                "type": "string",
                "enum": concept_ids,
            },
            "direction": {
                "type": "string",
                "enum": ["desired", "avoided"],
            },
            "importance": {
                "type": "integer",
                "minimum": 1,
                "maximum": 3,
            },
            "target": {
                "anyOf": [
                    {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 5,
                    },
                    {"type": "null"},
                ]
            },
        },
        "required": ["concept_id", "direction", "importance", "target"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "version": {
                "type": "string",
                "enum": [PROMPT_INTERPRETATION_VERSION],
            },
            "preferences": {
                "type": "array",
                "items": preference_schema,
                "maxItems": MAX_PROMPT_CONCEPTS,
            },
            "constraints": {
                "type": "object",
                "properties": {
                    "maximum_completion_minutes": {
                        "anyOf": [
                            {
                                "type": "integer",
                                "minimum": MIN_COMPLETION_MINUTES,
                                "maximum": MAX_COMPLETION_MINUTES,
                            },
                            {"type": "null"},
                        ]
                    },
                    "play_status": {
                        "type": "string",
                        "enum": [status.value for status in PlayStatus],
                    },
                },
                "required": [
                    "maximum_completion_minutes",
                    "play_status",
                ],
                "additionalProperties": False,
            },
            "unmatched_phrases": {
                "type": "array",
                "items": {"type": "string", "maxLength": 100},
                "maxItems": MAX_UNMATCHED_PHRASES,
            },
        },
        "required": [
            "version",
            "preferences",
            "constraints",
            "unmatched_phrases",
        ],
        "additionalProperties": False,
    }
