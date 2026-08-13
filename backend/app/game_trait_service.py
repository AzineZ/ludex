from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.game_trait_facts import build_game_trait_facts
from app.game_trait_generation import generate_game_traits
from app.game_traits import GameTraitResponse
from app.gemini_client import GeminiClient
from app.models import (
    Game,
    GameIGDBMetadataTerm,
)


def generate_saved_game_traits(
    session: Session,
    client: GeminiClient,
    *,
    steam_app_id: int,
    operation_id: str,
) -> GameTraitResponse:
    """Load one saved game's facts, then generate its derived traits.

    The factual database read completes before Gemini is contacted. Generation
    and successful persistence therefore do not hold a transaction open during
    external network work.

    Args:
        session: Database session used for factual loading and persistence.
        client: Configured backend-only Gemini transport.
        steam_app_id: Shared Steam game to classify.
        operation_id: Identifier shared by every model attempt in this
            classification operation.

    Returns:
        The validated response persisted as the current derivation.

    Raises:
        ValueError: If the Steam game is not saved locally.
        GameTraitInvalidResponseError: If corrective validation also fails.
        GeminiAPIError: If Gemini fails or rejects the request.
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
                "Trait generation must reference a saved Steam game."
            )

        facts = build_game_trait_facts(game)

    return generate_game_traits(
        session,
        client,
        steam_app_id=steam_app_id,
        facts=facts,
        operation_id=operation_id,
    )
