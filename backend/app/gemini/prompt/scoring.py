from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from fractions import Fraction
from typing import Iterable

from app.gemini.prompt.confirmation import PromptConfirmationSnapshot
from app.gemini.prompt.contracts import (
    PROMPT_SCORING_VERSION,
    PromptConceptKind,
    PromptConstraints,
    PromptPreferenceDirection,
)
from app.gemini.prompt.validation import (
    ValidatedPromptConcept,
    ValidatedPromptInterpretation,
)
from app.recommendations.candidate_facts import CandidateFacts
from app.recommendations.eligibility import evaluate_candidate_eligibility


PROMPT_CANDIDATE_POOL_SIZE = 15


class PromptMatchState(StrEnum):
    MATCHED = "matched"
    NOT_MATCHED = "not_matched"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class NumericTraitValue:
    value: int
    confidence: Decimal

    def __post_init__(self) -> None:
        if not 0 <= self.value <= 5:
            raise ValueError("Numeric trait values must be between 0 and 5.")
        if not Decimal("0.30") <= self.confidence <= Decimal("1"):
            raise ValueError("Known trait confidence must be between .30 and 1.")


@dataclass(frozen=True)
class MoodValue:
    label: str
    confidence: Decimal

    def __post_init__(self) -> None:
        if not self.label or self.label != self.label.strip():
            raise ValueError("Mood labels must be non-empty and trimmed.")
        if not Decimal("0.30") <= self.confidence <= Decimal("1"):
            raise ValueError("Mood confidence must be between .30 and 1.")


@dataclass(frozen=True)
class PromptCandidateTraits:
    numeric_traits: tuple[tuple[str, NumericTraitValue | None], ...]
    moods: tuple[MoodValue, ...]

    def __post_init__(self) -> None:
        names = [name for name, value in self.numeric_traits]
        if len(names) != len(set(names)):
            raise ValueError("Numeric trait names must be unique.")
        mood_labels = [mood.label for mood in self.moods]
        if len(mood_labels) != len(set(mood_labels)):
            raise ValueError("Mood labels must be unique.")

    def numeric_value(self, name: str) -> NumericTraitValue | None:
        return dict(self.numeric_traits).get(name)

    def mood_value(self, label: str) -> MoodValue | None:
        return next((mood for mood in self.moods if mood.label == label), None)


@dataclass(frozen=True)
class PromptCandidate:
    facts: CandidateFacts
    traits: PromptCandidateTraits | None


@dataclass(frozen=True)
class PromptScoreContribution:
    concept_id: str
    direction: PromptPreferenceDirection
    importance: int
    match_state: PromptMatchState
    utility_numerator: int
    utility_denominator: int


@dataclass(frozen=True)
class PromptScoreEvidence:
    version: str
    score_basis_points: int
    active_importance: int
    contributions: tuple[PromptScoreContribution, ...]


@dataclass(frozen=True)
class PromptScoredCandidate:
    steam_app_id: int
    evidence: PromptScoreEvidence


@dataclass(frozen=True)
class PromptCandidatePool:
    candidates: tuple[PromptScoredCandidate, ...]
    eligible_count: int


def active_prompt_concepts(
    validated: ValidatedPromptInterpretation,
    snapshot: PromptConfirmationSnapshot,
) -> tuple[ValidatedPromptConcept, ...]:
    """Resolve the exact confirmation-approved concept subset."""
    active_ids = {
        preference.concept_id
        for preference in snapshot.active_preferences
    }
    return tuple(
        concept
        for concept in validated.concepts
        if concept.preference.concept_id in active_ids
    )


def _factual_ids(
    candidate: CandidateFacts,
    kind: PromptConceptKind,
) -> tuple[int, ...] | None:
    field_by_kind = {
        PromptConceptKind.GENRE: "genre_ids",
        PromptConceptKind.THEME: "theme_ids",
        PromptConceptKind.KEYWORD: "keyword_ids",
        PromptConceptKind.GAME_MODE: "game_mode_ids",
    }
    return getattr(candidate, field_by_kind[kind])


def _concept_utility(
    candidate: PromptCandidate,
    concept: ValidatedPromptConcept,
) -> tuple[PromptMatchState, Fraction]:
    definition = concept.definition
    preference = concept.preference
    sign = (
        1
        if preference.direction is PromptPreferenceDirection.DESIRED
        else -1
    )

    if definition.kind in {
        PromptConceptKind.GENRE,
        PromptConceptKind.THEME,
        PromptConceptKind.KEYWORD,
        PromptConceptKind.GAME_MODE,
    }:
        values = _factual_ids(candidate.facts, definition.kind)
        if values is None:
            return PromptMatchState.UNKNOWN, Fraction(0)
        if definition.igdb_id in values:
            return PromptMatchState.MATCHED, Fraction(sign)
        return PromptMatchState.NOT_MATCHED, Fraction(0)

    if candidate.traits is None:
        return PromptMatchState.UNKNOWN, Fraction(0)

    name = definition.concept_id.split(":", 1)[1]
    if definition.kind is PromptConceptKind.NUMERIC_TRAIT:
        value = candidate.traits.numeric_value(name)
        if value is None:
            return PromptMatchState.UNKNOWN, Fraction(0)
        distance_utility = Fraction(
            5 - abs(value.value - preference.target),
            5,
        )
        return (
            PromptMatchState.MATCHED,
            sign * distance_utility * Fraction(value.confidence),
        )

    mood = candidate.traits.mood_value(name)
    if mood is None:
        return PromptMatchState.NOT_MATCHED, Fraction(0)
    return (
        PromptMatchState.MATCHED,
        sign * Fraction(mood.confidence),
    )


def _round_signed_half_up(value: Fraction) -> int:
    if value < 0:
        return -_round_signed_half_up(-value)
    return (2 * value.numerator + value.denominator) // (
        2 * value.denominator
    )


def score_prompt_candidate(
    candidate: PromptCandidate,
    concepts: tuple[ValidatedPromptConcept, ...],
) -> PromptScoredCandidate:
    """Score one eligible candidate from validated cached concepts only."""
    active_importance = sum(
        concept.preference.importance for concept in concepts
    )
    total = Fraction(0)
    contributions: list[PromptScoreContribution] = []
    for concept in concepts:
        state, utility = _concept_utility(candidate, concept)
        importance = concept.preference.importance
        total += utility * importance
        contributions.append(
            PromptScoreContribution(
                concept_id=concept.preference.concept_id,
                direction=concept.preference.direction,
                importance=importance,
                match_state=state,
                utility_numerator=utility.numerator,
                utility_denominator=utility.denominator,
            )
        )

    normalized = (
        total * 10_000 / active_importance
        if active_importance
        else Fraction(0)
    )
    return PromptScoredCandidate(
        steam_app_id=candidate.facts.steam_app_id,
        evidence=PromptScoreEvidence(
            version=PROMPT_SCORING_VERSION,
            score_basis_points=_round_signed_half_up(normalized),
            active_importance=active_importance,
            contributions=tuple(contributions),
        ),
    )


def order_prompt_candidates(
    candidates: Iterable[PromptScoredCandidate],
) -> tuple[PromptScoredCandidate, ...]:
    return tuple(
        sorted(
            candidates,
            key=lambda candidate: (
                -candidate.evidence.score_basis_points,
                candidate.steam_app_id,
            ),
        )
    )


def retrieve_prompt_candidates(
    candidates: Iterable[PromptCandidate],
    *,
    concepts: tuple[ValidatedPromptConcept, ...],
    constraints: PromptConstraints,
    session_excluded_steam_app_ids: frozenset[int],
) -> PromptCandidatePool:
    """Apply hard rules, score all eligible games, then retain the top 15."""
    scored: list[PromptScoredCandidate] = []
    for candidate in candidates:
        eligibility = evaluate_candidate_eligibility(
            candidate.facts,
            reference_steam_app_ids=frozenset(),
            session_excluded_steam_app_ids=session_excluded_steam_app_ids,
            play_status=constraints.play_status,
            maximum_completion_minutes=(
                constraints.maximum_completion_minutes
            ),
        )
        if eligibility.eligible:
            scored.append(score_prompt_candidate(candidate, concepts))

    ordered = order_prompt_candidates(scored)
    return PromptCandidatePool(
        candidates=ordered[:PROMPT_CANDIDATE_POOL_SIZE],
        eligible_count=len(ordered),
    )
