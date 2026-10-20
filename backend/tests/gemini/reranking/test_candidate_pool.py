import json

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
from app.gemini.reranking.reranker import (
    MAX_RERANK_REQUEST_BYTES,
    build_rerank_user_prompt,
    rerank_user_prompt_size_bytes,
)
from app.models import Game, GameIGDBMetadataTerm, IGDBMetadataTerm, Profile
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

    assert options.eligible_count == 2
    assert [
        (item.igdb_id, item.name, item.eligible_count)
        for item in options.themes
    ] == [(17, "Fantasy", 2)]
    assert [
        (item.igdb_id, item.name, item.eligible_count)
        for item in options.game_modes
    ] == [(2, "Multiplayer", 1), (1, "Single player", 1)]

    narrowed = list_rerank_filter_options(
        database_session,
        profile_id=1,
        selected_genre_id=31,
        play_status=PlayStatus.UNPLAYED,
        maximum_completion_minutes=90,
        theme_ids=(17,),
        game_mode_ids=(1,),
    )

    assert narrowed.eligible_count == 1
    assert narrowed.themes == options.themes
    assert narrowed.game_modes == options.game_modes


def _shrink_pool_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stand in 2 and 3 for the 400 and 2,000 limits to test routing cheaply."""
    import app.gemini.reranking.candidate_pool as candidate_pool

    monkeypatch.setattr(candidate_pool, "MAX_RERANK_DETAILED_CANDIDATES", 2)
    monkeypatch.setattr(candidate_pool, "MAX_RERANK_CANDIDATES", 3)


def test_zero_and_oversized_pools_never_build_a_provider_request(
    database_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _shrink_pool_limits(monkeypatch)
    for steam_app_id in range(1, 5):
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
    no_genre = build_rerank_candidate_pool(
        database_session,
        profile_id=1,
        prompt="Something fun",
        selected_genre_id=None,
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
    assert oversized.eligible_count == 4
    assert oversized.request is None
    assert oversized.presentations == ()
    assert no_genre.state is RerankCandidatePoolState.NEEDS_GENRE
    assert no_genre.request is None
    assert empty.state is RerankCandidatePoolState.EMPTY
    assert empty.eligible_count == 0
    assert empty.request is None


def test_pool_size_picks_the_detailed_or_names_genres_format(
    database_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _shrink_pool_limits(monkeypatch)
    _add_game(database_session, profile_id=1, steam_app_id=1)
    _add_game(
        database_session,
        profile_id=1,
        steam_app_id=2,
        genre=(12, "Role-playing (RPG)"),
    )

    def pool(selected_genre_id: int | None):
        return build_rerank_candidate_pool(
            database_session,
            profile_id=1,
            prompt="Something fun",
            selected_genre_id=selected_genre_id,
            filters=RerankFilters(),
        )

    small = pool(None)
    assert small.state is RerankCandidatePoolState.READY
    assert small.request.candidate_format == "detailed"
    assert small.request.selected_genre_id is None
    assert small.eligible_count == 2

    _add_game(database_session, profile_id=1, steam_app_id=3)
    large = pool(None)
    assert large.request.candidate_format == "names_genres"
    prompt = build_rerank_user_prompt(large.request)
    payload = json.loads(
        prompt.split("<rerank_input>\n")[1].split("\n</rerank_input>")[0]
    )
    assert payload["selected_genre"] is None
    assert {
        frozenset(candidate) for candidate in payload["candidates"]
    } == {frozenset({"id", "title", "genres"})}

    genre_pool = pool(31)
    assert genre_pool.request.candidate_format == "detailed"
    assert genre_pool.request.selected_genre_name == "Adventure"
    assert genre_pool.eligible_count == 2


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
    for steam_app_id in range(1, 402):
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
    assert pool.eligible_count == 400
    assert pool.request is not None
    assert 1 not in {item.steam_app_id for item in pool.request.candidates}


@pytest.mark.parametrize(
    ("game_count", "expected_summary_length"),
    [
        (30, 1200),
        (31, 300),
        (60, 300),
        (61, 240),
        (100, 240),
        (101, 240),
        (200, 240),
        (201, 240),
        (400, 240),
    ],
)
def test_complete_pool_uses_the_approved_adaptive_projection(
    database_session: Session,
    game_count: int,
    expected_summary_length: int,
) -> None:
    for steam_app_id in range(1, game_count + 1):
        _add_game(
            database_session,
            profile_id=1,
            steam_app_id=steam_app_id,
            summary="s" * 1200,
        )

    pool = build_rerank_candidate_pool(
        database_session,
        profile_id=1,
        prompt="x" * 500,
        selected_genre_id=31,
        filters=RerankFilters(),
    )

    assert pool.state is RerankCandidatePoolState.READY
    assert pool.eligible_count == game_count
    assert pool.request is not None
    assert len(pool.request.candidates) == game_count
    assert {
        len(candidate.summary or "") for candidate in pool.request.candidates
    } == {expected_summary_length}
    assert (
        rerank_user_prompt_size_bytes(pool.request)
        <= MAX_RERANK_REQUEST_BYTES
    )


def test_only_the_headline_score_reaches_the_provider_prompt(
    database_session: Session,
) -> None:
    _add_game(database_session, profile_id=1, steam_app_id=7)
    _add_game(database_session, profile_id=1, steam_app_id=8)
    _add_game(database_session, profile_id=1, steam_app_id=9)
    critics_game = database_session.get(Game, 7)
    critics_game.igdb_total_rating = 87.4
    critics_game.igdb_total_rating_count = 1_204
    critics_game.igdb_aggregated_rating = 93.6
    critics_game.igdb_aggregated_rating_count = 12
    rated_game = database_session.get(Game, 8)
    rated_game.igdb_total_rating = 81.2
    rated_game.igdb_total_rating_count = 40
    rated_game.igdb_aggregated_rating = 55.0
    rated_game.igdb_aggregated_rating_count = 2
    thin_game = database_session.get(Game, 9)
    thin_game.igdb_total_rating = 99.0
    thin_game.igdb_total_rating_count = 3
    database_session.commit()

    pool = build_rerank_candidate_pool(
        database_session,
        profile_id=1,
        prompt="Something tense",
        selected_genre_id=31,
        filters=RerankFilters(),
    )

    assert pool.request is not None
    scores = {
        candidate.steam_app_id: (candidate.critic_score, candidate.igdb_rating)
        for candidate in pool.request.candidates
    }
    assert scores == {7: (94, None), 8: (None, 81), 9: (None, None)}
    prompt = build_rerank_user_prompt(pool.request)
    payload = json.loads(
        prompt.split("<rerank_input>\n")[1].split("\n</rerank_input>")[0]
    )
    sent = {
        candidate["steam_app_id"]: candidate
        for candidate in payload["candidates"]
    }

    assert sent[7]["critic_score"] == 94 and "igdb_rating" not in sent[7]
    assert sent[8]["igdb_rating"] == 81 and "critic_score" not in sent[8]
    assert "critic_score" not in sent[9] and "igdb_rating" not in sent[9]
    # Vote counts and raw averages never reach the model.
    assert not any(
        "count" in key or "aggregated" in key or "total" in key
        for candidate in payload["candidates"]
        for key in candidate
    )


def test_an_oversized_large_payload_asks_for_narrowing_instead_of_failing(
    database_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.gemini.reranking.candidate_pool as candidate_pool

    _shrink_pool_limits(monkeypatch)
    monkeypatch.setattr(candidate_pool, "MAX_RERANK_REQUEST_BYTES", 100)
    for steam_app_id in range(1, 4):
        _add_game(database_session, profile_id=1, steam_app_id=steam_app_id)

    def pool(selected_genre_id: int | None):
        return build_rerank_candidate_pool(
            database_session,
            profile_id=1,
            prompt="Something fun",
            selected_genre_id=selected_genre_id,
            filters=RerankFilters(),
        )

    assert pool(None).state is RerankCandidatePoolState.NEEDS_GENRE
    assert pool(31).state is RerankCandidatePoolState.NEEDS_REFINEMENT
    assert pool(None).request is None
