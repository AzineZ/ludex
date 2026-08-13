from app.gemini.traits.prompt import (
    GAME_TRAIT_DERIVATION_VERSION,
    GAME_TRAIT_MODEL_ID,
    GAME_TRAIT_SCHEMA_VERSION,
)
from app.gemini.traits.contracts import (
    GameTraitFacts,
    calculate_facts_fingerprint,
)
from app.models import GameTraitDerivation


def is_game_trait_derivation_current(
    derivation: GameTraitDerivation | None,
    facts: GameTraitFacts,
) -> bool:
    """Determine whether a successful derivation remains reusable.

    Args:
        derivation: Current successful derivation, when one exists.
        facts: Canonical factual input that would be supplied now.

    Returns:
        True when the schema, rubric, model, and factual fingerprint all match
        current classifier configuration; otherwise, False.
    """
    if derivation is None:
        return False

    return (
        derivation.schema_version == GAME_TRAIT_SCHEMA_VERSION
        and derivation.derivation_version
        == GAME_TRAIT_DERIVATION_VERSION
        and derivation.model_id == GAME_TRAIT_MODEL_ID
        and derivation.facts_fingerprint
        == calculate_facts_fingerprint(facts)
    )
