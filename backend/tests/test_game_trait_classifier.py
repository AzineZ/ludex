from unittest.mock import Mock

import pytest

from app.game_trait_classifier import (
    GameTraitInvalidResponseError,
    classify_game_traits,
)
from app.game_trait_prompt import (
    GAME_TRAIT_MODEL_ID,
    GAME_TRAIT_SYSTEM_INSTRUCTION,
    build_game_trait_user_prompt,
)
from app.game_trait_schema import build_game_trait_response_schema
from app.game_traits import GameTraitFacts
from app.gemini_client import (
    GeminiClient,
    GeminiUnavailableError,
)


def _facts() -> GameTraitFacts:
    """Return canonical facts for classifier tests."""
    return GameTraitFacts(
        name="Example Adventure",
        summary="A story-driven adventure.",
        genres=("Adventure",),
        themes=(),
        keywords=(),
        game_modes=("Single player",),
        time_to_beat=(),
        release_information=(),
    )


def _valid_response() -> dict[str, object]:
    """Return one complete grounded Gemini response."""
    evidence = {
        "field": "summary",
        "value": "A story-driven adventure.",
        "reason": "Directly supports the derived value.",
    }
    unknown_trait = {
        "value": None,
        "confidence": 0,
        "evidence": [],
    }

    return {
        "story_focus": {
            "value": 4,
            "confidence": 0.80,
            "evidence": [evidence],
        },
        "combat_intensity": unknown_trait,
        "difficulty": unknown_trait,
        "pacing": unknown_trait,
        "session_friendliness": unknown_trait,
        "exploration_focus": unknown_trait,
        "moods": [
            {
                "label": "emotional",
                "confidence": 0.80,
                "evidence": [evidence],
            }
        ],
    }


def test_classifies_with_versioned_prompt_and_schema() -> None:
    """Validate one grounded response from the configured classifier."""
    client = Mock(spec=GeminiClient)
    client.generate_structured_content.return_value = _valid_response()
    facts = _facts()

    response = classify_game_traits(client, facts)

    assert response.story_focus.value == 4
    assert response.moods[0].label == "emotional"

    client.generate_structured_content.assert_called_once_with(
        model_id=GAME_TRAIT_MODEL_ID,
        system_instruction=GAME_TRAIT_SYSTEM_INSTRUCTION,
        user_prompt=build_game_trait_user_prompt(facts),
        response_schema=build_game_trait_response_schema(),
    )


@pytest.mark.parametrize(
    "response_change",
    [
        {"story_focus": {"unsupported": True}},
        {"moods": [{"label": "cozy"}]},
    ],
)
def test_rejects_structurally_invalid_model_response(
    response_change: dict[str, object],
) -> None:
    """Translate Pydantic failures into one classifier-domain error."""
    raw_response = _valid_response()
    raw_response.update(response_change)

    client = Mock(spec=GeminiClient)
    client.generate_structured_content.return_value = raw_response

    with pytest.raises(
        GameTraitInvalidResponseError,
        match="invalid game-trait response",
    ):
        classify_game_traits(client, _facts())


def test_rejects_evidence_absent_from_supplied_facts() -> None:
    """Reject plausible citations that were not supplied to Gemini."""
    raw_response = _valid_response()
    raw_response["story_focus"] = {
        "value": 4,
        "confidence": 0.80,
        "evidence": [
            {
                "field": "theme",
                "value": "Drama",
                "reason": "Supports the derived value.",
            }
        ],
    }

    client = Mock(spec=GeminiClient)
    client.generate_structured_content.return_value = raw_response

    with pytest.raises(
        GameTraitInvalidResponseError,
        match="invalid game-trait response",
    ):
        classify_game_traits(client, _facts())


def test_preserves_transport_failure_category() -> None:
    """Allow orchestration to distinguish retryable transport failures."""
    upstream_error = GeminiUnavailableError(
        "Gemini is currently unavailable."
    )
    client = Mock(spec=GeminiClient)
    client.generate_structured_content.side_effect = upstream_error

    with pytest.raises(GeminiUnavailableError) as caught:
        classify_game_traits(client, _facts())

    assert caught.value is upstream_error


def test_classifies_corrective_retry_with_fresh_prompt() -> None:
    """Request a corrected response without changing model or schema."""
    client = Mock(spec=GeminiClient)
    client.generate_structured_content.return_value = _valid_response()
    facts = _facts()

    response = classify_game_traits(
        client,
        facts,
        corrective_retry=True,
    )

    assert response.story_focus.value == 4
    client.generate_structured_content.assert_called_once_with(
        model_id=GAME_TRAIT_MODEL_ID,
        system_instruction=GAME_TRAIT_SYSTEM_INSTRUCTION,
        user_prompt=build_game_trait_user_prompt(
            facts,
            corrective_retry=True,
        ),
        response_schema=build_game_trait_response_schema(),
    )
