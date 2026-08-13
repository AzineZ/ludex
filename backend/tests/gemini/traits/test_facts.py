from datetime import UTC, datetime

from app.gemini.traits.facts import build_game_trait_facts
from app.models import (
    Game,
    GameIGDBMetadataTerm,
    IGDBMetadataTerm,
)


def _add_term(
    game: Game,
    *,
    kind: str,
    igdb_id: int,
    name: str,
) -> None:
    """Attach one factual IGDB term to a test game.

    Args:
        game: Shared game receiving the factual term.
        kind: IGDB term category.
        igdb_id: Stable IGDB term identifier.
        name: Exact factual display name.
    """
    game.metadata_term_links.append(
        GameIGDBMetadataTerm(
            term=IGDBMetadataTerm(
                kind=kind,
                igdb_id=igdb_id,
                name=name,
            )
        )
    )


def test_builds_canonical_facts_from_stored_game_metadata() -> None:
    """Map every supported stored fact into the classifier payload."""
    game = Game(
        steam_app_id=440,
        name="Example Adventure",
        summary="A story-driven adventure.",
        first_release_at=datetime(2025, 6, 15, 18, 30, tzinfo=UTC),
        time_to_beat_hastily_seconds=21_600,
        time_to_beat_normally_seconds=43_200,
        time_to_beat_completely_seconds=72_000,
    )
    _add_term(
        game,
        kind="genre",
        igdb_id=12,
        name="Role-playing",
    )
    _add_term(
        game,
        kind="genre",
        igdb_id=31,
        name="Adventure",
    )
    _add_term(
        game,
        kind="theme",
        igdb_id=17,
        name="Fantasy",
    )
    _add_term(
        game,
        kind="keyword",
        igdb_id=101,
        name="Choices matter",
    )
    _add_term(
        game,
        kind="game_mode",
        igdb_id=1,
        name="Single player",
    )

    facts = build_game_trait_facts(game)

    assert facts.name == "Example Adventure"
    assert facts.summary == "A story-driven adventure."
    assert facts.genres == ("Adventure", "Role-playing")
    assert facts.themes == ("Fantasy",)
    assert facts.keywords == ("Choices matter",)
    assert facts.game_modes == ("Single player",)
    assert facts.time_to_beat == (
        "completely: 72000 seconds",
        "hastily: 21600 seconds",
        "normally: 43200 seconds",
    )
    assert facts.release_information == (
        "first release: 2025-06-15",
    )


def test_preserves_absent_optional_metadata_as_unknown() -> None:
    """Keep missing facts absent instead of inventing replacements."""
    game = Game(
        steam_app_id=440,
        name="Unknown Metadata Game",
        summary=None,
        first_release_at=None,
        time_to_beat_hastily_seconds=None,
        time_to_beat_normally_seconds=None,
        time_to_beat_completely_seconds=None,
    )

    facts = build_game_trait_facts(game)

    assert facts.name == "Unknown Metadata Game"
    assert facts.summary is None
    assert facts.genres == ()
    assert facts.themes == ()
    assert facts.keywords == ()
    assert facts.game_modes == ()
    assert facts.time_to_beat == ()
    assert facts.release_information == ()


def test_ignores_unsupported_metadata_term_kind() -> None:
    """Exclude term categories that are not classifier evidence fields."""
    game = Game(
        steam_app_id=440,
        name="Example Adventure",
    )
    _add_term(
        game,
        kind="unsupported",
        igdb_id=999,
        name="Model should never receive this",
    )

    facts = build_game_trait_facts(game)

    assert facts.genres == ()
    assert facts.themes == ()
    assert facts.keywords == ()
    assert facts.game_modes == ()
