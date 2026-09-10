from app.gemini.prompt.contracts import (
    PROMPT_INTERPRETATION_VERSION,
    PromptConceptKind,
    PromptVocabulary,
    PromptVocabularyEntry,
)
from app.gemini.prompt.schema import (
    MAX_COMPLETION_MINUTES,
    MIN_COMPLETION_MINUTES,
    build_prompt_interpretation_response_schema,
)


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


def test_response_schema_is_closed_bounded_and_vocabulary_scoped() -> None:
    schema = build_prompt_interpretation_response_schema(_vocabulary())

    assert schema["additionalProperties"] is False
    assert schema["properties"]["version"]["enum"] == [
        PROMPT_INTERPRETATION_VERSION
    ]
    preferences = schema["properties"]["preferences"]
    assert preferences["maxItems"] == 16
    assert preferences["items"]["properties"]["concept_id"]["enum"] == [
        "genre:12",
        "mood:relaxing",
    ]
    assert preferences["items"]["additionalProperties"] is False
    completion = schema["properties"]["constraints"]["properties"][
        "maximum_completion_minutes"
    ]["anyOf"][0]
    assert completion["minimum"] == MIN_COMPLETION_MINUTES
    assert completion["maximum"] == MAX_COMPLETION_MINUTES
    assert schema["properties"]["unmatched_phrases"]["maxItems"] == 8


def test_response_schema_rejects_an_empty_vocabulary() -> None:
    vocabulary = PromptVocabulary(version="v1", entries=())

    try:
        build_prompt_interpretation_response_schema(vocabulary)
    except ValueError as error:
        assert str(error) == "Prompt interpretation requires a vocabulary."
    else:
        raise AssertionError("Expected empty vocabulary rejection.")
