from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.gemini.prompt.contracts import (
    PROMPT_INTERPRETATION_VERSION,
    PromptConceptKind,
    PromptConceptPreference,
    PromptConstraints,
    PromptInterpretation,
    PromptVocabulary,
    PromptVocabularyEntry,
)
from app.gemini.prompt.reads import load_prompt_candidates
from app.gemini.prompt.validation import validate_prompt_interpretation
from app.gemini.traits.contracts import calculate_facts_fingerprint
from app.gemini.traits.facts import build_game_trait_facts
from app.gemini.traits.prompt import (
    GAME_TRAIT_DERIVATION_VERSION,
    GAME_TRAIT_MODEL_ID,
    GAME_TRAIT_SCHEMA_VERSION,
)
from app.models import (
    Game,
    GameCurrentTraitDerivation,
    GameIGDBMetadataTerm,
    GameTraitDerivation,
    GameTraitMood,
    IGDBMetadataTerm,
    Profile,
    ProfileGame,
)
from app.recommendations.contracts import PlayStatus


NOW = datetime(2026, 9, 10, tzinfo=UTC)


def _validated_concepts():
    vocabulary = PromptVocabulary(
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
    interpretation = PromptInterpretation(
        version=PROMPT_INTERPRETATION_VERSION,
        preferences=(
            PromptConceptPreference(
                concept_id="genre:12",
                direction="desired",
                importance=2,
            ),
            PromptConceptPreference(
                concept_id="mood:relaxing",
                direction="desired",
                importance=3,
            ),
        ),
        constraints=PromptConstraints(
            maximum_completion_minutes=None,
            play_status=PlayStatus.EITHER,
        ),
        unmatched_phrases=(),
    )
    return validate_prompt_interpretation(
        interpretation,
        vocabulary,
    ).concepts


def _derivation(game: Game, *, current_fingerprint: bool):
    fingerprint = calculate_facts_fingerprint(build_game_trait_facts(game))
    return GameTraitDerivation(
        steam_app_id=game.steam_app_id,
        schema_version=GAME_TRAIT_SCHEMA_VERSION,
        derivation_version=GAME_TRAIT_DERIVATION_VERSION,
        model_id=GAME_TRAIT_MODEL_ID,
        facts_fingerprint=(fingerprint if current_fingerprint else "0" * 64),
        derived_at=NOW,
        story_focus_value=2,
        story_focus_confidence=Decimal("0.70"),
        combat_intensity_value=None,
        combat_intensity_confidence=Decimal("0"),
        difficulty_value=None,
        difficulty_confidence=Decimal("0"),
        pacing_value=1,
        pacing_confidence=Decimal("0.80"),
        session_friendliness_value=5,
        session_friendliness_confidence=Decimal("0.90"),
        exploration_focus_value=None,
        exploration_focus_confidence=Decimal("0"),
    )


def test_reads_profile_owned_facts_and_only_current_cached_traits() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        profile = Profile(steam_id="1", display_name="Player")
        other = Profile(steam_id="2", display_name="Other")
        genre = IGDBMetadataTerm(kind="genre", igdb_id=12, name="RPG")
        fresh_game = Game(
            steam_app_id=10,
            name="Fresh",
            igdb_status="ready",
            summary="A calm role-playing adventure.",
            metadata_term_links=[GameIGDBMetadataTerm(term=genre)],
        )
        stale_game = Game(
            steam_app_id=20,
            name="Stale",
            igdb_status="ready",
            summary="An older role-playing adventure.",
            metadata_term_links=[GameIGDBMetadataTerm(term=genre)],
        )
        unowned_game = Game(
            steam_app_id=30,
            name="Unowned",
            igdb_status="ready",
        )
        session.add_all([profile, other, fresh_game, stale_game, unowned_game])
        session.flush()
        session.add_all(
            [
                ProfileGame(profile_id=profile.id, steam_app_id=10),
                ProfileGame(profile_id=profile.id, steam_app_id=20),
                ProfileGame(profile_id=other.id, steam_app_id=30),
            ]
        )
        fresh = _derivation(fresh_game, current_fingerprint=True)
        stale = _derivation(stale_game, current_fingerprint=False)
        session.add_all([fresh, stale])
        session.flush()
        session.add_all(
            [
                GameCurrentTraitDerivation(
                    steam_app_id=10,
                    derivation_id=fresh.id,
                ),
                GameCurrentTraitDerivation(
                    steam_app_id=20,
                    derivation_id=stale.id,
                ),
                GameTraitMood(
                    derivation_id=fresh.id,
                    label="relaxing",
                    confidence=Decimal("0.85"),
                ),
            ]
        )
        session.commit()

        candidates = load_prompt_candidates(
            session,
            profile_id=profile.id,
            concepts=_validated_concepts(),
        )

    assert [item.facts.steam_app_id for item in candidates] == [10, 20]
    assert candidates[0].facts.genre_ids == (12,)
    assert candidates[0].facts.theme_ids is None
    assert candidates[0].traits is not None
    assert candidates[0].traits.numeric_value("pacing").value == 1
    assert candidates[0].traits.mood_value("relaxing").confidence == Decimal(
        "0.85"
    )
    assert candidates[1].traits is None
    engine.dispose()
