import pytest
from pydantic import ValidationError

from app.gemini.prompt.contracts import (
    PROMPT_INTERPRETATION_VERSION,
    PromptConceptPreference,
    PromptConstraints,
    PromptInterpretation,
    PromptPreferenceDirection,
    PromptText,
)
from app.recommendations.contracts import PlayStatus


def _constraints() -> PromptConstraints:
    return PromptConstraints(
        maximum_completion_minutes=None,
        play_status=PlayStatus.EITHER,
    )


def test_prompt_text_is_trimmed_and_bounded() -> None:
    assert PromptText(text="  something relaxing  ").text == (
        "something relaxing"
    )
    with pytest.raises(ValidationError):
        PromptText(text="x" * 501)


def test_numeric_trait_requires_bounded_target() -> None:
    preference = PromptConceptPreference(
        concept_id="trait:pacing",
        direction=PromptPreferenceDirection.DESIRED,
        importance=3,
        target=1,
    )
    assert preference.target == 1

    with pytest.raises(ValidationError):
        PromptConceptPreference(
            concept_id="trait:pacing",
            direction="desired",
            importance=3,
            target=None,
        )
    with pytest.raises(ValidationError):
        PromptConceptPreference(
            concept_id="mood:relaxing",
            direction="desired",
            importance=3,
            target=2,
        )


def test_interpretation_rejects_duplicate_concepts_and_extra_fields() -> None:
    preference = PromptConceptPreference(
        concept_id="genre:12",
        direction="desired",
        importance=2,
    )
    with pytest.raises(ValidationError, match="unique"):
        PromptInterpretation(
            version=PROMPT_INTERPRETATION_VERSION,
            preferences=(preference, preference),
            constraints=_constraints(),
            unmatched_phrases=(),
        )
    with pytest.raises(ValidationError):
        PromptInterpretation.model_validate(
            {
                "version": PROMPT_INTERPRETATION_VERSION,
                "preferences": [],
                "constraints": {
                    "maximum_completion_minutes": None,
                    "play_status": "either",
                },
                "unmatched_phrases": [],
                "game_ids": [10],
            }
        )


def test_unmatched_phrases_are_bounded_and_not_silently_normalized() -> None:
    with pytest.raises(ValidationError):
        PromptInterpretation(
            version=PROMPT_INTERPRETATION_VERSION,
            preferences=(),
            constraints=_constraints(),
            unmatched_phrases=("  unclear phrase  ",),
        )
