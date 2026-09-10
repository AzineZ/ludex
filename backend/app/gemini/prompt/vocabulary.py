from sqlalchemy import select
from sqlalchemy.orm import Session

from app.gemini.prompt.contracts import (
    MAX_PROMPT_VOCABULARY_ENTRIES,
    PromptConceptKind,
    PromptVocabulary,
    PromptVocabularyEntry,
)
from app.models import GameIGDBMetadataTerm, IGDBMetadataTerm, ProfileGame


PROMPT_VOCABULARY_VERSION = "prompt-vocabulary-v1"

NUMERIC_TRAIT_LABELS = {
    "story_focus": "Story focused",
    "combat_intensity": "Combat intensity",
    "difficulty": "Difficulty",
    "pacing": "Pacing",
    "session_friendliness": "Short-session friendly",
    "exploration_focus": "Exploration focused",
}
MOOD_LABELS = {
    "relaxing": "Relaxing",
    "tense": "Tense",
    "emotional": "Emotional",
    "humorous": "Humorous",
    "dark": "Dark",
}

# Keep this deliberately broad and stable. Only names present in a selected
# profile's cached IGDB terms enter its runtime vocabulary.
CURATED_KEYWORD_NAMES = frozenset(
    {
        "2d",
        "3d",
        "aliens",
        "alternate history",
        "choices matter",
        "co-op",
        "comedy",
        "crafting",
        "detective",
        "dinosaurs",
        "dystopian",
        "exploration",
        "family friendly",
        "fantasy",
        "farming",
        "female protagonist",
        "first person",
        "historical",
        "horror",
        "investigation",
        "magic",
        "management",
        "medieval",
        "multiplayer",
        "mystery",
        "open world",
        "parkour",
        "pirates",
        "post-apocalyptic",
        "puzzle",
        "resource management",
        "robots",
        "science fiction",
        "space",
        "stealth",
        "survival",
        "third person",
        "time travel",
        "turn-based",
        "vampires",
        "war",
        "zombies",
    }
)

_FACTUAL_KIND_ORDER = {
    "genre": 0,
    "theme": 1,
    "game_mode": 2,
    "keyword": 3,
}


def _subjective_entries() -> tuple[PromptVocabularyEntry, ...]:
    return tuple(
        PromptVocabularyEntry(
            concept_id=f"trait:{name}",
            kind=PromptConceptKind.NUMERIC_TRAIT,
            label=label,
        )
        for name, label in NUMERIC_TRAIT_LABELS.items()
    ) + tuple(
        PromptVocabularyEntry(
            concept_id=f"mood:{name}",
            kind=PromptConceptKind.MOOD,
            label=label,
        )
        for name, label in MOOD_LABELS.items()
    )


def build_prompt_vocabulary(
    session: Session,
    *,
    profile_id: int,
) -> PromptVocabulary:
    """Build one deterministic, profile-scoped concept vocabulary."""
    rows = session.execute(
        select(
            IGDBMetadataTerm.kind,
            IGDBMetadataTerm.igdb_id,
            IGDBMetadataTerm.name,
        )
        .join(
            GameIGDBMetadataTerm,
            GameIGDBMetadataTerm.term_id == IGDBMetadataTerm.id,
        )
        .join(
            ProfileGame,
            ProfileGame.steam_app_id
            == GameIGDBMetadataTerm.steam_app_id,
        )
        .where(ProfileGame.profile_id == profile_id)
        .distinct()
    ).all()

    factual: list[PromptVocabularyEntry] = []
    for kind, igdb_id, name in sorted(
        rows,
        key=lambda row: (
            _FACTUAL_KIND_ORDER[row.kind],
            row.igdb_id,
        ),
    ):
        if kind == "keyword" and name.casefold() not in CURATED_KEYWORD_NAMES:
            continue
        factual.append(
            PromptVocabularyEntry(
                concept_id=f"{kind}:{igdb_id}",
                kind=PromptConceptKind(kind),
                label=name,
                igdb_id=igdb_id,
            )
        )

    subjective = _subjective_entries()
    non_keyword_count = sum(
        entry.kind is not PromptConceptKind.KEYWORD for entry in factual
    )
    required_count = non_keyword_count + len(subjective)
    if required_count > MAX_PROMPT_VOCABULARY_ENTRIES:
        raise ValueError(
            "The required prompt vocabulary exceeds its safe size limit."
        )

    keyword_capacity = MAX_PROMPT_VOCABULARY_ENTRIES - required_count
    non_keywords = tuple(
        entry
        for entry in factual
        if entry.kind is not PromptConceptKind.KEYWORD
    )
    keywords = tuple(
        entry
        for entry in factual
        if entry.kind is PromptConceptKind.KEYWORD
    )[:keyword_capacity]
    return PromptVocabulary(
        version=PROMPT_VOCABULARY_VERSION,
        entries=non_keywords + keywords + subjective,
    )
