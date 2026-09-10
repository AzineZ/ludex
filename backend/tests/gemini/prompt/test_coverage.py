from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.gemini.prompt.coverage import get_prompt_trait_coverage
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
    GameTraitDerivation,
    Profile,
    ProfileGame,
)


NOW = datetime(2026, 9, 10, tzinfo=UTC)


def _add_library(
    session: Session,
    *,
    game_count: int,
    current_count: int,
) -> int:
    profile = Profile(steam_id="1", display_name="Player")
    session.add(profile)
    session.flush()
    games = [
        Game(
            steam_app_id=index + 1,
            name=f"Game {index + 1}",
            igdb_status="ready",
            summary="A grounded summary.",
        )
        for index in range(game_count)
    ]
    session.add_all(games)
    session.flush()
    session.add_all(
        ProfileGame(
            profile_id=profile.id,
            steam_app_id=game.steam_app_id,
        )
        for game in games
    )
    for game in games[:current_count]:
        derivation = GameTraitDerivation(
            steam_app_id=game.steam_app_id,
            schema_version=GAME_TRAIT_SCHEMA_VERSION,
            derivation_version=GAME_TRAIT_DERIVATION_VERSION,
            model_id=GAME_TRAIT_MODEL_ID,
            facts_fingerprint=calculate_facts_fingerprint(
                build_game_trait_facts(game)
            ),
            derived_at=NOW,
            story_focus_value=None,
            story_focus_confidence=Decimal("0"),
            combat_intensity_value=None,
            combat_intensity_confidence=Decimal("0"),
            difficulty_value=None,
            difficulty_confidence=Decimal("0"),
            pacing_value=None,
            pacing_confidence=Decimal("0"),
            session_friendliness_value=None,
            session_friendliness_confidence=Decimal("0"),
            exploration_focus_value=None,
            exploration_focus_confidence=Decimal("0"),
        )
        session.add(derivation)
        session.flush()
        session.add(
            GameCurrentTraitDerivation(
                steam_app_id=game.steam_app_id,
                derivation_id=derivation.id,
            )
        )
    session.commit()
    return profile.id


def test_exact_ninety_percent_enables_subjective_matching() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        profile_id = _add_library(
            session,
            game_count=10,
            current_count=9,
        )
        coverage = get_prompt_trait_coverage(
            session,
            profile_id=profile_id,
        )

    assert coverage.ready_game_count == 10
    assert coverage.current_trait_game_count == 9
    assert coverage.coverage_basis_points == 9_000
    assert coverage.subjective_available is True
    engine.dispose()


def test_zero_ready_games_is_unavailable_not_complete() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        profile_id = _add_library(
            session,
            game_count=0,
            current_count=0,
        )
        coverage = get_prompt_trait_coverage(
            session,
            profile_id=profile_id,
        )

    assert coverage.coverage_basis_points == 0
    assert coverage.subjective_available is False
    engine.dispose()
