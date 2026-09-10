from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.gemini.traits.planning import (
    load_game_trait_generation_plan,
    load_owned_ready_game_trait_inventory,
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
    Profile,
    ProfileGame,
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


def test_inventory_selects_owned_ready_games_and_reports_freshness() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        profile = Profile(
            steam_id="76561198000000000",
            display_name="Tester",
        )
        session.add(profile)
        session.add_all(
            [
                Game(steam_app_id=10, name="Current", igdb_status="ready"),
                Game(steam_app_id=20, name="Pending", igdb_status="ready"),
                Game(steam_app_id=30, name="Not ready", igdb_status="pending"),
                Game(steam_app_id=40, name="Unowned", igdb_status="ready"),
            ]
        )
        session.flush()
        session.add_all(
            [
                ProfileGame(profile_id=profile.id, steam_app_id=10),
                ProfileGame(profile_id=profile.id, steam_app_id=20),
                ProfileGame(profile_id=profile.id, steam_app_id=30),
            ]
        )
        session.commit()
        _add_matching_current_derivation(session, 10)

        inventory = load_owned_ready_game_trait_inventory(session)

        assert inventory.ready_owned_game_count == 2
        assert inventory.current_steam_app_ids == (10,)
        assert inventory.pending_steam_app_ids == (20,)
        assert session.in_transaction() is False

    engine.dispose()
