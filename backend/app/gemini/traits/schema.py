from typing import Any

from app.gemini.traits.contracts import (
    MAX_GAMES_PER_TRAIT_REQUEST,
    NUMERIC_TRAIT_FIELDS,
)


MOOD_LABELS = (
    "relaxing",
    "tense",
    "emotional",
    "humorous",
    "dark",
)

EVIDENCE_FIELDS = (
    "summary",
    "genre",
    "theme",
    "keyword",
    "game_mode",
    "time_to_beat",
    "release_information",
)


def _build_evidence_schema() -> dict[str, Any]:
    """Build the provider-facing schema for one evidence citation.

    Returns:
        A strict object schema containing an allowlisted factual field, source
        value, and explanatory reason.
    """
    return {
        "type": "object",
        "properties": {
            "field": {
                "type": "string",
                "enum": list(EVIDENCE_FIELDS),
            },
            "value": {
                "type": "string",
            },
            "reason": {
                "type": "string",
            },
        },
        "required": [
            "field",
            "value",
            "reason",
        ],
        "additionalProperties": False,
    }


def _build_evidence_array_schema(
    *,
    minimum_items: int,
    maximum_items: int,
) -> dict[str, Any]:
    """Build one bounded array of structured evidence.

    Args:
        minimum_items: Minimum citations the model may return.
        maximum_items: Maximum citations the model may return.

    Returns:
        An array schema containing structured evidence items.
    """
    return {
        "type": "array",
        "items": _build_evidence_schema(),
        "minItems": minimum_items,
        "maxItems": maximum_items,
    }


def _build_known_trait_schema() -> dict[str, Any]:
    """Build the schema for one supported numeric interpretation.

    Returns:
        A strict known-trait object with value, confidence, and evidence.
    """
    return {
        "type": "object",
        "properties": {
            "value": {
                "type": "integer",
                "minimum": 0,
                "maximum": 5,
            },
            "confidence": {
                "type": "number",
                "minimum": 0.30,
                "maximum": 1.00,
            },
            "evidence": _build_evidence_array_schema(
                minimum_items=1,
                maximum_items=3,
            ),
        },
        "required": [
            "value",
            "confidence",
            "evidence",
        ],
        "additionalProperties": False,
    }


def _build_unknown_trait_schema() -> dict[str, Any]:
    """Build the exact schema for an unsupported numeric interpretation.

    Returns:
        A strict unknown-trait object containing null, zero, and no evidence.
    """
    return {
        "type": "object",
        "properties": {
            "value": {
                "type": "null",
            },
            "confidence": {
                "type": "number",
                "enum": [0],
            },
            "evidence": _build_evidence_array_schema(
                minimum_items=0,
                maximum_items=0,
            ),
        },
        "required": [
            "value",
            "confidence",
            "evidence",
        ],
        "additionalProperties": False,
    }


def _build_numeric_trait_schema() -> dict[str, Any]:
    """Build the known-or-unknown schema for one numeric trait.

    Returns:
        A schema requiring exactly one valid numeric-trait state.
    """
    return {
        "anyOf": [
            _build_known_trait_schema(),
            _build_unknown_trait_schema(),
        ]
    }


def _build_mood_schema() -> dict[str, Any]:
    """Build the schema for one supported mood.

    Returns:
        A strict mood object with an allowlisted label and grounded evidence.
    """
    return {
        "type": "object",
        "properties": {
            "label": {
                "type": "string",
                "enum": list(MOOD_LABELS),
            },
            "confidence": {
                "type": "number",
                "minimum": 0.30,
                "maximum": 1.00,
            },
            "evidence": _build_evidence_array_schema(
                minimum_items=1,
                maximum_items=3,
            ),
        },
        "required": [
            "label",
            "confidence",
            "evidence",
        ],
        "additionalProperties": False,
    }


def build_game_trait_response_schema() -> dict[str, Any]:
    """Build the Gemini structured-output schema for game traits.

    Returns:
        A new JSON Schema dictionary requiring all six numeric traits and the
        allowlisted mood array.
    """
    properties = {
        trait_name: _build_numeric_trait_schema()
        for trait_name in NUMERIC_TRAIT_FIELDS
    }
    properties["moods"] = {
        "type": "array",
        "items": _build_mood_schema(),
    }

    return {
        "type": "object",
        "properties": properties,
        "required": [
            *NUMERIC_TRAIT_FIELDS,
            "moods",
        ],
        "additionalProperties": False,
    }


def build_game_trait_batch_response_schema(
    steam_app_ids: tuple[int, ...],
) -> dict[str, Any]:
    """Build a strict response envelope for one exact game batch."""
    if not steam_app_ids or len(steam_app_ids) > MAX_GAMES_PER_TRAIT_REQUEST:
        raise ValueError("Trait batches must contain one through five games.")

    if len(steam_app_ids) != len(set(steam_app_ids)):
        raise ValueError("Trait batch Steam App IDs must be unique.")

    if any(
        not isinstance(steam_app_id, int)
        or isinstance(steam_app_id, bool)
        or steam_app_id <= 0
        for steam_app_id in steam_app_ids
    ):
        raise ValueError("Steam App IDs must be positive integers.")

    item_schema = {
        "type": "object",
        "properties": {
            "steam_app_id": {
                "type": "integer",
                "enum": list(steam_app_ids),
            },
            "traits": build_game_trait_response_schema(),
        },
        "required": ["steam_app_id", "traits"],
        "additionalProperties": False,
    }

    return {
        "type": "object",
        "properties": {
            "games": {
                "type": "array",
                "items": item_schema,
                "minItems": len(steam_app_ids),
                "maxItems": len(steam_app_ids),
            }
        },
        "required": ["games"],
        "additionalProperties": False,
    }
