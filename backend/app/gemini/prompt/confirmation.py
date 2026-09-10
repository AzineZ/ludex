from enum import StrEnum
from hashlib import sha256
from json import dumps

from pydantic import BaseModel, ConfigDict, Field

from app.gemini.prompt.contracts import (
    PromptConceptPreference,
    PromptConstraints,
)
from app.gemini.prompt.coverage import PromptTraitCoverage
from app.gemini.prompt.validation import ValidatedPromptInterpretation
from app.recommendations.contracts import PlayStatus


class PromptConfirmationState(StrEnum):
    READY = "ready"
    FACTUAL_ONLY = "factual_only"
    GUIDED_ONLY = "guided_only"


class PromptConfirmationSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    interpretation_version: str
    vocabulary_version: str
    state: PromptConfirmationState
    interpreted_preferences: tuple[PromptConceptPreference, ...]
    active_preferences: tuple[PromptConceptPreference, ...]
    unavailable_subjective_concept_ids: tuple[str, ...]
    constraints: PromptConstraints
    unmatched_phrases: tuple[str, ...]
    ready_trait_game_count: int = Field(ge=0)
    current_trait_game_count: int = Field(ge=0)
    trait_coverage_basis_points: int = Field(ge=0, le=10_000)

    @property
    def can_generate(self) -> bool:
        return self.state is not PromptConfirmationState.GUIDED_ONLY


def _has_hard_constraint(constraints: PromptConstraints) -> bool:
    return (
        constraints.maximum_completion_minutes is not None
        or constraints.play_status is not PlayStatus.EITHER
    )


def build_prompt_confirmation_snapshot(
    validated: ValidatedPromptInterpretation,
    coverage: PromptTraitCoverage,
) -> PromptConfirmationSnapshot:
    """Freeze the exact honest interpretation a visitor may confirm."""
    subjective = tuple(
        concept for concept in validated.concepts if concept.is_subjective
    )
    factual = tuple(
        concept for concept in validated.concepts if not concept.is_subjective
    )
    all_preferences = tuple(
        concept.preference for concept in validated.concepts
    )

    has_hard_constraint = _has_hard_constraint(
        validated.interpretation.constraints
    )
    if not all_preferences and not has_hard_constraint:
        state = PromptConfirmationState.GUIDED_ONLY
        active_preferences = ()
        unavailable_ids = ()
    elif not subjective or coverage.subjective_available:
        state = PromptConfirmationState.READY
        active_preferences = all_preferences
        unavailable_ids: tuple[str, ...] = ()
    elif factual or has_hard_constraint:
        state = PromptConfirmationState.FACTUAL_ONLY
        active_preferences = tuple(
            concept.preference for concept in factual
        )
        unavailable_ids = tuple(
            concept.preference.concept_id for concept in subjective
        )
    else:
        state = PromptConfirmationState.GUIDED_ONLY
        active_preferences = ()
        unavailable_ids = tuple(
            concept.preference.concept_id for concept in subjective
        )

    payload = {
        "interpretation_version": validated.interpretation.version,
        "vocabulary_version": validated.vocabulary_version,
        "state": state.value,
        "interpreted_preferences": [
            preference.model_dump(mode="json")
            for preference in all_preferences
        ],
        "active_preferences": [
            preference.model_dump(mode="json")
            for preference in active_preferences
        ],
        "unavailable_subjective_concept_ids": unavailable_ids,
        "constraints": validated.interpretation.constraints.model_dump(
            mode="json"
        ),
        "unmatched_phrases": validated.interpretation.unmatched_phrases,
        "ready_trait_game_count": coverage.ready_game_count,
        "current_trait_game_count": coverage.current_trait_game_count,
        "trait_coverage_basis_points": coverage.coverage_basis_points,
    }
    fingerprint = sha256(
        dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return PromptConfirmationSnapshot(
        fingerprint=fingerprint,
        **payload,
    )
