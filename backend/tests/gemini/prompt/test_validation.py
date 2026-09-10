import pytest

from app.gemini.prompt.contracts import (
    PROMPT_INTERPRETATION_VERSION,
    PromptConceptKind,
    PromptConceptPreference,
    PromptConstraints,
    PromptInterpretation,
    PromptVocabulary,
    PromptVocabularyEntry,
)
from app.gemini.prompt.validation import validate_prompt_interpretation
from app.recommendations.contracts import PlayStatus


def _vocabulary() -> PromptVocabulary:
    return PromptVocabulary(
        version="v1",
        entries=(
            PromptVocabularyEntry(
                concept_id="genre:12",
                kind=PromptConceptKind.GENRE,
                label="Role-playing",
                igdb_id=12,
            ),
            PromptVocabularyEntry(
                concept_id="mood:relaxing",
                kind=PromptConceptKind.MOOD,
                label="Relaxing",
            ),
        ),
    )


def _interpretation(concept_id: str) -> PromptInterpretation:
    return PromptInterpretation(
        version=PROMPT_INTERPRETATION_VERSION,
        preferences=(
            PromptConceptPreference(
                concept_id=concept_id,
                direction="desired",
                importance=2,
            ),
        ),
        constraints=PromptConstraints(
            maximum_completion_minutes=None,
            play_status=PlayStatus.EITHER,
        ),
        unmatched_phrases=(),
    )


def test_resolves_only_ids_in_the_exact_vocabulary() -> None:
    result = validate_prompt_interpretation(
        _interpretation("genre:12"),
        _vocabulary(),
    )
    assert result.concepts[0].definition.label == "Role-playing"
    assert result.concepts[0].is_subjective is False

    with pytest.raises(ValueError, match="unknown ID"):
        validate_prompt_interpretation(
            _interpretation("genre:999"),
            _vocabulary(),
        )


def test_rejects_an_unrecognized_contract_version() -> None:
    interpretation = _interpretation("genre:12").model_copy(
        update={"version": "future"}
    )
    with pytest.raises(ValueError, match="version"):
        validate_prompt_interpretation(interpretation, _vocabulary())
