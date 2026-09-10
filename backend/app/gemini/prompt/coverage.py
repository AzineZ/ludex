from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.gemini.traits.facts import build_game_trait_facts
from app.gemini.traits.freshness import is_game_trait_derivation_current
from app.models import (
    Game,
    GameCurrentTraitDerivation,
    GameIGDBMetadataTerm,
    GameTraitDerivation,
    ProfileGame,
)


SUBJECTIVE_COVERAGE_THRESHOLD_BASIS_POINTS = 9_000


@dataclass(frozen=True)
class PromptTraitCoverage:
    ready_game_count: int
    current_trait_game_count: int
    coverage_basis_points: int
    subjective_available: bool


def get_prompt_trait_coverage(
    session: Session,
    *,
    profile_id: int,
) -> PromptTraitCoverage:
    """Measure current trait coverage for one owned IGDB-ready library."""
    games = tuple(
        session.scalars(
            select(Game)
            .join(ProfileGame)
            .options(
                selectinload(Game.metadata_term_links).selectinload(
                    GameIGDBMetadataTerm.term
                )
            )
            .where(
                ProfileGame.profile_id == profile_id,
                Game.igdb_status == "ready",
            )
            .order_by(Game.steam_app_id)
        ).all()
    )
    ready_count = len(games)
    if not games:
        return PromptTraitCoverage(0, 0, 0, False)

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
    current_count = sum(
        is_game_trait_derivation_current(
            current_by_id.get(game.steam_app_id),
            build_game_trait_facts(game),
        )
        for game in games
    )
    basis_points = (current_count * 10_000) // ready_count
    return PromptTraitCoverage(
        ready_game_count=ready_count,
        current_trait_game_count=current_count,
        coverage_basis_points=basis_points,
        subjective_available=(
            basis_points >= SUBJECTIVE_COVERAGE_THRESHOLD_BASIS_POINTS
        ),
    )
