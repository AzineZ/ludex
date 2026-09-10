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


@dataclass(frozen=True)
class OwnedReadyGameTraitInventory:
    """Summarize reusable and pending traits for owned IGDB-ready games."""

    plans: tuple[GameTraitGenerationPlan, ...]

    @property
    def ready_owned_game_count(self) -> int:
        return len(self.plans)

    @property
    def current_steam_app_ids(self) -> tuple[int, ...]:
        return tuple(
            plan.steam_app_id
            for plan in self.plans
            if not plan.needs_generation
        )

    @property
    def pending_steam_app_ids(self) -> tuple[int, ...]:
        return tuple(
            plan.steam_app_id
            for plan in self.plans
            if plan.needs_generation
        )


def load_owned_ready_game_trait_inventory(
    session: Session,
) -> OwnedReadyGameTraitInventory:
    """Load deterministic trait plans for unique owned IGDB-ready games."""
    with session.begin():
        games = tuple(
            session.scalars(
                select(Game)
                .options(
                    selectinload(Game.metadata_term_links).selectinload(
                        GameIGDBMetadataTerm.term
                    )
                )
                .where(
                    Game.profile_games.any(),
                    Game.igdb_status == "ready",
                )
                .order_by(Game.steam_app_id)
            ).all()
        )

        current_by_id: dict[int, GameTraitDerivation] = {}
        if games:
            current_rows = session.execute(
                select(
                    GameCurrentTraitDerivation.steam_app_id,
                    GameTraitDerivation,
                )
                .join(
                    GameTraitDerivation,
                    GameTraitDerivation.id
                    == GameCurrentTraitDerivation.derivation_id,
                )
                .where(
                    GameCurrentTraitDerivation.steam_app_id.in_(
                        game.steam_app_id for game in games
                    )
                )
            ).all()
            current_by_id = {
                steam_app_id: derivation
                for steam_app_id, derivation in current_rows
            }

        plans: list[GameTraitGenerationPlan] = []
        for game in games:
            facts = build_game_trait_facts(game)
            current = current_by_id.get(game.steam_app_id)
            plans.append(
                GameTraitGenerationPlan(
                    steam_app_id=game.steam_app_id,
                    facts=facts,
                    current_derivation_id=(
                        current.id if current is not None else None
                    ),
                    needs_generation=not is_game_trait_derivation_current(
                        current,
                        facts,
                    ),
                )
            )

    return OwnedReadyGameTraitInventory(plans=tuple(plans))


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
