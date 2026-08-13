from app.gemini.traits.contracts import GameTraitFacts
from app.models import Game


TERM_COLLECTION_FIELDS = {
    "genre": "genres",
    "theme": "themes",
    "keyword": "keywords",
    "game_mode": "game_modes",
}

TIME_TO_BEAT_FIELDS = (
    ("hastily", "time_to_beat_hastily_seconds"),
    ("normally", "time_to_beat_normally_seconds"),
    ("completely", "time_to_beat_completely_seconds"),
)


def _collect_metadata_terms(
    game: Game,
) -> dict[str, tuple[str, ...]]:
    """Collect supported IGDB terms by classifier fact category.

    Args:
        game: Shared game whose loaded metadata links will be mapped.

    Returns:
        Supported term names grouped into canonical fact collections.
    """
    collected: dict[str, list[str]] = {
        field_name: []
        for field_name in TERM_COLLECTION_FIELDS.values()
    }

    for link in game.metadata_term_links:
        term = link.term
        destination = TERM_COLLECTION_FIELDS.get(term.kind)

        if destination is not None:
            collected[destination].append(term.name)

    return {
        field_name: tuple(values)
        for field_name, values in collected.items()
    }


def _build_time_to_beat_facts(game: Game) -> tuple[str, ...]:
    """Format known factual completion estimates without conversion.

    Args:
        game: Shared game containing optional IGDB time estimates.

    Returns:
        Exact known estimates expressed in their stored unit of seconds.
    """
    facts: list[str] = []

    for label, attribute_name in TIME_TO_BEAT_FIELDS:
        seconds = getattr(game, attribute_name)

        if seconds is not None:
            facts.append(f"{label}: {seconds} seconds")

    return tuple(facts)


def _build_release_facts(game: Game) -> tuple[str, ...]:
    """Format known factual release information.

    Args:
        game: Shared game containing an optional first-release timestamp.

    Returns:
        The known first-release calendar date, or an empty tuple.
    """
    if game.first_release_at is None:
        return ()

    return (
        f"first release: {game.first_release_at.date().isoformat()}",
    )


def build_game_trait_facts(game: Game) -> GameTraitFacts:
    """Build canonical classifier facts from one stored shared game.

    Args:
        game: Shared game with its IGDB metadata-term links loaded.

    Returns:
        Canonical factual input containing only supported stored metadata.
    """
    terms = _collect_metadata_terms(game)

    return GameTraitFacts(
        name=game.name,
        summary=game.summary,
        genres=terms["genres"],
        themes=terms["themes"],
        keywords=terms["keywords"],
        game_modes=terms["game_modes"],
        time_to_beat=_build_time_to_beat_facts(game),
        release_information=_build_release_facts(game),
    )
