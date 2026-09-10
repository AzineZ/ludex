from decimal import Decimal

from app.gemini.prompt.confirmation import build_prompt_confirmation_snapshot
from app.gemini.prompt.contracts import (
    PROMPT_INTERPRETATION_VERSION,
    PROMPT_SCORING_VERSION,
    PromptConceptKind,
    PromptConceptPreference,
    PromptConstraints,
    PromptInterpretation,
    PromptVocabulary,
    PromptVocabularyEntry,
)
from app.gemini.prompt.coverage import PromptTraitCoverage
from app.gemini.prompt.scoring import (
    MoodValue,
    NumericTraitValue,
    PromptCandidate,
    PromptCandidateTraits,
    PromptMatchState,
    active_prompt_concepts,
    retrieve_prompt_candidates,
    score_prompt_candidate,
)
from app.gemini.prompt.validation import validate_prompt_interpretation
from app.recommendations.candidate_facts import CandidateFacts
from app.recommendations.contracts import PlayStatus


def _candidate(
    steam_app_id: int = 1,
    *,
    genre_ids: tuple[int, ...] | None = (),
    playtime: int = 0,
    traits: PromptCandidateTraits | None = None,
) -> PromptCandidate:
    return PromptCandidate(
        facts=CandidateFacts(
            steam_app_id=steam_app_id,
            owned_by_selected_profile=True,
            total_playtime_minutes=playtime,
            normal_completion_seconds=None,
            genre_ids=genre_ids,
            theme_ids=(),
            keyword_ids=(),
            game_mode_ids=(),
        ),
        traits=traits,
    )


def _validated(
    *preferences: PromptConceptPreference,
):
    entries = {
        "genre:12": PromptVocabularyEntry(
            concept_id="genre:12",
            kind=PromptConceptKind.GENRE,
            label="RPG",
            igdb_id=12,
        ),
        "trait:pacing": PromptVocabularyEntry(
            concept_id="trait:pacing",
            kind=PromptConceptKind.NUMERIC_TRAIT,
            label="Pacing",
        ),
        "mood:relaxing": PromptVocabularyEntry(
            concept_id="mood:relaxing",
            kind=PromptConceptKind.MOOD,
            label="Relaxing",
        ),
    }
    interpretation = PromptInterpretation(
        version=PROMPT_INTERPRETATION_VERSION,
        preferences=preferences,
        constraints=PromptConstraints(
            maximum_completion_minutes=None,
            play_status=PlayStatus.EITHER,
        ),
        unmatched_phrases=(),
    )
    vocabulary = PromptVocabulary(
        version="v1",
        entries=tuple(entries[item.concept_id] for item in preferences),
    )
    return validate_prompt_interpretation(interpretation, vocabulary)


def _preference(
    concept_id: str,
    *,
    direction: str = "desired",
    importance: int = 1,
    target: int | None = None,
) -> PromptConceptPreference:
    return PromptConceptPreference(
        concept_id=concept_id,
        direction=direction,
        importance=importance,
        target=target,
    )


def test_factual_desired_and_avoided_matches_use_signed_utility() -> None:
    desired = _validated(_preference("genre:12")).concepts
    avoided = _validated(
        _preference("genre:12", direction="avoided")
    ).concepts

    positive = score_prompt_candidate(_candidate(genre_ids=(12,)), desired)
    negative = score_prompt_candidate(_candidate(genre_ids=(12,)), avoided)

    assert positive.evidence.version == PROMPT_SCORING_VERSION
    assert positive.evidence.score_basis_points == 10_000
    assert negative.evidence.score_basis_points == -10_000
    assert positive.evidence.contributions[0].match_state is (
        PromptMatchState.MATCHED
    )


def test_unknown_metadata_is_neutral_but_remains_in_denominator() -> None:
    concepts = _validated(
        _preference("genre:12", importance=1),
        _preference("mood:relaxing", importance=1),
    ).concepts
    result = score_prompt_candidate(
        _candidate(genre_ids=(12,), traits=None),
        concepts,
    )

    assert result.evidence.score_basis_points == 5_000
    assert result.evidence.active_importance == 2
    assert result.evidence.contributions[1].match_state is (
        PromptMatchState.UNKNOWN
    )


def test_numeric_similarity_and_confidence_are_deterministic() -> None:
    concepts = _validated(
        _preference("trait:pacing", importance=3, target=1)
    ).concepts
    traits = PromptCandidateTraits(
        numeric_traits=(
            (
                "pacing",
                NumericTraitValue(2, Decimal("0.75")),
            ),
        ),
        moods=(),
    )
    result = score_prompt_candidate(_candidate(traits=traits), concepts)

    assert result.evidence.score_basis_points == 6_000
    contribution = result.evidence.contributions[0]
    assert (contribution.utility_numerator, contribution.utility_denominator) == (
        3,
        5,
    )


def test_mood_uses_cached_confidence_and_absence_is_known_nonmatch() -> None:
    concepts = _validated(_preference("mood:relaxing")).concepts
    present = PromptCandidateTraits(
        numeric_traits=(),
        moods=(MoodValue("relaxing", Decimal("0.80")),),
    )
    absent = PromptCandidateTraits(numeric_traits=(), moods=())

    assert score_prompt_candidate(
        _candidate(traits=present), concepts
    ).evidence.score_basis_points == 8_000
    absent_result = score_prompt_candidate(_candidate(traits=absent), concepts)
    assert absent_result.evidence.score_basis_points == 0
    assert absent_result.evidence.contributions[0].match_state is (
        PromptMatchState.NOT_MATCHED
    )


def test_retrieval_scores_all_eligible_games_before_top_fifteen() -> None:
    validated = _validated(_preference("genre:12"))
    candidates = tuple(
        _candidate(
            steam_app_id=index,
            genre_ids=(12,) if index == 20 else (),
        )
        for index in range(1, 21)
    )
    pool = retrieve_prompt_candidates(
        candidates,
        concepts=validated.concepts,
        constraints=validated.interpretation.constraints,
        session_excluded_steam_app_ids=frozenset({2}),
    )

    assert pool.eligible_count == 19
    assert len(pool.candidates) == 15
    assert pool.candidates[0].steam_app_id == 20
    assert all(item.steam_app_id != 2 for item in pool.candidates)


def test_confirmation_removes_subjective_concepts_when_coverage_is_low() -> None:
    validated = _validated(
        _preference("mood:relaxing"),
        _preference("genre:12"),
    )
    coverage = PromptTraitCoverage(10, 8, 8_000, False)
    snapshot = build_prompt_confirmation_snapshot(validated, coverage)
    concepts = active_prompt_concepts(validated, snapshot)

    assert [item.preference.concept_id for item in concepts] == ["genre:12"]
