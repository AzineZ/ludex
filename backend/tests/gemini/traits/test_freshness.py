from datetime import UTC, datetime

import pytest

from app.gemini.traits.freshness import (
    is_game_trait_derivation_current,
)
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


def _facts() -> GameTraitFacts:
    """Return canonical facts for freshness tests."""
    return GameTraitFacts(
        name="Example Adventure",
        summary="A story-driven adventure.",
        genres=("Adventure",),
        themes=(),
        keywords=(),
        game_modes=("Single player",),
        time_to_beat=(),
        release_information=(),
    )


def _derivation(
    facts: GameTraitFacts,
) -> GameTraitDerivation:
    """Return a derivation matching current classifier provenance."""
    return GameTraitDerivation(
        steam_app_id=440,
        schema_version=GAME_TRAIT_SCHEMA_VERSION,
        derivation_version=GAME_TRAIT_DERIVATION_VERSION,
        model_id=GAME_TRAIT_MODEL_ID,
        facts_fingerprint=calculate_facts_fingerprint(facts),
        derived_at=datetime(2026, 8, 12, tzinfo=UTC),
        story_focus_value=None,
        story_focus_confidence=0,
        combat_intensity_value=None,
        combat_intensity_confidence=0,
        difficulty_value=None,
        difficulty_confidence=0,
        pacing_value=None,
        pacing_confidence=0,
        session_friendliness_value=None,
        session_friendliness_confidence=0,
        exploration_focus_value=None,
        exploration_focus_confidence=0,
    )


def test_current_derivation_reuses_unchanged_facts() -> None:
    """Reuse a derivation whose complete provenance still matches."""
    facts = _facts()

    assert is_game_trait_derivation_current(
        _derivation(facts),
        facts,
    ) is True


def test_missing_derivation_requires_generation() -> None:
    """Require initial generation when no successful result exists."""
    assert is_game_trait_derivation_current(
        None,
        _facts(),
    ) is False


@pytest.mark.parametrize(
    ("field_name", "stale_value"),
    [
        ("schema_version", "older-schema"),
        ("derivation_version", "older-prompt"),
        ("model_id", "different-model"),
        ("facts_fingerprint", "a" * 64),
    ],
)
def test_changed_provenance_requires_regeneration(
    field_name: str,
    stale_value: str,
) -> None:
    """Reject a current pointer whose trusted provenance is stale."""
    facts = _facts()
    derivation = _derivation(facts)
    setattr(derivation, field_name, stale_value)

    assert is_game_trait_derivation_current(
        derivation,
        facts,
    ) is False


def test_changed_relevant_facts_require_regeneration() -> None:
    """Regenerate when canonical factual classifier input changes."""
    original_facts = _facts()
    changed_facts = original_facts.model_copy(
        update={"themes": ("Fantasy",)}
    )

    assert is_game_trait_derivation_current(
        _derivation(original_facts),
        changed_facts,
    ) is False
