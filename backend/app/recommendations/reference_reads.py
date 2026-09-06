from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.integrations.igdb.images import igdb_cover_url
from app.models import (
    Game,
    GameIGDBMetadataTerm,
    IGDBMetadataTerm,
    Profile,
    ProfileGame,
)

SEARCH_RESULT_LIMIT = 10
KEYWORD_BROWSE_LIMIT = 250


class InvalidSearchQueryError(ValueError):
    """Report a query that cannot be used for autocomplete."""

    code = "invalid_query"
    field = "query"


class ProfileNotFoundError(LookupError):
    """Report an unknown local profile."""

    code = "profile_not_found"
    field = "profile_id"


class ReferenceNotOwnedError(LookupError):
    """Report a reference outside the selected profile's library."""

    code = "reference_not_owned"
    field = "steam_app_id"


class ReferenceMetadataUnavailableError(LookupError):
    """Report a reference without ready factual metadata."""

    code = "reference_metadata_unavailable"
    field = "steam_app_id"


class MetadataStatus(StrEnum):
    """Identify the cached factual enrichment state."""

    PENDING = "pending"
    READY = "ready"
    MISSING = "missing"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True)
class OwnedGameSuggestion:
    """Project one owned game for autocomplete."""

    steam_app_id: int
    name: str
    cover_url: str | None
    metadata_status: MetadataStatus


@dataclass(frozen=True)
class FacetOption:
    """Project one stored IGDB facet for selection."""

    id: int
    name: str


@dataclass(frozen=True)
class KeywordBrowse:
    """Project one bounded reference-scoped keyword collection."""

    items: tuple[FacetOption, ...]
    truncated: bool


@dataclass(frozen=True)
class ReferenceFacets:
    """Project directly displayed facets for one reference."""

    genres: tuple[FacetOption, ...]
    themes: tuple[FacetOption, ...]
    game_modes: tuple[FacetOption, ...]


@dataclass(frozen=True)
class ReferenceDetails:
    """Project one ready owned reference and its direct facets."""

    steam_app_id: int
    name: str
    cover_url: str | None
    metadata_status: MetadataStatus
    facets: ReferenceFacets


@dataclass(frozen=True)
class _OwnedReadyReference:
    """Project cached fields shared by ready-reference reads."""

    steam_app_id: int
    name: str
    cover_image_id: str | None
    metadata_status: MetadataStatus


def normalize_search_query(query: str) -> str:
    """Normalize and validate one autocomplete query.

    Args:
        query: Raw text supplied to game or keyword autocomplete.

    Returns:
        The query with surrounding whitespace removed and internal
        whitespace collapsed.

    Raises:
        InvalidSearchQueryError: If the value is not a string or its
            normalized length is outside the inclusive 1–100 range.
    """
    if not isinstance(query, str):
        raise InvalidSearchQueryError(
            "Search query must contain between 1 and 100 characters."
        )

    normalized_query = " ".join(query.split())

    if not 1 <= len(normalized_query) <= 100:
        raise InvalidSearchQueryError(
            "Search query must contain between 1 and 100 characters."
        )

    return normalized_query


def _require_profile(
    session: Session,
    profile_id: int,
) -> None:
    """Require one existing local profile."""
    stored_profile_id = session.scalar(
        select(Profile.id).where(Profile.id == profile_id)
    )
    if stored_profile_id is None:
        raise ProfileNotFoundError(
            "The selected profile does not exist."
        )


def _load_owned_ready_reference(
    session: Session,
    profile_id: int,
    steam_app_id: int,
) -> _OwnedReadyReference:
    """Require and project one owned reference with ready metadata."""
    _require_profile(session, profile_id)

    game_row = session.execute(
        select(
            Game.steam_app_id,
            Game.name,
            Game.cover_image_id,
            Game.igdb_status,
        )
        .join(
            ProfileGame,
            ProfileGame.steam_app_id == Game.steam_app_id,
        )
        .where(
            ProfileGame.profile_id == profile_id,
            Game.steam_app_id == steam_app_id,
        )
    ).one_or_none()

    if game_row is None:
        raise ReferenceNotOwnedError(
            "The selected reference game is not owned by this profile."
        )

    metadata_status = MetadataStatus(game_row.igdb_status)
    if metadata_status is not MetadataStatus.READY:
        raise ReferenceMetadataUnavailableError(
            "Factual metadata is unavailable for this reference game."
        )

    return _OwnedReadyReference(
        steam_app_id=game_row.steam_app_id,
        name=game_row.name,
        cover_image_id=game_row.cover_image_id,
        metadata_status=metadata_status,
    )


def search_owned_games(
    session: Session,
    profile_id: int,
    query: str,
) -> tuple[OwnedGameSuggestion, ...]:
    """Search one profile's cached owned games.

    Args:
        session: Database session used only for cached reads.
        profile_id: Selected local profile identity.
        query: Raw autocomplete text.

    Returns:
        Immutable owned-game suggestions.

    Raises:
        InvalidSearchQueryError: If the normalized query is invalid.
        ProfileNotFoundError: If the selected profile does not exist.
    """
    normalized_query = normalize_search_query(query)

    _require_profile(session, profile_id)

    normalized_name = func.lower(Game.name)
    normalized_pattern = normalized_query.lower()

    match_tier = case(
        (
            normalized_name == normalized_pattern,
            0,
        ),
        (
            normalized_name.startswith(
                normalized_pattern,
                autoescape=True,
            ),
            1,
        ),
        else_=2,
    )

    rows = session.execute(
        select(
            Game.steam_app_id,
            Game.name,
            Game.cover_image_id,
            Game.igdb_status,
        )
        .join(
            ProfileGame,
            ProfileGame.steam_app_id == Game.steam_app_id,
        )
        .where(
            ProfileGame.profile_id == profile_id,
            normalized_name.contains(
                normalized_pattern,
                autoescape=True,
            ),
        )
        .order_by(
            match_tier,
            normalized_name,
            Game.name,
            Game.steam_app_id,
        )
        .limit(SEARCH_RESULT_LIMIT)
    ).all()

    return tuple(
        OwnedGameSuggestion(
            steam_app_id=row.steam_app_id,
            name=row.name,
            cover_url=igdb_cover_url(row.cover_image_id),
            metadata_status=MetadataStatus(row.igdb_status),
        )
        for row in rows
    )


def load_reference_details(
    session: Session,
    profile_id: int,
    steam_app_id: int,
) -> ReferenceDetails:
    """Load one owned ready reference and its direct factual facets.

    Args:
        session: Database session used only for cached reads.
        profile_id: Selected local profile identity.
        steam_app_id: Authoritative Steam identity of the reference.

    Returns:
        Immutable reference details with genres, themes, and game modes.

    Raises:
        ProfileNotFoundError: If the selected profile does not exist.
        ReferenceNotOwnedError: If the game is not owned by the profile.
        ReferenceMetadataUnavailableError: If factual metadata is not ready.
    """
    reference = _load_owned_ready_reference(
        session,
        profile_id,
        steam_app_id,
    )

    term_rows = session.execute(
        select(
            IGDBMetadataTerm.kind,
            IGDBMetadataTerm.igdb_id,
            IGDBMetadataTerm.name,
        )
        .join(
            GameIGDBMetadataTerm,
            GameIGDBMetadataTerm.term_id == IGDBMetadataTerm.id,
        )
        .where(
            GameIGDBMetadataTerm.steam_app_id == steam_app_id,
            IGDBMetadataTerm.kind.in_(
                ("genre", "theme", "game_mode")
            ),
        )
        .order_by(
            IGDBMetadataTerm.kind,
            func.lower(IGDBMetadataTerm.name),
            IGDBMetadataTerm.name,
            IGDBMetadataTerm.igdb_id,
        )
    ).all()

    grouped_facets: dict[str, list[FacetOption]] = {
        "genre": [],
        "theme": [],
        "game_mode": [],
    }
    for term_row in term_rows:
        grouped_facets[term_row.kind].append(
            FacetOption(
                id=term_row.igdb_id,
                name=term_row.name,
            )
        )

    return ReferenceDetails(
        steam_app_id=reference.steam_app_id,
        name=reference.name,
        cover_url=igdb_cover_url(reference.cover_image_id),
        metadata_status=reference.metadata_status,
        facets=ReferenceFacets(
            genres=tuple(grouped_facets["genre"]),
            themes=tuple(grouped_facets["theme"]),
            game_modes=tuple(grouped_facets["game_mode"]),
        ),
    )


def search_reference_keywords(
    session: Session,
    profile_id: int,
    steam_app_id: int,
    query: str,
) -> tuple[FacetOption, ...]:
    """Search exact stored keywords for one owned ready reference.

    Args:
        session: Database session used only for cached reads.
        profile_id: Selected local profile identity.
        steam_app_id: Authoritative Steam identity of the reference.
        query: Raw keyword autocomplete text.

    Returns:
        Immutable stored keyword options.

    Raises:
        InvalidSearchQueryError: If the normalized query is invalid.
        ProfileNotFoundError: If the selected profile does not exist.
        ReferenceNotOwnedError: If the game is not owned by the profile.
        ReferenceMetadataUnavailableError: If factual metadata is not ready.
    """
    normalized_query = normalize_search_query(query)
    _load_owned_ready_reference(
        session,
        profile_id,
        steam_app_id,
    )

    normalized_name = func.lower(IGDBMetadataTerm.name)
    normalized_pattern = normalized_query.lower()
    match_tier = case(
        (
            normalized_name == normalized_pattern,
            0,
        ),
        (
            normalized_name.startswith(
                normalized_pattern,
                autoescape=True,
            ),
            1,
        ),
        else_=2,
    )

    rows = session.execute(
        select(
            IGDBMetadataTerm.igdb_id,
            IGDBMetadataTerm.name,
        )
        .join(
            GameIGDBMetadataTerm,
            GameIGDBMetadataTerm.term_id == IGDBMetadataTerm.id,
        )
        .where(
            GameIGDBMetadataTerm.steam_app_id == steam_app_id,
            IGDBMetadataTerm.kind == "keyword",
            normalized_name.contains(
                normalized_pattern,
                autoescape=True,
            ),
        )
        .order_by(
            match_tier,
            normalized_name,
            IGDBMetadataTerm.name,
            IGDBMetadataTerm.igdb_id,
        )
        .limit(SEARCH_RESULT_LIMIT)
    ).all()

    return tuple(
        FacetOption(
            id=row.igdb_id,
            name=row.name,
        )
        for row in rows
    )


def browse_reference_keywords(
    session: Session,
    profile_id: int,
    steam_app_id: int,
) -> KeywordBrowse:
    """Browse a bounded alphabetical keyword list for one reference.

    The extra fetched row is used only to report truncation. It is never
    exposed as a selectable option.
    """
    _load_owned_ready_reference(
        session,
        profile_id,
        steam_app_id,
    )

    rows = session.execute(
        select(
            IGDBMetadataTerm.igdb_id,
            IGDBMetadataTerm.name,
        )
        .join(
            GameIGDBMetadataTerm,
            GameIGDBMetadataTerm.term_id == IGDBMetadataTerm.id,
        )
        .where(
            GameIGDBMetadataTerm.steam_app_id == steam_app_id,
            IGDBMetadataTerm.kind == "keyword",
        )
        .order_by(
            func.lower(IGDBMetadataTerm.name),
            IGDBMetadataTerm.name,
            IGDBMetadataTerm.igdb_id,
        )
        .limit(KEYWORD_BROWSE_LIMIT + 1)
    ).all()

    return KeywordBrowse(
        items=tuple(
            FacetOption(id=row.igdb_id, name=row.name)
            for row in rows[:KEYWORD_BROWSE_LIMIT]
        ),
        truncated=len(rows) > KEYWORD_BROWSE_LIMIT,
    )
