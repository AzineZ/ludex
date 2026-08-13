from sqlalchemy.orm import Session

from app.gemini.traits.generation import generate_game_traits
from app.gemini.traits.planning import (
    load_game_trait_generation_plan,
)
from app.gemini.traits.contracts import GameTraitResponse
from app.gemini.client import GeminiClient


def generate_saved_game_traits(
    session: Session,
    client: GeminiClient,
    *,
    steam_app_id: int,
    operation_id: str,
) -> GameTraitResponse | None:
    """Generate traits only when one saved game's derivation is stale.

    The generation plan loads canonical facts and closes its read transaction
    before this function can contact Gemini. A current derivation is reused
    without creating a model call or attempt record.

    Args:
        session: Database session used for planning and persistence.
        client: Configured backend-only Gemini transport.
        steam_app_id: Shared Steam game to inspect and possibly classify.
        operation_id: Identifier shared by every model attempt in this
            classification operation.

    Returns:
        The newly validated and persisted response, or None when the existing
        current derivation remains reusable.

    Raises:
        ValueError: If the Steam game is not saved locally.
        GameTraitInvalidResponseError: If corrective validation also fails.
        GeminiAPIError: If Gemini fails or rejects the request.
    """
    plan = load_game_trait_generation_plan(
        session,
        steam_app_id,
    )

    if not plan.needs_generation:
        return None

    return generate_game_traits(
        session,
        client,
        steam_app_id=steam_app_id,
        facts=plan.facts,
        operation_id=operation_id,
    )
