from dataclasses import dataclass

from app.gemini.prompt.contracts import (
    PROMPT_INTERPRETATION_VERSION,
    PromptConceptKind,
    PromptConceptPreference,
    PromptInterpretation,
    PromptVocabulary,
    PromptVocabularyEntry,
)


@dataclass(frozen=True)
class ValidatedPromptConcept:
    definition: PromptVocabularyEntry
    preference: PromptConceptPreference

    @property
    def is_subjective(self) -> bool:
        return self.definition.kind in {
            PromptConceptKind.NUMERIC_TRAIT,
            PromptConceptKind.MOOD,
        }


@dataclass(frozen=True)
class ValidatedPromptInterpretation:
    interpretation: PromptInterpretation
    vocabulary_version: str
    concepts: tuple[ValidatedPromptConcept, ...]


def validate_prompt_interpretation(
    interpretation: PromptInterpretation,
    vocabulary: PromptVocabulary,
) -> ValidatedPromptInterpretation:
    """Resolve every model-returned concept against the supplied vocabulary."""
    if interpretation.version != PROMPT_INTERPRETATION_VERSION:
        raise ValueError("The prompt interpretation version is unsupported.")

    definitions = {
        entry.concept_id: entry
        for entry in vocabulary.entries
    }
    concepts: list[ValidatedPromptConcept] = []
    for preference in interpretation.preferences:
        definition = definitions.get(preference.concept_id)
        if definition is None:
            raise ValueError("The prompt interpretation contains an unknown ID.")
        if (
            definition.kind is PromptConceptKind.NUMERIC_TRAIT
        ) != (preference.target is not None):
            raise ValueError("The prompt concept target is invalid.")
        concepts.append(
            ValidatedPromptConcept(
                definition=definition,
                preference=preference,
            )
        )

    return ValidatedPromptInterpretation(
        interpretation=interpretation,
        vocabulary_version=vocabulary.version,
        concepts=tuple(concepts),
    )
