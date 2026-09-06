from dataclasses import dataclass

from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from app.integrations.igdb.images import igdb_cover_url
from app.models import Game, IGDBMetadataTerm, ProfileGame
from app.recommendations.factual_scoring import FacetKind
from app.recommendations.final_results import (
    FINAL_RECOMMENDATION_LIMIT,
    CandidatePresentationFacts,
    FacetLabel,
)

_FACET_KIND_ORDER = {
    FacetKind.GENRE: 0,
    FacetKind.THEME: 1,
    FacetKind.KEYWORD: 2,
    FacetKind.GAME_MODE: 3,
}


@dataclass(frozen=True)
class FinalResultPresentationProjection:
    """Hold bounded cached presentation facts for final assembly."""

    presentations: tuple[CandidatePresentationFacts, ...]
    facet_labels: tuple[FacetLabel, ...]


def load_final_result_presentation(
    session: Session,
    profile_id: int,
    *,
    selected_steam_app_ids: tuple[int, ...],
    facet_identities: frozenset[tuple[FacetKind, int]],
) -> FinalResultPresentationProjection:
    """Project cached final-result facts through at most two selects."""
    if len(set(selected_steam_app_ids)) != len(selected_steam_app_ids):
        raise ValueError("selected Steam App IDs must be unique")
    if len(selected_steam_app_ids) > FINAL_RECOMMENDATION_LIMIT:
        raise ValueError("select at most 6 Steam App IDs")

    presentations: tuple[CandidatePresentationFacts, ...] = ()
    if selected_steam_app_ids:
        game_rows = session.execute(
            select(
                Game.steam_app_id,
                Game.name,
                Game.cover_image_id,
                ProfileGame.playtime_minutes,
                Game.time_to_beat_normally_seconds,
            )
            .join(
                ProfileGame,
                ProfileGame.steam_app_id == Game.steam_app_id,
            )
            .where(
                ProfileGame.profile_id == profile_id,
                Game.steam_app_id.in_(selected_steam_app_ids),
            )
            .order_by(Game.steam_app_id)
            .execution_options(autoflush=False)
        ).all()
        presentations = tuple(
            CandidatePresentationFacts(
                steam_app_id=row.steam_app_id,
                title=row.name,
                cover_url=igdb_cover_url(row.cover_image_id),
                profile_playtime_minutes=row.playtime_minutes,
                normal_completion_seconds=(
                    row.time_to_beat_normally_seconds
                ),
            )
            for row in game_rows
        )

    facet_labels: tuple[FacetLabel, ...] = ()
    if facet_identities:
        identity_values = tuple(
            (kind.value, igdb_id)
            for kind, igdb_id in facet_identities
        )
        term_rows = session.execute(
            select(
                IGDBMetadataTerm.kind,
                IGDBMetadataTerm.igdb_id,
                IGDBMetadataTerm.name,
            )
            .where(
                tuple_(
                    IGDBMetadataTerm.kind,
                    IGDBMetadataTerm.igdb_id,
                ).in_(identity_values)
            )
            .execution_options(autoflush=False)
        ).all()
        facet_labels = tuple(
            sorted(
                (
                    FacetLabel(
                        facet_kind=FacetKind(row.kind),
                        facet_igdb_id=row.igdb_id,
                        name=row.name,
                    )
                    for row in term_rows
                ),
                key=lambda label: (
                    _FACET_KIND_ORDER[label.facet_kind],
                    label.facet_igdb_id,
                ),
            )
        )

    return FinalResultPresentationProjection(
        presentations=presentations,
        facet_labels=facet_labels,
    )
