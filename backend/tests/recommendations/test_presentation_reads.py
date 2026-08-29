from collections.abc import Generator

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Game, IGDBMetadataTerm, Profile, ProfileGame
from app.recommendations.factual_scoring import FacetKind
from app.recommendations.final_results import (
    CandidatePresentationFacts,
    FacetLabel,
)
from app.recommendations.presentation_reads import (
    FinalResultPresentationProjection,
    load_final_result_presentation,
)


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
    playtime_minutes: int,
) -> ProfileGame:
    return ProfileGame(
        profile=profile,
        game=game,
        playtime_minutes=playtime_minutes,
    )


def test_projects_only_selected_owned_games_with_profile_specific_playtime(
    database_session: Session,
) -> None:
    selected_profile = _profile(1)
    other_profile = _profile(2)
    shared_game = Game(
        steam_app_id=620,
        name="Portal 2",
        cover_image_id="co6abc",
        time_to_beat_normally_seconds=28_800,
    )
    selected_unrequested = Game(
        steam_app_id=220,
        name="Half-Life 2",
        cover_image_id="co6def",
        time_to_beat_normally_seconds=46_800,
    )
    other_only = Game(
        steam_app_id=999,
        name="Other library game",
    )
    database_session.add_all(
        [
            _ownership(selected_profile, shared_game, 42),
            _ownership(other_profile, shared_game, 9_999),
            _ownership(selected_profile, selected_unrequested, 60),
            _ownership(other_profile, other_only, 10),
        ]
    )
    database_session.commit()

    result = load_final_result_presentation(
        database_session,
        selected_profile.id,
        selected_steam_app_ids=(620, 999),
        facet_identities=frozenset(),
    )

    assert result.presentations == (
        CandidatePresentationFacts(
            steam_app_id=620,
            title="Portal 2",
            cover_url=(
                "https://images.igdb.com/igdb/image/upload/"
                "t_cover_big/co6abc.jpg"
            ),
            profile_playtime_minutes=42,
            normal_completion_seconds=28_800,
        ),
    )


def test_preserves_unknown_cover_and_completion_time(
    database_session: Session,
) -> None:
    profile = _profile(1)
    game = Game(
        steam_app_id=10,
        name="Mystery Game",
        cover_image_id=None,
        time_to_beat_normally_seconds=None,
    )
    database_session.add(_ownership(profile, game, 0))
    database_session.commit()

    result = load_final_result_presentation(
        database_session,
        profile.id,
        selected_steam_app_ids=(10,),
        facet_identities=frozenset(),
    )

    assert result.presentations[0].cover_url is None
    assert result.presentations[0].profile_playtime_minutes == 0
    assert result.presentations[0].normal_completion_seconds is None


def test_projects_only_requested_labels_in_canonical_order(
    database_session: Session,
) -> None:
    database_session.add_all(
        [
            IGDBMetadataTerm(
                kind="keyword",
                igdb_id=4_928,
                name="Environmental puzzles",
            ),
            IGDBMetadataTerm(
                kind="genre",
                igdb_id=10,
                name="Strategy",
            ),
            IGDBMetadataTerm(
                kind="genre",
                igdb_id=9,
                name="Puzzle",
            ),
            IGDBMetadataTerm(
                kind="theme",
                igdb_id=18,
                name="Science fiction",
            ),
            IGDBMetadataTerm(
                kind="game_mode",
                igdb_id=1,
                name="Single player",
            ),
            IGDBMetadataTerm(
                kind="theme",
                igdb_id=99,
                name="Unrequested theme",
            ),
        ]
    )
    database_session.commit()

    result = load_final_result_presentation(
        database_session,
        profile_id=1,
        selected_steam_app_ids=(),
        facet_identities=frozenset(
            {
                (FacetKind.KEYWORD, 4_928),
                (FacetKind.GAME_MODE, 1),
                (FacetKind.GENRE, 10),
                (FacetKind.THEME, 18),
                (FacetKind.GENRE, 9),
            }
        ),
    )

    assert result.facet_labels == (
        FacetLabel(FacetKind.GENRE, 9, "Puzzle"),
        FacetLabel(FacetKind.GENRE, 10, "Strategy"),
        FacetLabel(FacetKind.THEME, 18, "Science fiction"),
        FacetLabel(FacetKind.KEYWORD, 4_928, "Environmental puzzles"),
        FacetLabel(FacetKind.GAME_MODE, 1, "Single player"),
    )


def test_empty_projection_performs_no_selects(
    database_session: Session,
) -> None:
    statements: list[str] = []

    def record_select(
        connection: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    bind = database_session.get_bind()
    event.listen(bind, "before_cursor_execute", record_select)
    try:
        result = load_final_result_presentation(
            database_session,
            profile_id=1,
            selected_steam_app_ids=(),
            facet_identities=frozenset(),
        )
    finally:
        event.remove(bind, "before_cursor_execute", record_select)

    assert result == FinalResultPresentationProjection(
        presentations=(),
        facet_labels=(),
    )
    assert statements == []


def test_projection_uses_at_most_two_bounded_cache_selects(
    database_session: Session,
) -> None:
    profile = _profile(1)
    game = Game(steam_app_id=620, name="Portal 2")
    label = IGDBMetadataTerm(
        kind="genre",
        igdb_id=9,
        name="Puzzle",
    )
    database_session.add_all([_ownership(profile, game, 42), label])
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
        result = load_final_result_presentation(
            database_session,
            profile.id,
            selected_steam_app_ids=(620,),
            facet_identities=frozenset({(FacetKind.GENRE, 9)}),
        )
    finally:
        event.remove(bind, "before_cursor_execute", record_select)

    assert len(result.presentations) == 1
    assert len(result.facet_labels) == 1
    assert len(statements) == 2
    combined_sql = " ".join(statement.lower() for statement, _ in statements)
    assert "game_trait" not in combined_sql
    assert "summary" not in combined_sql
    assert "time_to_beat_hastily" not in combined_sql
    assert "time_to_beat_completely" not in combined_sql


@pytest.mark.parametrize(
    ("selected_steam_app_ids", "message"),
    [
        ((1, 1), "must be unique"),
        (tuple(range(1, 8)), "at most 6"),
    ],
)
def test_projection_rejects_unbounded_candidate_ids_before_querying(
    database_session: Session,
    selected_steam_app_ids: tuple[int, ...],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        load_final_result_presentation(
            database_session,
            profile_id=1,
            selected_steam_app_ids=selected_steam_app_ids,
            facet_identities=frozenset(),
        )


def test_projection_does_not_autoflush_pending_writes(
    database_session: Session,
) -> None:
    profile = _profile(1)
    database_session.add(profile)
    database_session.commit()
    pending_game = Game(steam_app_id=10, name="Pending")
    database_session.add(_ownership(profile, pending_game, 5))

    result = load_final_result_presentation(
        database_session,
        profile.id,
        selected_steam_app_ids=(10,),
        facet_identities=frozenset(),
    )

    assert result.presentations == ()
    assert pending_game in database_session.new
