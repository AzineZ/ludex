from pydantic import ValidationError

from app.game_trait_prompt import (
    GAME_TRAIT_MODEL_ID,
    GAME_TRAIT_SYSTEM_INSTRUCTION,
    build_game_trait_user_prompt,
)
from app.game_trait_schema import build_game_trait_response_schema
from app.game_traits import (
    GameTraitFacts,
    GameTraitResponse,
    TraitEvidenceError,
    validate_response_evidence,
)
from app.gemini_client import GeminiClient


class GameTraitInvalidResponseError(ValueError):
    """Indicate that Gemini returned an unusable trait interpretation."""


def classify_game_traits(
    client: GeminiClient,
    facts: GameTraitFacts,
    *,
    corrective_retry: bool = False,
) -> GameTraitResponse:
    """Classify one game's canonical facts into grounded Ludex traits.

    Args:
        client: Gemini transport used to request structured output.
        facts: Exact canonical factual metadata supplied for classification.
        corrective_retry: Whether to request a fresh correction after an
            invalid prior response.

    Returns:
        A structurally and factually validated game-trait response.

    Raises:
        GameTraitInvalidResponseError: If Gemini's decoded JSON violates the
            response contract or cites facts absent from the supplied input.
        GeminiAPIError: If the underlying Gemini request fails.
    """
    raw_response = client.generate_structured_content(
        model_id=GAME_TRAIT_MODEL_ID,
        system_instruction=GAME_TRAIT_SYSTEM_INSTRUCTION,
        user_prompt=build_game_trait_user_prompt(
            facts,
            corrective_retry=corrective_retry,
        ),
        response_schema=build_game_trait_response_schema(),
    )

    try:
        response = GameTraitResponse.model_validate(raw_response)
        return validate_response_evidence(response, facts)
    except (ValidationError, TraitEvidenceError):
        raise GameTraitInvalidResponseError(
            "Gemini returned an invalid game-trait response."
        ) from None
