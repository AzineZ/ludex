from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.gemini.traits.planning import (
    load_game_trait_generation_plan,
)
from app.gemini.traits.prompt import (
    GAME_TRAIT_DERIVATION_VERSION,
    GAME_TRAIT_MODEL_ID,
    GAME_TRAIT_SCHEMA_VERSION,
)
from app.gemini.traits.contracts import calculate_facts_fingerprint
from app.models import (
    Game,
    GameCurrentTraitDerivation,
    GameTraitDerivation,
)


def _add_matching_current_derivation(
    session: Session,
    steam_app_id: int,
) -> int:
    """Persist a current derivation matching one stored game's facts.

    Args:
        session: Database session receiving the derivation.
        steam_app_id: Stable ID of the stored game whose facts should match.

    Returns:
        Database ID of the saved derivation.
    """
    plan = load_game_trait_generation_plan(
        session,
        steam_app_id,
    )

    derivation = GameTraitDerivation(
        steam_app_id=steam_app_id,
        schema_version=GAME_TRAIT_SCHEMA_VERSION,
        derivation_version=GAME_TRAIT_DERIVATION_VERSION,
        model_id=GAME_TRAIT_MODEL_ID,
        facts_fingerprint=calculate_facts_fingerprint(plan.facts),
        derived_at=datetime(2026, 8, 12, tzinfo=UTC),
        story_focus_value=None,
        story_focus_confidence=Decimal("0.00"),
        combat_intensity_value=None,
        combat_intensity_confidence=Decimal("0.00"),
        difficulty_value=None,
        difficulty_confidence=Decimal("0.00"),
        pacing_value=None,
        pacing_confidence=Decimal("0.00"),
        session_friendliness_value=None,
        session_friendliness_confidence=Decimal("0.00"),
        exploration_focus_value=None,
        exploration_focus_confidence=Decimal("0.00"),
    )
    session.add(derivation)
    session.flush()
    derivation_id = derivation.id
    session.add(
        GameCurrentTraitDerivation(
            steam_app_id=steam_app_id,
            derivation_id=derivation_id,
        )
    )
    session.commit()

    return derivation_id


def test_plan_requires_generation_without_current_derivation() -> None:
    """Return canonical facts and require an initial classification."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(
            Game(
                steam_app_id=440,
                name="Example Adventure",
                summary="A story-driven adventure.",
            )
        )
        session.commit()

        plan = load_game_trait_generation_plan(session, 440)

        assert plan.steam_app_id == 440
        assert plan.facts.name == "Example Adventure"
        assert plan.facts.summary == "A story-driven adventure."
        assert plan.needs_generation is True
        assert session.in_transaction() is False

    engine.dispose()


def test_plan_reuses_current_derivation_until_facts_change() -> None:
    """Skip unchanged facts and detect a later factual change."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        game = Game(
            steam_app_id=440,
            name="Example Adventure",
            summary="A story-driven adventure.",
        )
        session.add(game)
        session.commit()

        derivation_id = _add_matching_current_derivation(
            session,
            440,
        )

        current_plan = load_game_trait_generation_plan(
            session,
            440,
        )

        assert current_plan.current_derivation_id == derivation_id
        assert current_plan.needs_generation is False
        assert session.in_transaction() is False

        game.summary = "A newly updated factual summary."
        session.commit()

        stale_plan = load_game_trait_generation_plan(
            session,
            440,
        )

        assert stale_plan.current_derivation_id == derivation_id
        assert stale_plan.needs_generation is True
        assert session.in_transaction() is False

    engine.dispose()
