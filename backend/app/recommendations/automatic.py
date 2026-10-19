import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.integrations.igdb.images import igdb_cover_url
from app.models import (
    Game,
    GameIGDBMetadataTerm,
    IGDBMetadataTerm,
    ProfileGame,
)
from app.recommendations.contracts import (
    PreferenceConstraints,
    RecommendationPreference,
    ReferencePreference,
    SelectedFacets,
)
from app.recommendations.factual_scoring import FacetKind
from app.recommendations.final_results import FinalRecommendationResult
from app.recommendations.reference_reads import (
    ReferenceMetadataUnavailableError,
    ReferenceNotOwnedError,
)
from app.recommendations.service import recommend_cached_games

AUTOMATIC_MINIMUM_PLAYTIME_MINUTES = 60
RECENT_PLAYTIME_WEIGHT = 4
AUTOMATIC_SOURCE_GAME_LIMIT = 3
AUTOMATIC_SOURCE_SCAN_LIMIT = 10
AUTOMATIC_KEYWORD_LIMIT = 3

_AUTOMATIC_FACET_KINDS = (
    FacetKind.GENRE,
    FacetKind.THEME,
    FacetKind.KEYWORD,
)
# Whole words only, so a play description such as "steampunk" is not
# mistaken for a store or platform keyword.
_META_KEYWORD_PATTERN = re.compile(
    r"\b(?:achievements?|awards?|steam|xbox|playstation|ps[345]|nintendo|"
    r"controllers?|censorship|dlc|trophy|trophies|cloud saves?|"
    r"trading cards?|game pass)\b",
    re.IGNORECASE,
)


class AutomaticRecommendationStatus(StrEnum):
    """Describe whether automatic rows could be built."""

    READY = "ready"
    PREPARING = "preparing"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class PlayedGame:
    """Hold the cached play facts used to rank one owned game."""

    steam_app_id: int
    title: str
    cover_url: str | None
    igdb_status: str
    playtime_minutes: int
    recent_playtime_minutes: int | None
    last_played_at: datetime | None

    @property
    def interest_score(self) -> int:
        """Weight total playtime toward the last two weeks of play."""
        return self.playtime_minutes + RECENT_PLAYTIME_WEIGHT * (
            self.recent_playtime_minutes or 0
        )


@dataclass(frozen=True)
class AutomaticSourceGame:
    """Describe one played game used as an implicit reference."""

    steam_app_id: int
    title: str
    cover_url: str | None
    playtime_minutes: int
    facets: SelectedFacets


@dataclass(frozen=True)
class AutomaticRecommendationRow:
    """Pair one source game with the recommendations it produced."""

    source_game: AutomaticSourceGame
    result: FinalRecommendationResult


@dataclass(frozen=True)
class AutomaticRecommendations:
    """Return automatic rows and the combined preference behind them."""

    status: AutomaticRecommendationStatus
    rows: tuple[AutomaticRecommendationRow, ...]
    suggested_preference: RecommendationPreference | None


def rank_played_games(
    games: tuple[PlayedGame, ...],
) -> tuple[PlayedGame, ...]:
    """Order played games by weighted interest, then recency and ID."""
    return tuple(
        sorted(
            (
                game
                for game in games
                if game.playtime_minutes
                >= AUTOMATIC_MINIMUM_PLAYTIME_MINUTES
            ),
            key=lambda game: (
                -game.interest_score,
                game.last_played_at is None,
                -(
                    game.last_played_at.timestamp()
                    if game.last_played_at is not None
                    else 0
                ),
                game.steam_app_id,
            ),
        )
    )


def _load_played_games(
    session: Session,
    profile_id: int,
) -> tuple[PlayedGame, ...]:
    """Project one profile's owned games with enough playtime."""
    rows = session.execute(
        select(
            Game.steam_app_id,
            Game.name,
            Game.cover_image_id,
            Game.igdb_status,
            ProfileGame.playtime_minutes,
            ProfileGame.recent_playtime_minutes,
            ProfileGame.last_played_at,
        )
        .join(
            ProfileGame,
            ProfileGame.steam_app_id == Game.steam_app_id,
        )
        .where(
            ProfileGame.profile_id == profile_id,
            ProfileGame.playtime_minutes
            >= AUTOMATIC_MINIMUM_PLAYTIME_MINUTES,
        )
        .execution_options(autoflush=False)
    ).all()
    return tuple(
        PlayedGame(
            steam_app_id=row.steam_app_id,
            title=row.name,
            cover_url=igdb_cover_url(row.cover_image_id),
            igdb_status=row.igdb_status,
            playtime_minutes=row.playtime_minutes,
            recent_playtime_minutes=row.recent_playtime_minutes,
            last_played_at=row.last_played_at,
        )
        for row in rows
    )


def is_meta_keyword(name: str) -> bool:
    """Return whether a keyword describes the store or platform, not play."""
    return _META_KEYWORD_PATTERN.search(name) is not None


def _load_source_facets(
    session: Session,
    profile_id: int,
    steam_app_ids: tuple[int, ...],
) -> dict[int, SelectedFacets]:
    """Build each ready game's distinctive implicit facets in three selects.

    Genres and themes carried by more than half of the visitor's ready
    library are dropped because nearly every candidate matches them, unless
    nothing distinctive would remain. Game modes are never selected
    automatically. Keywords are the rarest ones that at least one other
    ready owned game shares, excluding store and platform keywords.
    """
    if not steam_app_ids:
        return {}

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
        .where(
            GameIGDBMetadataTerm.steam_app_id.in_(steam_app_ids),
            IGDBMetadataTerm.kind.in_(
                tuple(kind.value for kind in _AUTOMATIC_FACET_KINDS)
            ),
        )
        .execution_options(autoflush=False)
    ).all()

    ids_by_game: dict[int, dict[FacetKind, set[int]]] = {
        steam_app_id: {kind: set() for kind in _AUTOMATIC_FACET_KINDS}
        for steam_app_id in steam_app_ids
    }
    meta_keyword_ids: set[int] = set()
    for row in term_rows:
        kind = FacetKind(row.kind)
        ids_by_game[row.steam_app_id][kind].add(row.igdb_id)
        if kind is FacetKind.KEYWORD and is_meta_keyword(row.name):
            meta_keyword_ids.add(row.igdb_id)

    term_identities = {
        (kind.value, igdb_id)
        for ids in ids_by_game.values()
        for kind, kind_ids in ids.items()
        for igdb_id in kind_ids
    }
    ready_owner_counts: dict[tuple[FacetKind, int], int] = {}
    if term_identities:
        count_rows = session.execute(
            select(
                IGDBMetadataTerm.kind,
                IGDBMetadataTerm.igdb_id,
                func.count(
                    GameIGDBMetadataTerm.steam_app_id.distinct()
                ).label("game_count"),
            )
            .join(
                GameIGDBMetadataTerm,
                GameIGDBMetadataTerm.term_id == IGDBMetadataTerm.id,
            )
            .join(
                Game,
                Game.steam_app_id == GameIGDBMetadataTerm.steam_app_id,
            )
            .join(
                ProfileGame,
                ProfileGame.steam_app_id == Game.steam_app_id,
            )
            .where(
                ProfileGame.profile_id == profile_id,
                Game.igdb_status == "ready",
                IGDBMetadataTerm.kind.in_(
                    {kind for kind, _ in term_identities}
                ),
                IGDBMetadataTerm.igdb_id.in_(
                    {igdb_id for _, igdb_id in term_identities}
                ),
            )
            .group_by(IGDBMetadataTerm.kind, IGDBMetadataTerm.igdb_id)
            .execution_options(autoflush=False)
        ).all()
        ready_owner_counts = {
            (FacetKind(row.kind), row.igdb_id): row.game_count
            for row in count_rows
        }

    ready_library_size = session.scalar(
        select(func.count())
        .select_from(ProfileGame)
        .join(Game, Game.steam_app_id == ProfileGame.steam_app_id)
        .where(
            ProfileGame.profile_id == profile_id,
            Game.igdb_status == "ready",
        )
        .execution_options(autoflush=False)
    ) or 0

    def owner_count(kind: FacetKind, igdb_id: int) -> int:
        return ready_owner_counts.get((kind, igdb_id), 0)

    def distinctive(kind: FacetKind, ids: set[int]) -> tuple[int, ...]:
        return tuple(
            igdb_id
            for igdb_id in ids
            if owner_count(kind, igdb_id) * 2 <= ready_library_size
        )

    facets_by_game: dict[int, SelectedFacets] = {}
    for steam_app_id, ids in ids_by_game.items():
        # A keyword no other owned ready game carries cannot match.
        keywords = tuple(
            sorted(
                (
                    keyword_id
                    for keyword_id in ids[FacetKind.KEYWORD]
                    if keyword_id not in meta_keyword_ids
                    and owner_count(FacetKind.KEYWORD, keyword_id) > 1
                ),
                key=lambda keyword_id: (
                    owner_count(FacetKind.KEYWORD, keyword_id),
                    keyword_id,
                ),
            )[:AUTOMATIC_KEYWORD_LIMIT]
        )
        genres = distinctive(FacetKind.GENRE, ids[FacetKind.GENRE])
        themes = distinctive(FacetKind.THEME, ids[FacetKind.THEME])
        if not (genres or themes or keywords):
            # Common facets still beat having no reference at all.
            genres = tuple(ids[FacetKind.GENRE])
            themes = tuple(ids[FacetKind.THEME])
        if not (genres or themes or keywords):
            continue

        facets_by_game[steam_app_id] = SelectedFacets(
            genre_ids=genres,
            theme_ids=themes,
            keyword_ids=keywords,
            game_mode_ids=(),
        )

    return facets_by_game


def _source_game(
    game: PlayedGame,
    facets: SelectedFacets,
) -> AutomaticSourceGame:
    return AutomaticSourceGame(
        steam_app_id=game.steam_app_id,
        title=game.title,
        cover_url=game.cover_url,
        playtime_minutes=game.playtime_minutes,
        facets=facets,
    )


def _single_reference_preference(
    source_game: AutomaticSourceGame,
    constraints: PreferenceConstraints,
) -> RecommendationPreference:
    return RecommendationPreference(
        references=(
            ReferencePreference(
                steam_app_id=source_game.steam_app_id,
                facets=source_game.facets,
            ),
        ),
        constraints=constraints,
    )


def recommend_automatic_rows(
    session: Session,
    *,
    profile_id: int,
    constraints: PreferenceConstraints,
    rejected_steam_app_ids: frozenset[int],
    wait_for_pending: bool,
) -> AutomaticRecommendations:
    """Build one recommendation row per top played game."""
    ranked_games = rank_played_games(
        _load_played_games(session, profile_id)
    )
    scanned_ready_ids = tuple(
        game.steam_app_id
        for game in ranked_games
        if game.igdb_status == "ready"
    )[:AUTOMATIC_SOURCE_SCAN_LIMIT]
    facets_by_game = _load_source_facets(
        session,
        profile_id,
        scanned_ready_ids,
    )

    source_games: list[AutomaticSourceGame] = []
    for game in ranked_games:
        if len(source_games) == AUTOMATIC_SOURCE_GAME_LIMIT:
            break
        if game.igdb_status == "pending" and wait_for_pending:
            return AutomaticRecommendations(
                status=AutomaticRecommendationStatus.PREPARING,
                rows=(),
                suggested_preference=None,
            )
        facets = facets_by_game.get(game.steam_app_id)
        if facets is not None:
            source_games.append(_source_game(game, facets))

    if not source_games:
        return AutomaticRecommendations(
            status=AutomaticRecommendationStatus.UNAVAILABLE,
            rows=(),
            suggested_preference=None,
        )

    excluded_steam_app_ids = set(rejected_steam_app_ids) | {
        source_game.steam_app_id for source_game in source_games
    }
    rows: list[AutomaticRecommendationRow] = []
    for source_game in source_games:
        result = recommend_cached_games(
            session,
            profile_id=profile_id,
            preference=_single_reference_preference(
                source_game,
                constraints,
            ),
            session_excluded_steam_app_ids=frozenset(
                excluded_steam_app_ids
            ),
        )
        # Earlier rows keep their waiting games, so later rows skip them.
        excluded_steam_app_ids.update(
            item.presentation.steam_app_id for item in result.items
        )
        rows.append(
            AutomaticRecommendationRow(
                source_game=source_game,
                result=result,
            )
        )

    return AutomaticRecommendations(
        status=AutomaticRecommendationStatus.READY,
        rows=tuple(rows),
        suggested_preference=RecommendationPreference(
            references=tuple(
                ReferencePreference(
                    steam_app_id=source_game.steam_app_id,
                    facets=source_game.facets,
                )
                for source_game in source_games
            ),
            constraints=constraints,
        ),
    )


def recommend_more_like_game(
    session: Session,
    *,
    profile_id: int,
    steam_app_id: int,
    constraints: PreferenceConstraints,
    excluded_steam_app_ids: frozenset[int],
) -> AutomaticRecommendationRow:
    """Build one row using a single owned ready game as the reference."""
    row = session.execute(
        select(
            Game.steam_app_id,
            Game.name,
            Game.cover_image_id,
            Game.igdb_status,
            ProfileGame.playtime_minutes,
            ProfileGame.recent_playtime_minutes,
            ProfileGame.last_played_at,
        )
        .join(
            ProfileGame,
            ProfileGame.steam_app_id == Game.steam_app_id,
        )
        .where(
            ProfileGame.profile_id == profile_id,
            Game.steam_app_id == steam_app_id,
        )
        .execution_options(autoflush=False)
    ).one_or_none()
    if row is None:
        raise ReferenceNotOwnedError(
            "The selected reference game is not owned by this profile."
        )

    facets = None
    if row.igdb_status == "ready":
        facets = _load_source_facets(
            session,
            profile_id,
            (steam_app_id,),
        ).get(steam_app_id)
    if facets is None:
        raise ReferenceMetadataUnavailableError(
            "Factual metadata is unavailable for this reference game."
        )

    source_game = _source_game(
        PlayedGame(
            steam_app_id=row.steam_app_id,
            title=row.name,
            cover_url=igdb_cover_url(row.cover_image_id),
            igdb_status=row.igdb_status,
            playtime_minutes=row.playtime_minutes,
            recent_playtime_minutes=row.recent_playtime_minutes,
            last_played_at=row.last_played_at,
        ),
        facets,
    )
    result = recommend_cached_games(
        session,
        profile_id=profile_id,
        preference=_single_reference_preference(source_game, constraints),
        session_excluded_steam_app_ids=excluded_steam_app_ids,
    )
    return AutomaticRecommendationRow(
        source_game=source_game,
        result=result,
    )
