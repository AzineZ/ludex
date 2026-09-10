from app.gemini.prompt.confirmation import (
    PromptConfirmationState,
    build_prompt_confirmation_snapshot,
)
from app.gemini.prompt.contracts import (
    PROMPT_INTERPRETATION_VERSION,
    PromptConceptKind,
    PromptConceptPreference,
    PromptConstraints,
    PromptInterpretation,
    PromptVocabulary,
    PromptVocabularyEntry,
)
from app.gemini.prompt.coverage import PromptTraitCoverage
from app.gemini.prompt.validation import validate_prompt_interpretation
from app.recommendations.contracts import PlayStatus


def _snapshot(
    concept_ids: tuple[str, ...],
    *,
    coverage_available: bool,
    maximum_minutes: int | None = None,
):
    entries = {
        "genre:12": PromptVocabularyEntry(
            concept_id="genre:12",
            kind=PromptConceptKind.GENRE,
            label="Role-playing",
            igdb_id=12,
        ),
        "mood:relaxing": PromptVocabularyEntry(
            concept_id="mood:relaxing",
            kind=PromptConceptKind.MOOD,
            label="Relaxing",
        ),
    }
    interpretation = PromptInterpretation(
        version=PROMPT_INTERPRETATION_VERSION,
        preferences=tuple(
            PromptConceptPreference(
                concept_id=concept_id,
                direction="desired",
                importance=2,
            )
            for concept_id in concept_ids
        ),
        constraints=PromptConstraints(
            maximum_completion_minutes=maximum_minutes,
            play_status=PlayStatus.EITHER,
        ),
        unmatched_phrases=(),
    )
    vocabulary = PromptVocabulary(
        version="v1",
        entries=tuple(entries[concept_id] for concept_id in concept_ids),
    )
    validated = validate_prompt_interpretation(
        interpretation,
        vocabulary,
    )
    coverage = PromptTraitCoverage(
        ready_game_count=10,
        current_trait_game_count=9 if coverage_available else 8,
        coverage_basis_points=9_000 if coverage_available else 8_000,
        subjective_available=coverage_available,
    )
    return build_prompt_confirmation_snapshot(validated, coverage)


def test_sufficient_coverage_keeps_subjective_preferences() -> None:
    snapshot = _snapshot(
        ("mood:relaxing",),
        coverage_available=True,
    )
    assert snapshot.state is PromptConfirmationState.READY
    assert snapshot.can_generate is True
    assert snapshot.active_preferences == snapshot.interpreted_preferences


def test_mixed_prompt_requires_explicit_factual_only_confirmation() -> None:
    snapshot = _snapshot(
        ("mood:relaxing", "genre:12"),
        coverage_available=False,
    )
    assert snapshot.state is PromptConfirmationState.FACTUAL_ONLY
    assert [item.concept_id for item in snapshot.active_preferences] == [
        "genre:12"
    ]
    assert snapshot.unavailable_subjective_concept_ids == (
        "mood:relaxing",
    )
    assert snapshot.can_generate is True


def test_pure_subjective_prompt_routes_to_guided_flow() -> None:
    snapshot = _snapshot(
        ("mood:relaxing",),
        coverage_available=False,
    )
    assert snapshot.state is PromptConfirmationState.GUIDED_ONLY
    assert snapshot.active_preferences == ()
    assert snapshot.can_generate is False


def test_hard_constraint_is_an_honest_factual_remainder() -> None:
    snapshot = _snapshot(
        ("mood:relaxing",),
        coverage_available=False,
        maximum_minutes=120,
    )
    assert snapshot.state is PromptConfirmationState.FACTUAL_ONLY
    assert snapshot.can_generate is True


def test_unmatched_only_interpretation_does_not_generate_arbitrary_games() -> None:
    interpretation = PromptInterpretation(
        version=PROMPT_INTERPRETATION_VERSION,
        preferences=(),
        constraints=PromptConstraints(
            maximum_completion_minutes=None,
            play_status=PlayStatus.EITHER,
        ),
        unmatched_phrases=("something indescribable",),
    )
    validated = validate_prompt_interpretation(
        interpretation,
        PromptVocabulary(version="v1", entries=()),
    )
    snapshot = build_prompt_confirmation_snapshot(
        validated,
        PromptTraitCoverage(10, 10, 10_000, True),
    )

    assert snapshot.state is PromptConfirmationState.GUIDED_ONLY
    assert snapshot.can_generate is False


def test_confirmation_fingerprint_is_stable_and_changes_with_coverage() -> None:
    first = _snapshot(("genre:12",), coverage_available=False)
    second = _snapshot(("genre:12",), coverage_available=False)
    changed = _snapshot(("genre:12",), coverage_available=True)
    assert first.fingerprint == second.fingerprint
    assert first.fingerprint != changed.fingerprint
