from collections.abc import Generator

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.database import Base
from app.models import (
    Game,
    GameIGDBMetadataTerm,
    IGDBMetadataTerm,
    Profile,
    ProfileGame,
)
from app.recommendations.candidate_facts import CandidateFacts
from app.recommendations.candidate_reads import load_candidate_facts
from app.recommendations.factual_scoring import FacetKind


@pytest.fixture
def database_session() -> Generator[Session, None, None]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine, expire_on_commit=False) as session:
        yield session

    engine.dispose()


def _profile(profile_id: int) -> Profile:
    return Profile(
        id=profile_id,
        steam_id=f"7656119800000000{profile_id}",
        display_name=f"Player {profile_id}",
    )


def _ownership(
    profile: Profile,
    game: Game,
    *,
    playtime_minutes: int,
) -> ProfileGame:
    return ProfileGame(
        profile=profile,
        game=game,
        playtime_minutes=playtime_minutes,
    )


def _term(
    term_id: int,
    *,
    kind: str,
    igdb_id: int,
) -> IGDBMetadataTerm:
    return IGDBMetadataTerm(
        id=term_id,
        kind=kind,
        igdb_id=igdb_id,
        name=f"{kind} {igdb_id}",
    )


def test_loads_only_selected_profiles_owned_candidate_facts(
    database_session: Session,
) -> None:
    selected_profile = _profile(1)
    other_profile = _profile(2)
    shared_game = Game(
        steam_app_id=30,
        name="Shared",
        igdb_status="ready",
        time_to_beat_normally_seconds=7_200,
    )
    selected_only_game = Game(
        steam_app_id=10,
        name="Selected only",
        igdb_status="ready",
        time_to_beat_normally_seconds=None,
    )
    other_only_game = Game(
        steam_app_id=20,
        name="Other only",
        igdb_status="ready",
        time_to_beat_normally_seconds=3_600,
    )
    database_session.add_all(
        [
            _ownership(
                selected_profile,
                shared_game,
                playtime_minutes=7,
            ),
            _ownership(
                selected_profile,
                selected_only_game,
                playtime_minutes=0,
            ),
            _ownership(
                other_profile,
                shared_game,
                playtime_minutes=99,
            ),
            _ownership(
                other_profile,
                other_only_game,
                playtime_minutes=50,
            ),
        ]
    )
    database_session.commit()

    result = load_candidate_facts(
        database_session,
        selected_profile.id,
        active_facet_kinds=frozenset({FacetKind.GENRE}),
    )

    assert result == (
        CandidateFacts(
            steam_app_id=10,
            owned_by_selected_profile=True,
            total_playtime_minutes=0,
            normal_completion_seconds=None,
            genre_ids=(),
            theme_ids=None,
            keyword_ids=None,
            game_mode_ids=None,
        ),
        CandidateFacts(
            steam_app_id=30,
            owned_by_selected_profile=True,
            total_playtime_minutes=7,
            normal_completion_seconds=7_200,
            genre_ids=(),
            theme_ids=None,
            keyword_ids=None,
            game_mode_ids=None,
        ),
    )


def test_projects_active_terms_as_sorted_unique_igdb_ids(
    database_session: Session,
) -> None:
    profile = _profile(1)
    game = Game(
        steam_app_id=10,
        name="Candidate",
        igdb_status="ready",
    )
    high_genre = _term(1, kind="genre", igdb_id=30)
    low_genre = _term(2, kind="genre", igdb_id=10)
    inactive_theme = _term(3, kind="theme", igdb_id=20)
    database_session.add_all(
        [
            _ownership(profile, game, playtime_minutes=0),
            GameIGDBMetadataTerm(game=game, term=high_genre),
            GameIGDBMetadataTerm(game=game, term=low_genre),
            GameIGDBMetadataTerm(game=game, term=inactive_theme),
        ]
    )
    database_session.commit()

    result = load_candidate_facts(
        database_session,
        profile.id,
        active_facet_kinds=frozenset({FacetKind.GENRE}),
    )

    assert result[0].genre_ids == (10, 30)
    assert result[0].theme_ids is None
    assert result[0].keyword_ids is None
    assert result[0].game_mode_ids is None


def test_distinguishes_ready_empty_facets_from_nonready_unknown_facets(
    database_session: Session,
) -> None:
    profile = _profile(1)
    ready_game = Game(
        steam_app_id=10,
        name="Ready without terms",
        igdb_status="ready",
    )
    missing_game = Game(
        steam_app_id=20,
        name="Missing metadata",
        igdb_status="missing",
    )
    database_session.add_all(
        [
            _ownership(profile, ready_game, playtime_minutes=0),
            _ownership(profile, missing_game, playtime_minutes=0),
        ]
    )
    database_session.commit()

    result = load_candidate_facts(
        database_session,
        profile.id,
        active_facet_kinds=frozenset(
            {
                FacetKind.GENRE,
                FacetKind.THEME,
                FacetKind.KEYWORD,
                FacetKind.GAME_MODE,
            }
        ),
    )

    assert result[0].genre_ids == ()
    assert result[0].theme_ids == ()
    assert result[0].keyword_ids == ()
    assert result[0].game_mode_ids == ()
    assert result[1].genre_ids is None
    assert result[1].theme_ids is None
    assert result[1].keyword_ids is None
    assert result[1].game_mode_ids is None


def test_maps_every_active_facet_kind_to_its_candidate_field(
    database_session: Session,
) -> None:
    profile = _profile(1)
    game = Game(
        steam_app_id=10,
        name="Candidate",
        igdb_status="ready",
    )
    terms = [
        _term(1, kind="genre", igdb_id=10),
        _term(2, kind="theme", igdb_id=20),
        _term(3, kind="keyword", igdb_id=30),
        _term(4, kind="game_mode", igdb_id=40),
    ]
    database_session.add(
        _ownership(profile, game, playtime_minutes=0)
    )
    database_session.add_all(
        [
            GameIGDBMetadataTerm(game=game, term=term)
            for term in terms
        ]
    )
    database_session.commit()

    result = load_candidate_facts(
        database_session,
        profile.id,
        active_facet_kinds=frozenset(FacetKind),
    )

    assert result[0].genre_ids == (10,)
    assert result[0].theme_ids == (20,)
    assert result[0].keyword_ids == (30,)
    assert result[0].game_mode_ids == (40,)


def test_empty_owned_library_returns_empty_tuple(
    database_session: Session,
) -> None:
    profile = _profile(1)
    database_session.add(profile)
    database_session.commit()

    result = load_candidate_facts(
        database_session,
        profile.id,
        active_facet_kinds=frozenset({FacetKind.GENRE}),
    )

    assert result == ()


def test_loads_all_owned_games_without_candidate_pool_truncation(
    database_session: Session,
) -> None:
    profile = _profile(1)
    games = [
        Game(
            steam_app_id=steam_app_id,
            name=f"Candidate {steam_app_id}",
            igdb_status="ready",
        )
        for steam_app_id in range(30, 10, -1)
    ]
    database_session.add_all(
        [
            _ownership(profile, game, playtime_minutes=0)
            for game in games
        ]
    )
    database_session.commit()

    result = load_candidate_facts(
        database_session,
        profile.id,
        active_facet_kinds=frozenset({FacetKind.GENRE}),
    )

    assert len(result) == 20
    assert tuple(candidate.steam_app_id for candidate in result) == tuple(
        range(11, 31)
    )


def test_candidate_projection_uses_two_bounded_selects(
    database_session: Session,
) -> None:
    profile = _profile(1)
    genre = _term(1, kind="genre", igdb_id=10)
    theme = _term(2, kind="theme", igdb_id=20)
    games = [
        Game(
            steam_app_id=steam_app_id,
            name=f"Candidate {steam_app_id}",
            igdb_status="ready",
        )
        for steam_app_id in range(1, 21)
    ]
    database_session.add_all(
        [
            _ownership(profile, game, playtime_minutes=0)
            for game in games
        ]
    )
    database_session.add_all(
        [
            GameIGDBMetadataTerm(game=game, term=term)
            for game in games
            for term in (genre, theme)
        ]
    )
    database_session.commit()

    statements: list[tuple[str, object]] = []

    def record_select(
        connection: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append((statement, parameters))

    bind = database_session.get_bind()
    event.listen(bind, "before_cursor_execute", record_select)

    try:
        result = load_candidate_facts(
            database_session,
            profile.id,
            active_facet_kinds=frozenset({FacetKind.GENRE}),
        )
    finally:
        event.remove(bind, "before_cursor_execute", record_select)

    assert len(result) == 20
    assert len(statements) == 2
    combined_sql = " ".join(
        statement.lower() for statement, _ in statements
    )
    assert "game_trait" not in combined_sql
    assert "summary" not in combined_sql
    assert "time_to_beat_hastily" not in combined_sql
    assert "time_to_beat_completely" not in combined_sql
    combined_parameters = repr(
        tuple(parameters for _, parameters in statements)
    )
    assert "genre" in combined_parameters
    assert "theme" not in combined_parameters
    assert "keyword" not in combined_parameters
    assert "game_mode" not in combined_parameters


def test_candidate_projection_does_not_autoflush_pending_writes(
    database_session: Session,
) -> None:
    profile = _profile(1)
    database_session.add(profile)
    database_session.commit()
    pending_game = Game(
        steam_app_id=10,
        name="Pending candidate",
        igdb_status="ready",
    )
    database_session.add(
        _ownership(profile, pending_game, playtime_minutes=0)
    )

    result = load_candidate_facts(
        database_session,
        profile.id,
        active_facet_kinds=frozenset({FacetKind.GENRE}),
    )

    assert result == ()
    assert pending_game in database_session.new
