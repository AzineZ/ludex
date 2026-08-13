from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.gemini.traits.facts import build_game_trait_facts
from app.gemini.traits.freshness import (
    is_game_trait_derivation_current,
)
from app.gemini.traits.contracts import GameTraitFacts
from app.models import (
    Game,
    GameCurrentTraitDerivation,
    GameIGDBMetadataTerm,
    GameTraitDerivation,
)


@dataclass(frozen=True)
class GameTraitGenerationPlan:
    """Describe whether one saved game requires classification."""

    steam_app_id: int
    facts: GameTraitFacts
    current_derivation_id: int | None
    needs_generation: bool


def load_game_trait_generation_plan(
    session: Session,
    steam_app_id: int,
) -> GameTraitGenerationPlan:
    """Load canonical facts and determine derivation freshness.

    The complete read transaction closes before the plan is returned. A caller
    may therefore perform slow external classification without retaining the
    database transaction.

    Args:
        session: Database session used for the factual read.
        steam_app_id: Shared Steam game to inspect.

    Returns:
        Immutable facts, current derivation identity, and generation decision.

    Raises:
        ValueError: If the Steam game is not saved locally.
    """
    with session.begin():
        game = session.scalar(
            select(Game)
            .options(
                selectinload(Game.metadata_term_links).selectinload(
                    GameIGDBMetadataTerm.term
                )
            )
            .where(Game.steam_app_id == steam_app_id)
        )

        if game is None:
            raise ValueError(
                "Trait planning must reference a saved Steam game."
            )

        facts = build_game_trait_facts(game)

        current_derivation = session.scalar(
            select(GameTraitDerivation)
            .join(
                GameCurrentTraitDerivation,
                GameCurrentTraitDerivation.derivation_id
                == GameTraitDerivation.id,
            )
            .where(
                GameCurrentTraitDerivation.steam_app_id
                == steam_app_id
            )
        )

        current_derivation_id = (
            current_derivation.id
            if current_derivation is not None
            else None
        )
        needs_generation = not is_game_trait_derivation_current(
            current_derivation,
            facts,
        )

    return GameTraitGenerationPlan(
        steam_app_id=steam_app_id,
        facts=facts,
        current_derivation_id=current_derivation_id,
        needs_generation=needs_generation,
    )
