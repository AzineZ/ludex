from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import pytest

from app.database import Base
from app.gemini.reranking.candidate_pool import (
    RerankCandidatePoolState,
    RerankFilterUnavailableError,
    RerankGenreUnavailableError,
    build_rerank_candidate_pool,
    list_available_rerank_genres,
    list_rerank_filter_options,
)
from app.gemini.reranking.contracts import RerankFilters
from app.models import GameIGDBMetadataTerm, IGDBMetadataTerm, Profile
from app.recommendations.contracts import PlayStatus
from tests.recommendations.recommendation_api_support import (
    _owned_game,
    _profile,
)


@pytest.fixture
def database_session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session
    engine.dispose()


def _add_game(
    session: Session,
    *,
    profile_id: int,
    steam_app_id: int,
    status: str = "ready",
    playtime_minutes: int = 0,
    completion_seconds: int | None = None,
    summary: str | None = "A cached factual summary.",
    genre: tuple[int, str] = (31, "Adventure"),
    theme: tuple[int, str] | None = None,
    game_mode: tuple[int, str] | None = None,
) -> None:
    profile = session.get(Profile, profile_id)
    if profile is None:
        profile = _profile(profile_id)

    def term_link(kind: str, identity: tuple[int, str]) -> GameIGDBMetadataTerm:
        igdb_id, name = identity
        with session.no_autoflush:
            term = session.query(IGDBMetadataTerm).filter_by(
                kind=kind,
                igdb_id=igdb_id,
            ).one_or_none()
        if term is None:
            term = IGDBMetadataTerm(kind=kind, igdb_id=igdb_id, name=name)
        return GameIGDBMetadataTerm(term=term)

    links = [term_link("genre", genre)]
    if theme is not None:
        links.append(term_link("theme", theme))
    if game_mode is not None:
        links.append(term_link("game_mode", game_mode))
    game = _owned_game(
        profile,
        steam_app_id,
        f"Game {steam_app_id}",
        status=status,
        cover_image_id=f"cover-{steam_app_id}",
        playtime_minutes=playtime_minutes,
        normal_completion_seconds=completion_seconds,
        links=tuple(links),
    )
    game.summary = summary
    session.add(game)
    session.commit()


def test_available_genres_are_ready_owned_profile_scoped_and_counted(
    database_session: Session,
) -> None:
    _add_game(database_session, profile_id=1, steam_app_id=1)
    _add_game(database_session, profile_id=1, steam_app_id=2)
    _add_game(
        database_session,
        profile_id=1,
        steam_app_id=3,
        genre=(5, "Shooter"),
    )
    _add_game(
        database_session,
        profile_id=1,
        steam_app_id=4,
        status="pending",
        genre=(9, "Puzzle"),
    )
    _add_game(
        database_session,
        profile_id=2,
        steam_app_id=5,
        genre=(12, "Racing"),
    )

    genres = list_available_rerank_genres(database_session, profile_id=1)

    assert [(item.igdb_id, item.name, item.eligible_count) for item in genres] == [
        (31, "Adventure", 2),
        (5, "Shooter", 1),
    ]


def test_candidate_pool_applies_every_hard_filter_before_snapshot(
    database_session: Session,
) -> None:
    _add_game(
        database_session,
        profile_id=1,
        steam_app_id=1,
        completion_seconds=3_600,
        theme=(17, "Fantasy"),
        game_mode=(1, "Single player"),
    )
    _add_game(
        database_session,
        profile_id=1,
        steam_app_id=2,
        playtime_minutes=30,
        completion_seconds=3_600,
        theme=(17, "Fantasy"),
        game_mode=(1, "Single player"),
    )
    _add_game(
        database_session,
        profile_id=1,
        steam_app_id=3,
        completion_seconds=9_000,
        theme=(17, "Fantasy"),
        game_mode=(1, "Single player"),
    )
    _add_game(
        database_session,
        profile_id=1,
        steam_app_id=4,
        completion_seconds=3_600,
        theme=(18, "Science fiction"),
        game_mode=(2, "Multiplayer"),
    )

    pool = build_rerank_candidate_pool(
        database_session,
        profile_id=1,
        prompt="Something calm after work",
        selected_genre_id=31,
        filters=RerankFilters(
            play_status=PlayStatus.UNPLAYED,
            maximum_completion_minutes=90,
            theme_ids=(17,),
            game_mode_ids=(1,),
        ),
        session_excluded_steam_app_ids=frozenset({99}),
    )

    assert pool.state is RerankCandidatePoolState.READY
    assert pool.eligible_count == 1
    assert pool.request is not None
    assert pool.request.selected_genre_name == "Adventure"
    assert [item.steam_app_id for item in pool.request.candidates] == [1]
    candidate = pool.request.candidates[0]
    assert candidate.summary == "A cached factual summary."
    assert candidate.themes == ("Fantasy",)
    assert candidate.game_modes == ("Single player",)
    assert candidate.normal_completion_minutes == 60
    assert pool.presentations[0].cover_url.endswith("cover-1.jpg")


def test_filter_options_are_scoped_to_genre_and_current_basic_constraints(
    database_session: Session,
) -> None:
    _add_game(
        database_session,
        profile_id=1,
        steam_app_id=1,
        completion_seconds=3_600,
        theme=(17, "Fantasy"),
        game_mode=(1, "Single player"),
    )
    _add_game(
        database_session,
        profile_id=1,
        steam_app_id=2,
        completion_seconds=3_600,
        theme=(17, "Fantasy"),
        game_mode=(2, "Multiplayer"),
    )
    _add_game(
        database_session,
        profile_id=1,
        steam_app_id=3,
        playtime_minutes=30,
        completion_seconds=3_600,
        theme=(18, "Science fiction"),
        game_mode=(1, "Single player"),
    )
    _add_game(
        database_session,
        profile_id=1,
        steam_app_id=4,
        completion_seconds=3_600,
        genre=(5, "Shooter"),
        theme=(18, "Science fiction"),
        game_mode=(2, "Multiplayer"),
    )

    options = list_rerank_filter_options(
        database_session,
        profile_id=1,
        selected_genre_id=31,
        play_status=PlayStatus.UNPLAYED,
        maximum_completion_minutes=90,
    )

    assert [
        (item.igdb_id, item.name, item.eligible_count)
        for item in options.themes
    ] == [(17, "Fantasy", 2)]
    assert [
        (item.igdb_id, item.name, item.eligible_count)
        for item in options.game_modes
    ] == [(2, "Multiplayer", 1), (1, "Single player", 1)]


def test_zero_and_oversized_pools_never_build_a_provider_request(
    database_session: Session,
) -> None:
    for steam_app_id in range(1, 32):
        _add_game(
            database_session,
            profile_id=1,
            steam_app_id=steam_app_id,
        )

    oversized = build_rerank_candidate_pool(
        database_session,
        profile_id=1,
        prompt="Something fun",
        selected_genre_id=31,
        filters=RerankFilters(),
    )
    empty = build_rerank_candidate_pool(
        database_session,
        profile_id=1,
        prompt="Something fun",
        selected_genre_id=31,
        filters=RerankFilters(play_status=PlayStatus.PREVIOUSLY_PLAYED),
    )

    assert oversized.state is RerankCandidatePoolState.NEEDS_REFINEMENT
    assert oversized.eligible_count == 31
    assert oversized.request is None
    assert oversized.presentations == ()
    assert empty.state is RerankCandidatePoolState.EMPTY
    assert empty.eligible_count == 0
    assert empty.request is None


def test_submitted_genre_and_filter_ids_are_revalidated_for_profile(
    database_session: Session,
) -> None:
    _add_game(
        database_session,
        profile_id=1,
        steam_app_id=1,
        theme=(17, "Fantasy"),
    )

    with pytest.raises(RerankGenreUnavailableError):
        build_rerank_candidate_pool(
            database_session,
            profile_id=1,
            prompt="Something fun",
            selected_genre_id=999,
            filters=RerankFilters(),
        )

    with pytest.raises(RerankFilterUnavailableError) as error:
        build_rerank_candidate_pool(
            database_session,
            profile_id=1,
            prompt="Something fun",
            selected_genre_id=31,
            filters=RerankFilters(theme_ids=(999,)),
        )

    assert error.value.field == "filters.theme_ids"


def test_session_exclusions_are_applied_before_the_complete_count(
    database_session: Session,
) -> None:
    for steam_app_id in range(1, 32):
        _add_game(
            database_session,
            profile_id=1,
            steam_app_id=steam_app_id,
        )

    pool = build_rerank_candidate_pool(
        database_session,
        profile_id=1,
        prompt="Something fun",
        selected_genre_id=31,
        filters=RerankFilters(),
        session_excluded_steam_app_ids=frozenset({1}),
    )

    assert pool.state is RerankCandidatePoolState.READY
    assert pool.eligible_count == 30
    assert pool.request is not None
    assert 1 not in {item.steam_app_id for item in pool.request.candidates}
