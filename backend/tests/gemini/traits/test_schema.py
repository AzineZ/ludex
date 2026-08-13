from json import dumps
from typing import Any

from app.gemini.traits.schema import build_game_trait_response_schema
from app.gemini.traits.contracts import NUMERIC_TRAIT_FIELDS


MOOD_LABELS = {
    "relaxing",
    "tense",
    "emotional",
    "humorous",
    "dark",
}

EVIDENCE_FIELDS = {
    "summary",
    "genre",
    "theme",
    "keyword",
    "game_mode",
    "time_to_beat",
    "release_information",
}


def _known_trait_schema(
    schema: dict[str, Any],
) -> dict[str, Any]:
    """Return the known numeric-trait branch."""
    return schema["properties"]["story_focus"]["anyOf"][0]


def _unknown_trait_schema(
    schema: dict[str, Any],
) -> dict[str, Any]:
    """Return the unknown numeric-trait branch."""
    return schema["properties"]["story_focus"]["anyOf"][1]


def test_requires_exact_top_level_response_fields() -> None:
    """Require every trait and moods while rejecting extra fields."""
    schema = build_game_trait_response_schema()
    expected_fields = {*NUMERIC_TRAIT_FIELDS, "moods"}

    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert set(schema["properties"]) == expected_fields
    assert set(schema["required"]) == expected_fields


def test_all_numeric_traits_share_known_and_unknown_states() -> None:
    """Give all six numeric traits the same strict state contract."""
    schema = build_game_trait_response_schema()
    expected_trait_schema = schema["properties"]["story_focus"]

    for trait_name in NUMERIC_TRAIT_FIELDS:
        assert schema["properties"][trait_name] == expected_trait_schema

    known = _known_trait_schema(schema)
    unknown = _unknown_trait_schema(schema)

    assert known["properties"]["value"] == {
        "type": "integer",
        "minimum": 0,
        "maximum": 5,
    }
    assert known["properties"]["confidence"] == {
        "type": "number",
        "minimum": 0.30,
        "maximum": 1.00,
    }
    assert known["properties"]["evidence"]["minItems"] == 1
    assert known["properties"]["evidence"]["maxItems"] == 3

    assert unknown["properties"]["value"] == {"type": "null"}
    assert unknown["properties"]["confidence"] == {
        "type": "number",
        "enum": [0],
    }
    assert unknown["properties"]["evidence"]["maxItems"] == 0


def test_mood_schema_uses_allowlist_and_supported_state() -> None:
    """Restrict moods to unique-domain labels with known confidence."""
    schema = build_game_trait_response_schema()
    mood = schema["properties"]["moods"]["items"]

    assert mood["type"] == "object"
    assert mood["additionalProperties"] is False
    assert set(mood["required"]) == {
        "label",
        "confidence",
        "evidence",
    }
    assert set(mood["properties"]["label"]["enum"]) == MOOD_LABELS
    assert mood["properties"]["confidence"] == {
        "type": "number",
        "minimum": 0.30,
        "maximum": 1.00,
    }
    assert mood["properties"]["evidence"]["minItems"] == 1
    assert mood["properties"]["evidence"]["maxItems"] == 3


def test_evidence_schema_restricts_factual_fields() -> None:
    """Restrict citations to the factual fields Ludex supplies."""
    schema = build_game_trait_response_schema()
    evidence = _known_trait_schema(
        schema
    )["properties"]["evidence"]["items"]

    assert evidence["type"] == "object"
    assert evidence["additionalProperties"] is False
    assert set(evidence["required"]) == {
        "field",
        "value",
        "reason",
    }
    assert set(evidence["properties"]["field"]["enum"]) == (
        EVIDENCE_FIELDS
    )
    assert evidence["properties"]["value"] == {"type": "string"}
    assert evidence["properties"]["reason"] == {"type": "string"}


def test_schema_avoids_unsupported_or_permissive_keywords() -> None:
    """Keep the provider schema within Gemini's documented subset."""
    serialized_schema = dumps(
        build_game_trait_response_schema(),
        sort_keys=True,
    )

    assert '"$defs"' not in serialized_schema
    assert '"pattern"' not in serialized_schema
    assert '"multipleOf"' not in serialized_schema
