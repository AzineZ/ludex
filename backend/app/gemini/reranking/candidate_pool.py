from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.gemini.reranking.contracts import (
    MAX_RERANK_CANDIDATES,
    MAX_RERANK_SUMMARY_CHARACTERS,
    RerankCandidate,
    RerankFilters,
    RerankRequest,
)
from app.gemini.reranking.projection import (
    project_rerank_candidates,
    select_product_projection,
)
from app.integrations.igdb.images import igdb_cover_url
from app.models import (
    Game,
    GameIGDBMetadataTerm,
    IGDBMetadataTerm,
    ProfileGame,
)
from app.recommendations.candidate_facts import CandidateFacts
from app.recommendations.candidate_reads import load_candidate_facts
from app.recommendations.contracts import PlayStatus
from app.recommendations.eligibility import evaluate_candidate_eligibility
from app.recommendations.factual_scoring import FacetKind


class RerankCandidatePoolState(StrEnum):
    READY = "ready"
    EMPTY = "empty"
    NEEDS_REFINEMENT = "needs_refinement"


class RerankGenreUnavailableError(ValueError):
    """Indicate that the selected genre is unavailable to this profile."""

    field = "selected_genre_id"


class RerankFilterUnavailableError(ValueError):
    """Indicate that a submitted filter is unavailable in the genre pool."""

    def __init__(self, field: str) -> None:
        self.field = field
        super().__init__("The selected filter is not available for this genre.")


@dataclass(frozen=True)
class RerankGenreOption:
    igdb_id: int
    name: str
    eligible_count: int


@dataclass(frozen=True)
class RerankFacetOption:
    igdb_id: int
    name: str
    eligible_count: int


@dataclass(frozen=True)
class RerankFilterOptions:
    eligible_count: int
    themes: tuple[RerankFacetOption, ...]
    game_modes: tuple[RerankFacetOption, ...]

    def __post_init__(self) -> None:
        if self.eligible_count < 0:
            raise ValueError("Eligible count cannot be negative.")


@dataclass(frozen=True)
class RerankCandidatePresentation:
    steam_app_id: int
    title: str
    cover_url: str | None
    profile_playtime_minutes: int
    normal_completion_seconds: int | None


@dataclass(frozen=True)
class RerankCandidatePool:
    state: RerankCandidatePoolState
    eligible_count: int
    request: RerankRequest | None = None
    presentations: tuple[RerankCandidatePresentation, ...] = ()

    def __post_init__(self) -> None:
        if self.eligible_count < 0:
            raise ValueError("Eligible count cannot be negative.")
        if self.state is RerankCandidatePoolState.READY:
            if (
                self.request is None
                or not 1 <= self.eligible_count <= MAX_RERANK_CANDIDATES
            ):
                raise ValueError("Ready pools require one bounded request.")
            request_ids = tuple(
                candidate.steam_app_id for candidate in self.request.candidates
            )
            presentation_ids = tuple(
                item.steam_app_id for item in self.presentations
            )
            if request_ids != presentation_ids:
                raise ValueError("Presentation facts must match the snapshot.")
        elif self.request is not None or self.presentations:
            raise ValueError("Stopped pools cannot contain provider data.")


def list_available_rerank_genres(
    session: Session,
    *,
    profile_id: int,
) -> tuple[RerankGenreOption, ...]:
    """List genres present on this profile's cached, IGDB-ready games."""
    rows = session.execute(
        select(
            IGDBMetadataTerm.igdb_id,
            IGDBMetadataTerm.name,
            func.count(Game.steam_app_id.distinct()).label("eligible_count"),
        )
        .join(
            GameIGDBMetadataTerm,
            GameIGDBMetadataTerm.term_id == IGDBMetadataTerm.id,
        )
        .join(Game, Game.steam_app_id == GameIGDBMetadataTerm.steam_app_id)
        .join(ProfileGame, ProfileGame.steam_app_id == Game.steam_app_id)
        .where(
            ProfileGame.profile_id == profile_id,
            Game.igdb_status == "ready",
            IGDBMetadataTerm.kind == FacetKind.GENRE.value,
        )
        .group_by(IGDBMetadataTerm.igdb_id, IGDBMetadataTerm.name)
        .order_by(func.lower(IGDBMetadataTerm.name), IGDBMetadataTerm.igdb_id)
        .execution_options(autoflush=False)
    ).all()
    return tuple(
        RerankGenreOption(
            igdb_id=row.igdb_id,
            name=row.name,
            eligible_count=row.eligible_count,
        )
        for row in rows
    )


def _matches_any(values: tuple[int, ...] | None, selected: tuple[int, ...]) -> bool:
    return not selected or bool(set(values or ()).intersection(selected))


def list_rerank_filter_options(
    session: Session,
    *,
    profile_id: int,
    selected_genre_id: int,
    play_status: PlayStatus,
    maximum_completion_minutes: int | None,
    theme_ids: tuple[int, ...] = (),
    game_mode_ids: tuple[int, ...] = (),
    session_excluded_steam_app_ids: frozenset[int] = frozenset(),
) -> RerankFilterOptions:
    """List refinements and count the current provider-free candidate pool."""
    genres = list_available_rerank_genres(session, profile_id=profile_id)
    if not any(item.igdb_id == selected_genre_id for item in genres):
        raise RerankGenreUnavailableError(
            "The selected genre is not available for this library."
        )
    facts = load_candidate_facts(
        session,
        profile_id,
        active_facet_kinds=frozenset(
            {FacetKind.GENRE, FacetKind.THEME, FacetKind.GAME_MODE}
        ),
    )
    selected_filters = RerankFilters(
        play_status=play_status,
        maximum_completion_minutes=maximum_completion_minutes,
        theme_ids=theme_ids,
        game_mode_ids=game_mode_ids,
    )
    _validate_filter_ids(
        facts,
        selected_genre_id=selected_genre_id,
        filters=selected_filters,
    )
    eligible = _eligible_facts(
        facts,
        selected_genre_id=selected_genre_id,
        filters=RerankFilters(
            play_status=play_status,
            maximum_completion_minutes=maximum_completion_minutes,
        ),
        session_excluded_steam_app_ids=session_excluded_steam_app_ids,
    )
    current_eligible_count = sum(
        1
        for item in eligible
        if _matches_any(item.theme_ids, selected_filters.theme_ids)
        and _matches_any(item.game_mode_ids, selected_filters.game_mode_ids)
    )
    counts: dict[tuple[FacetKind, int], int] = {}
    for item in eligible:
        for kind, identities in (
            (FacetKind.THEME, item.theme_ids or ()),
            (FacetKind.GAME_MODE, item.game_mode_ids or ()),
        ):
            for identity in identities:
                key = (kind, identity)
                counts[key] = counts.get(key, 0) + 1

    if not counts:
        return RerankFilterOptions(
            eligible_count=current_eligible_count,
            themes=(),
            game_modes=(),
        )
    rows = session.execute(
        select(
            IGDBMetadataTerm.kind,
            IGDBMetadataTerm.igdb_id,
            IGDBMetadataTerm.name,
        ).where(
            IGDBMetadataTerm.kind.in_(
                (FacetKind.THEME.value, FacetKind.GAME_MODE.value)
            ),
            IGDBMetadataTerm.igdb_id.in_(
                tuple(identity for _, identity in counts)
            ),
        )
    ).all()
    options: dict[FacetKind, list[RerankFacetOption]] = {
        FacetKind.THEME: [],
        FacetKind.GAME_MODE: [],
    }
    for row in rows:
        kind = FacetKind(row.kind)
        count = counts.get((kind, row.igdb_id))
        if count is not None:
            options[kind].append(
                RerankFacetOption(
                    igdb_id=row.igdb_id,
                    name=row.name,
                    eligible_count=count,
                )
            )
    for values in options.values():
        values.sort(key=lambda item: (item.name.casefold(), item.igdb_id))
    return RerankFilterOptions(
        eligible_count=current_eligible_count,
        themes=tuple(options[FacetKind.THEME]),
        game_modes=tuple(options[FacetKind.GAME_MODE]),
    )


def _eligible_facts(
    facts: tuple[CandidateFacts, ...],
    *,
    selected_genre_id: int,
    filters: RerankFilters,
    session_excluded_steam_app_ids: frozenset[int],
) -> tuple[CandidateFacts, ...]:
    eligible: list[CandidateFacts] = []
    for candidate in facts:
        if selected_genre_id not in (candidate.genre_ids or ()):
            continue
        if not _matches_any(candidate.theme_ids, filters.theme_ids):
            continue
        if not _matches_any(candidate.game_mode_ids, filters.game_mode_ids):
            continue
        decision = evaluate_candidate_eligibility(
            candidate,
            reference_steam_app_ids=frozenset(),
            session_excluded_steam_app_ids=session_excluded_steam_app_ids,
            play_status=filters.play_status,
            maximum_completion_minutes=filters.maximum_completion_minutes,
        )
        if decision.eligible:
            eligible.append(candidate)
    return tuple(sorted(eligible, key=lambda item: item.steam_app_id))


def _validate_filter_ids(
    facts: tuple[CandidateFacts, ...],
    *,
    selected_genre_id: int,
    filters: RerankFilters,
) -> None:
    genre_facts = tuple(
        item
        for item in facts
        if selected_genre_id in (item.genre_ids or ())
    )
    checks = (
        ("filters.theme_ids", filters.theme_ids, "theme_ids"),
        ("filters.game_mode_ids", filters.game_mode_ids, "game_mode_ids"),
    )
    for field, selected_ids, attribute in checks:
        available = {
            identity
            for item in genre_facts
            for identity in (getattr(item, attribute) or ())
        }
        if not set(selected_ids) <= available:
            raise RerankFilterUnavailableError(field)


def _bounded_text(value: str | None, maximum: int) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.split())
    return normalized[:maximum] or None


def _bounded_labels(
    labels: list[tuple[int, str]],
    maximum: int,
    *,
    required_id: int | None = None,
) -> tuple[str, ...]:
    ordered = sorted(labels, key=lambda item: (item[0], item[1].casefold()))
    if required_id is not None:
        ordered.sort(key=lambda item: item[0] != required_id)
    bounded: list[str] = []
    for _, name in ordered:
        normalized = " ".join(name.split())[:100]
        if normalized and normalized not in bounded:
            bounded.append(normalized)
        if len(bounded) == maximum:
            break
    return tuple(bounded)


def load_rerank_snapshot_data(
    session: Session,
    *,
    profile_id: int,
    selected_genre_id: int,
    eligible: tuple[CandidateFacts, ...],
) -> tuple[
    tuple[RerankCandidate, ...],
    tuple[RerankCandidatePresentation, ...],
]:
    """Load the bounded provider projection for preselected cached games."""
    eligible_ids = tuple(item.steam_app_id for item in eligible)
    rows = session.execute(
        select(
            Game.steam_app_id,
            Game.name,
            Game.summary,
            Game.cover_image_id,
            Game.time_to_beat_normally_seconds,
            ProfileGame.playtime_minutes,
        )
        .join(ProfileGame, ProfileGame.steam_app_id == Game.steam_app_id)
        .where(
            ProfileGame.profile_id == profile_id,
            Game.steam_app_id.in_(eligible_ids),
        )
        .order_by(Game.steam_app_id)
        .execution_options(autoflush=False)
    ).all()
    term_rows = session.execute(
        select(
            GameIGDBMetadataTerm.steam_app_id,
            IGDBMetadataTerm.kind,
            IGDBMetadataTerm.igdb_id,
            IGDBMetadataTerm.name,
        )
        .join(
            IGDBMetadataTerm,
            IGDBMetadataTerm.id == GameIGDBMetadataTerm.term_id,
        )
        .where(GameIGDBMetadataTerm.steam_app_id.in_(eligible_ids))
        .order_by(
            GameIGDBMetadataTerm.steam_app_id,
            IGDBMetadataTerm.kind,
            IGDBMetadataTerm.igdb_id,
        )
        .execution_options(autoflush=False)
    ).all()
    labels: dict[tuple[int, str], list[tuple[int, str]]] = {}
    for row in term_rows:
        labels.setdefault((row.steam_app_id, row.kind), []).append(
            (row.igdb_id, row.name)
        )

    candidates = tuple(
        RerankCandidate(
            steam_app_id=row.steam_app_id,
            title=row.name,
            summary=_bounded_text(row.summary, MAX_RERANK_SUMMARY_CHARACTERS),
            genres=_bounded_labels(
                labels.get((row.steam_app_id, FacetKind.GENRE.value), []),
                8,
                required_id=selected_genre_id,
            ),
            themes=_bounded_labels(
                labels.get((row.steam_app_id, FacetKind.THEME.value), []), 8
            ),
            keywords=_bounded_labels(
                labels.get((row.steam_app_id, FacetKind.KEYWORD.value), []), 12
            ),
            game_modes=_bounded_labels(
                labels.get((row.steam_app_id, FacetKind.GAME_MODE.value), []), 8
            ),
            profile_playtime_minutes=row.playtime_minutes,
            normal_completion_minutes=(
                None
                if row.time_to_beat_normally_seconds is None
                else (row.time_to_beat_normally_seconds + 59) // 60
            ),
        )
        for row in rows
    )
    presentations = tuple(
        RerankCandidatePresentation(
            steam_app_id=row.steam_app_id,
            title=row.name,
            cover_url=igdb_cover_url(row.cover_image_id),
            profile_playtime_minutes=row.playtime_minutes,
            normal_completion_seconds=row.time_to_beat_normally_seconds,
        )
        for row in rows
    )
    return candidates, presentations


def _load_snapshot(
    session: Session,
    *,
    profile_id: int,
    prompt: str,
    selected_genre_id: int,
    selected_genre_name: str,
    filters: RerankFilters,
    eligible: tuple[CandidateFacts, ...],
) -> tuple[RerankRequest, tuple[RerankCandidatePresentation, ...]]:
    candidates, presentations = load_rerank_snapshot_data(
        session,
        profile_id=profile_id,
        selected_genre_id=selected_genre_id,
        eligible=eligible,
    )
    candidates = project_rerank_candidates(
        candidates,
        select_product_projection(len(candidates)),
    )
    return (
        RerankRequest(
            prompt=prompt,
            selected_genre_id=selected_genre_id,
            selected_genre_name=" ".join(selected_genre_name.split())[:100],
            filters=filters,
            candidates=candidates,
        ),
        presentations,
    )


def build_rerank_candidate_pool(
    session: Session,
    *,
    profile_id: int,
    prompt: str,
    selected_genre_id: int,
    filters: RerankFilters,
    session_excluded_steam_app_ids: frozenset[int] = frozenset(),
) -> RerankCandidatePool:
    """Build the complete eligible pool before any provider interaction."""
    genres = list_available_rerank_genres(session, profile_id=profile_id)
    selected_genre = next(
        (item for item in genres if item.igdb_id == selected_genre_id), None
    )
    if selected_genre is None:
        raise RerankGenreUnavailableError(
            "The selected genre is not available for this library."
        )

    facts = load_candidate_facts(
        session,
        profile_id,
        active_facet_kinds=frozenset(
            {FacetKind.GENRE, FacetKind.THEME, FacetKind.GAME_MODE}
        ),
    )
    _validate_filter_ids(
        facts,
        selected_genre_id=selected_genre_id,
        filters=filters,
    )
    eligible = _eligible_facts(
        facts,
        selected_genre_id=selected_genre_id,
        filters=filters,
        session_excluded_steam_app_ids=session_excluded_steam_app_ids,
    )
    eligible_count = len(eligible)
    if eligible_count == 0:
        return RerankCandidatePool(
            state=RerankCandidatePoolState.EMPTY,
            eligible_count=0,
        )
    if eligible_count > MAX_RERANK_CANDIDATES:
        return RerankCandidatePool(
            state=RerankCandidatePoolState.NEEDS_REFINEMENT,
            eligible_count=eligible_count,
        )

    request, presentations = _load_snapshot(
        session,
        profile_id=profile_id,
        prompt=prompt,
        selected_genre_id=selected_genre_id,
        selected_genre_name=selected_genre.name,
        filters=filters,
        eligible=eligible,
    )
    return RerankCandidatePool(
        state=RerankCandidatePoolState.READY,
        eligible_count=eligible_count,
        request=request,
        presentations=presentations,
    )
