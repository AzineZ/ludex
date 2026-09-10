from enum import StrEnum
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.recommendations.contracts import CompletionMinutes, PlayStatus


PROMPT_INTERPRETATION_VERSION = "prompt-preference-v1"
PROMPT_SCORING_VERSION = "prompt-hybrid-v1"
MAX_PROMPT_CHARACTERS = 500
MAX_PROMPT_CONCEPTS = 16
MAX_PROMPT_VOCABULARY_ENTRIES = 256
MAX_UNMATCHED_PHRASES = 8

Importance = Annotated[int, Field(strict=True, ge=1, le=3)]
TraitTarget = Annotated[int, Field(strict=True, ge=0, le=5)]


class FrozenContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PromptConceptKind(StrEnum):
    GENRE = "genre"
    THEME = "theme"
    KEYWORD = "keyword"
    GAME_MODE = "game_mode"
    NUMERIC_TRAIT = "numeric_trait"
    MOOD = "mood"


class PromptPreferenceDirection(StrEnum):
    DESIRED = "desired"
    AVOIDED = "avoided"


class PromptText(FrozenContract):
    text: str = Field(min_length=1, max_length=MAX_PROMPT_CHARACTERS)

    @field_validator("text")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Prompt text must not be blank.")
        return normalized


class PromptVocabularyEntry(FrozenContract):
    concept_id: str = Field(min_length=3, max_length=80)
    kind: PromptConceptKind
    label: str = Field(min_length=1, max_length=255)
    igdb_id: int | None = Field(default=None, strict=True, gt=0)

    @field_validator("concept_id", "label")
    @classmethod
    def reject_padded_or_multiline_text(cls, value: str) -> str:
        if value != value.strip() or "\n" in value or "\r" in value:
            raise ValueError("Vocabulary text must be trimmed and single-line.")
        return value

    @model_validator(mode="after")
    def validate_identity(self) -> "PromptVocabularyEntry":
        factual = self.kind in {
            PromptConceptKind.GENRE,
            PromptConceptKind.THEME,
            PromptConceptKind.KEYWORD,
            PromptConceptKind.GAME_MODE,
        }
        if factual != (self.igdb_id is not None):
            raise ValueError("Only factual vocabulary entries use IGDB IDs.")
        expected = (
            f"{self.kind.value}:{self.igdb_id}"
            if factual
            else self.concept_id
        )
        if factual and self.concept_id != expected:
            raise ValueError("Factual concept IDs must contain their IGDB ID.")
        return self


class PromptVocabulary(FrozenContract):
    version: str = Field(min_length=1, max_length=50)
    entries: tuple[PromptVocabularyEntry, ...] = Field(
        max_length=MAX_PROMPT_VOCABULARY_ENTRIES
    )

    @field_validator("entries")
    @classmethod
    def validate_entries(
        cls,
        entries: tuple[PromptVocabularyEntry, ...],
    ) -> tuple[PromptVocabularyEntry, ...]:
        identities = [entry.concept_id for entry in entries]
        if len(identities) != len(set(identities)):
            raise ValueError("Vocabulary concept IDs must be unique.")
        return entries


class PromptConceptPreference(FrozenContract):
    concept_id: str = Field(min_length=3, max_length=80)
    direction: PromptPreferenceDirection
    importance: Importance
    target: TraitTarget | None = None

    @model_validator(mode="after")
    def validate_target(self) -> "PromptConceptPreference":
        is_numeric_trait = self.concept_id.startswith("trait:")
        if is_numeric_trait != (self.target is not None):
            raise ValueError(
                "Only numeric trait preferences require a target."
            )
        return self


class PromptConstraints(FrozenContract):
    maximum_completion_minutes: CompletionMinutes | None
    play_status: PlayStatus


class PromptInterpretation(FrozenContract):
    version: str = Field(min_length=1, max_length=50)
    preferences: tuple[PromptConceptPreference, ...] = Field(
        max_length=MAX_PROMPT_CONCEPTS
    )
    constraints: PromptConstraints
    unmatched_phrases: tuple[str, ...] = Field(
        max_length=MAX_UNMATCHED_PHRASES
    )

    @field_validator("preferences")
    @classmethod
    def reject_duplicate_concepts(
        cls,
        preferences: tuple[PromptConceptPreference, ...],
    ) -> tuple[PromptConceptPreference, ...]:
        identities = [preference.concept_id for preference in preferences]
        if len(identities) != len(set(identities)):
            raise ValueError("Prompt concepts must be unique.")
        return preferences

    @field_validator("unmatched_phrases")
    @classmethod
    def normalize_unmatched_phrases(
        cls,
        phrases: tuple[str, ...],
    ) -> tuple[str, ...]:
        normalized: list[str] = []
        for phrase in phrases:
            cleaned = phrase.strip()
            if (
                not cleaned
                or cleaned != phrase
                or len(cleaned) > 100
                or "\n" in cleaned
                or "\r" in cleaned
            ):
                raise ValueError(
                    "Unmatched phrases must be short, trimmed, and single-line."
                )
            if cleaned in normalized:
                raise ValueError("Unmatched phrases must be unique.")
            normalized.append(cleaned)
        return tuple(normalized)
