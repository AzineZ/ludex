from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Game,
    GameIGDBMetadataTerm,
    IGDBMetadataTerm,
    ProfileGame,
)
from app.recommendations.candidate_facts import CandidateFacts
from app.recommendations.factual_scoring import FacetKind

_FACET_FIELD_BY_KIND = {
    FacetKind.GENRE: "genre_ids",
    FacetKind.THEME: "theme_ids",
    FacetKind.KEYWORD: "keyword_ids",
    FacetKind.GAME_MODE: "game_mode_ids",
}


def load_candidate_facts(
    session: Session,
    profile_id: int,
    *,
    active_facet_kinds: frozenset[FacetKind],
) -> tuple[CandidateFacts, ...]:
    """Project one profile's cached owned library for factual scoring."""
    active_kinds = tuple(
        kind
        for kind in _FACET_FIELD_BY_KIND
        if kind in active_facet_kinds
    )
    game_rows = session.execute(
        select(
            Game.steam_app_id,
            ProfileGame.playtime_minutes,
            Game.time_to_beat_normally_seconds,
            Game.igdb_status,
        )
        .join(
            ProfileGame,
            ProfileGame.steam_app_id == Game.steam_app_id,
        )
        .where(ProfileGame.profile_id == profile_id)
        .order_by(Game.steam_app_id)
        .execution_options(autoflush=False)
    ).all()

    if not game_rows:
        return ()

    steam_app_ids = tuple(row.steam_app_id for row in game_rows)
    term_ids_by_game_and_kind: dict[
        tuple[int, FacetKind],
        list[int],
    ] = {}

    if active_kinds:
        term_rows = session.execute(
            select(
                GameIGDBMetadataTerm.steam_app_id,
                IGDBMetadataTerm.kind,
                IGDBMetadataTerm.igdb_id,
            )
            .join(
                IGDBMetadataTerm,
                (
                    IGDBMetadataTerm.id
                    == GameIGDBMetadataTerm.term_id
                ),
            )
            .where(
                GameIGDBMetadataTerm.steam_app_id.in_(
                    steam_app_ids
                ),
                IGDBMetadataTerm.kind.in_(
                    tuple(kind.value for kind in active_kinds)
                ),
            )
            .order_by(
                GameIGDBMetadataTerm.steam_app_id,
                IGDBMetadataTerm.kind,
                IGDBMetadataTerm.igdb_id,
            )
            .execution_options(autoflush=False)
        ).all()

        for row in term_rows:
            key = (
                row.steam_app_id,
                FacetKind(row.kind),
            )
            term_ids_by_game_and_kind.setdefault(key, []).append(
                row.igdb_id
            )

    candidates: list[CandidateFacts] = []
    for row in game_rows:
        facet_values: dict[str, tuple[int, ...] | None] = {
            field: None for field in _FACET_FIELD_BY_KIND.values()
        }

        if row.igdb_status == "ready":
            for kind in active_kinds:
                field = _FACET_FIELD_BY_KIND[kind]
                facet_values[field] = tuple(
                    term_ids_by_game_and_kind.get(
                        (row.steam_app_id, kind),
                        (),
                    )
                )

        candidates.append(
            CandidateFacts(
                steam_app_id=row.steam_app_id,
                owned_by_selected_profile=True,
                total_playtime_minutes=row.playtime_minutes,
                normal_completion_seconds=(
                    row.time_to_beat_normally_seconds
                ),
                genre_ids=facet_values["genre_ids"],
                theme_ids=facet_values["theme_ids"],
                keyword_ids=facet_values["keyword_ids"],
                game_mode_ids=facet_values["game_mode_ids"],
            )
        )

    return tuple(candidates)
