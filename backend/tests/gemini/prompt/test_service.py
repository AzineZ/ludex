from unittest.mock import Mock

import pytest

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
from app.gemini.prompt.service import (
    PromptConfirmationStaleError,
    PromptGuidedFallbackRequired,
    retrieve_confirmed_prompt_candidates,
)
from app.gemini.prompt.validation import validate_prompt_interpretation
from app.gemini.prompt.scoring import PromptCandidate
from app.recommendations.candidate_facts import CandidateFacts
from app.recommendations.contracts import PlayStatus


def _validated(*, subjective: bool = False):
    concept_id = "mood:relaxing" if subjective else "genre:12"
    entry = PromptVocabularyEntry(
        concept_id=concept_id,
        kind=(
            PromptConceptKind.MOOD
            if subjective
            else PromptConceptKind.GENRE
        ),
        label="Relaxing" if subjective else "RPG",
        igdb_id=None if subjective else 12,
    )
    return validate_prompt_interpretation(
        PromptInterpretation(
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
        ),
        PromptVocabulary(version="v1", entries=(entry,)),
    )


def test_service_rejects_a_confirmation_when_coverage_changed(
    monkeypatch,
) -> None:
    validated = _validated()
    confirmed = build_prompt_confirmation_snapshot(
        validated,
        PromptTraitCoverage(10, 8, 8_000, False),
    )
    monkeypatch.setattr(
        "app.gemini.prompt.service.get_prompt_trait_coverage",
        lambda session, profile_id: PromptTraitCoverage(
            10, 9, 9_000, True
        ),
    )

    with pytest.raises(PromptConfirmationStaleError):
        retrieve_confirmed_prompt_candidates(
            Mock(),
            profile_id=1,
            validated=validated,
            confirmed_snapshot=confirmed,
            session_excluded_steam_app_ids=frozenset(),
        )


def test_service_refuses_to_rank_a_guided_only_request(monkeypatch) -> None:
    validated = _validated(subjective=True)
    coverage = PromptTraitCoverage(10, 8, 8_000, False)
    confirmed = build_prompt_confirmation_snapshot(validated, coverage)
    assert confirmed.state is PromptConfirmationState.GUIDED_ONLY
    monkeypatch.setattr(
        "app.gemini.prompt.service.get_prompt_trait_coverage",
        lambda session, profile_id: coverage,
    )

    with pytest.raises(PromptGuidedFallbackRequired):
        retrieve_confirmed_prompt_candidates(
            Mock(),
            profile_id=1,
            validated=validated,
            confirmed_snapshot=confirmed,
            session_excluded_steam_app_ids=frozenset(),
        )


def test_service_revalidates_then_scores_the_cached_owned_library(
    monkeypatch,
) -> None:
    validated = _validated()
    coverage = PromptTraitCoverage(10, 9, 9_000, True)
    confirmed = build_prompt_confirmation_snapshot(validated, coverage)
    monkeypatch.setattr(
        "app.gemini.prompt.service.get_prompt_trait_coverage",
        lambda session, profile_id: coverage,
    )
    candidates = (
        PromptCandidate(
            facts=CandidateFacts(
                steam_app_id=20,
                owned_by_selected_profile=True,
                total_playtime_minutes=0,
                normal_completion_seconds=None,
                genre_ids=(),
                theme_ids=None,
                keyword_ids=None,
                game_mode_ids=None,
            ),
            traits=None,
        ),
        PromptCandidate(
            facts=CandidateFacts(
                steam_app_id=10,
                owned_by_selected_profile=True,
                total_playtime_minutes=0,
                normal_completion_seconds=None,
                genre_ids=(12,),
                theme_ids=None,
                keyword_ids=None,
                game_mode_ids=None,
            ),
            traits=None,
        ),
    )
    monkeypatch.setattr(
        "app.gemini.prompt.service.load_prompt_candidates",
        lambda session, profile_id, concepts: candidates,
    )

    result = retrieve_confirmed_prompt_candidates(
        Mock(),
        profile_id=1,
        validated=validated,
        confirmed_snapshot=confirmed,
        session_excluded_steam_app_ids=frozenset(),
    )

    assert result.eligible_count == 2
    assert [item.steam_app_id for item in result.candidates] == [10, 20]
