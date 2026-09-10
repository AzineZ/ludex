from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.gemini.prompt.contracts import PromptConceptKind
from app.gemini.prompt.scoring import (
    MoodValue,
    NumericTraitValue,
    PromptCandidate,
    PromptCandidateTraits,
)
from app.gemini.prompt.validation import ValidatedPromptConcept
from app.gemini.traits.facts import build_game_trait_facts
from app.gemini.traits.freshness import is_game_trait_derivation_current
from app.models import (
    Game,
    GameCurrentTraitDerivation,
    GameIGDBMetadataTerm,
    GameTraitDerivation,
    GameTraitMood,
)
from app.recommendations.candidate_reads import load_candidate_facts
from app.recommendations.factual_scoring import FacetKind


_FACET_KIND_BY_PROMPT_KIND = {
    PromptConceptKind.GENRE: FacetKind.GENRE,
    PromptConceptKind.THEME: FacetKind.THEME,
    PromptConceptKind.KEYWORD: FacetKind.KEYWORD,
    PromptConceptKind.GAME_MODE: FacetKind.GAME_MODE,
}

_NUMERIC_TRAIT_NAMES = (
    "story_focus",
    "combat_intensity",
    "difficulty",
    "pacing",
    "session_friendliness",
    "exploration_focus",
)


def _active_facet_kinds(
    concepts: tuple[ValidatedPromptConcept, ...],
) -> frozenset[FacetKind]:
    return frozenset(
        _FACET_KIND_BY_PROMPT_KIND[concept.definition.kind]
        for concept in concepts
        if concept.definition.kind in _FACET_KIND_BY_PROMPT_KIND
    )


def _traits_from_derivation(
    derivation: GameTraitDerivation,
    moods: tuple[GameTraitMood, ...],
) -> PromptCandidateTraits:
    numeric: list[tuple[str, NumericTraitValue | None]] = []
    for name in _NUMERIC_TRAIT_NAMES:
        value = getattr(derivation, f"{name}_value")
        confidence = Decimal(getattr(derivation, f"{name}_confidence"))
        numeric.append(
            (
                name,
                None
                if value is None
                else NumericTraitValue(value, confidence),
            )
        )
    return PromptCandidateTraits(
        numeric_traits=tuple(numeric),
        moods=tuple(
            MoodValue(mood.label, Decimal(mood.confidence))
            for mood in sorted(moods, key=lambda item: item.label)
        ),
    )


def load_prompt_candidates(
    session: Session,
    *,
    profile_id: int,
    concepts: tuple[ValidatedPromptConcept, ...],
) -> tuple[PromptCandidate, ...]:
    """Project owned factual candidates plus only fresh cached traits."""
    factual = load_candidate_facts(
        session,
        profile_id,
        active_facet_kinds=_active_facet_kinds(concepts),
    )
    if not factual:
        return ()

    factual_by_id = {item.steam_app_id: item for item in factual}
    games = tuple(
        session.scalars(
            select(Game)
            .options(
                selectinload(Game.metadata_term_links).selectinload(
                    GameIGDBMetadataTerm.term
                )
            )
            .where(Game.steam_app_id.in_(factual_by_id))
        ).all()
    )
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
        .where(GameCurrentTraitDerivation.steam_app_id.in_(factual_by_id))
    ).all()
    current_by_id = {
        steam_app_id: derivation
        for steam_app_id, derivation in current_rows
    }
    fresh_by_id: dict[int, GameTraitDerivation] = {}
    for game in games:
        derivation = current_by_id.get(game.steam_app_id)
        if is_game_trait_derivation_current(
            derivation,
            build_game_trait_facts(game),
        ):
            fresh_by_id[game.steam_app_id] = derivation

    moods_by_derivation: dict[int, list[GameTraitMood]] = {}
    if fresh_by_id:
        for mood in session.scalars(
            select(GameTraitMood).where(
                GameTraitMood.derivation_id.in_(
                    derivation.id for derivation in fresh_by_id.values()
                )
            )
        ):
            moods_by_derivation.setdefault(mood.derivation_id, []).append(mood)

    return tuple(
        PromptCandidate(
            facts=item,
            traits=(
                _traits_from_derivation(
                    fresh_by_id[item.steam_app_id],
                    tuple(
                        moods_by_derivation.get(
                            fresh_by_id[item.steam_app_id].id,
                            (),
                        )
                    ),
                )
                if item.steam_app_id in fresh_by_id
                else None
            ),
        )
        for item in factual
    )
