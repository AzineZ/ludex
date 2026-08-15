from collections.abc import Generator
from dataclasses import FrozenInstanceError

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
from app.recommendations.reference_reads import (
    FacetOption,
    InvalidSearchQueryError,
    MetadataStatus,
    OwnedGameSuggestion,
    ProfileNotFoundError,
    ReferenceDetails,
    ReferenceFacets,
    ReferenceMetadataUnavailableError,
    ReferenceNotOwnedError,
    load_reference_details,
    normalize_search_query,
    search_owned_games,
    search_reference_keywords,
)


def test_normalizes_surrounding_and_internal_unicode_whitespace() -> None:
    assert normalize_search_query(
        " \tStardew\u2003  Valley\n"
    ) == "Stardew Valley"


def test_preserves_case_punctuation_accents_and_wildcards() -> None:
    assert normalize_search_query(
        "  100%_ Café: Édition  "
    ) == "100%_ Café: Édition"


@pytest.mark.parametrize(
    "query",
    [
        "Q",
        "x" * 100,
    ],
)
def test_accepts_query_length_boundaries(query: str) -> None:
    assert normalize_search_query(query) == query


@pytest.mark.parametrize(
    "query",
    [
        "",
        " \t\u2003\n",
        "x" * 101,
    ],
)
def test_rejects_query_outside_length_boundaries(query: str) -> None:
    with pytest.raises(InvalidSearchQueryError) as caught:
        normalize_search_query(query)

    assert caught.value.code == "invalid_query"
    assert caught.value.field == "query"
    assert str(caught.value) == (
        "Search query must contain between 1 and 100 characters."
    )


@pytest.mark.parametrize("query", [None, True, 10])
def test_rejects_nonstring_queries(query: object) -> None:
    with pytest.raises(InvalidSearchQueryError):
        normalize_search_query(query)


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


def _ownership(profile: Profile, game: Game) -> ProfileGame:
    return ProfileGame(
        profile=profile,
        game=game,
        playtime_minutes=0,
    )


def test_searches_only_owned_games_and_projects_cached_state(
    database_session: Session,
) -> None:
    selected_profile = _profile(1)
    other_profile = _profile(2)
    ready_game = Game(
        steam_app_id=10,
        name="Portal",
        igdb_status="ready",
        cover_image_id="co6abc",
    )
    missing_game = Game(
        steam_app_id=20,
        name="Portal Stories: Mel",
        igdb_status="missing",
    )
    unowned_game = Game(
        steam_app_id=30,
        name="Portal 2",
        igdb_status="ready",
        cover_image_id="co6xyz",
    )
    database_session.add_all(
        [
            _ownership(selected_profile, ready_game),
            _ownership(selected_profile, missing_game),
            _ownership(other_profile, unowned_game),
        ]
    )
    database_session.commit()

    results = search_owned_games(
        database_session,
        selected_profile.id,
        " \tPORTAL  ",
    )

    assert results == (
        OwnedGameSuggestion(
            steam_app_id=10,
            name="Portal",
            cover_url=(
                "https://images.igdb.com/igdb/image/upload/"
                "t_cover_big/co6abc.jpg"
            ),
            metadata_status=MetadataStatus.READY,
        ),
        OwnedGameSuggestion(
            steam_app_id=20,
            name="Portal Stories: Mel",
            cover_url=None,
            metadata_status=MetadataStatus.MISSING,
        ),
    )


def test_unknown_profile_is_not_an_empty_search(
    database_session: Session,
) -> None:
    with pytest.raises(ProfileNotFoundError) as caught:
        search_owned_games(database_session, 999, "Portal")

    assert caught.value.code == "profile_not_found"
    assert caught.value.field == "profile_id"
    assert str(caught.value) == "The selected profile does not exist."


def test_existing_profile_with_no_matches_returns_empty_tuple(
    database_session: Session,
) -> None:
    profile = _profile(1)
    game = Game(
        steam_app_id=10,
        name="Portal",
        igdb_status="ready",
    )
    database_session.add(_ownership(profile, game))
    database_session.commit()

    assert search_owned_games(
        database_session,
        profile.id,
        "Stardew",
    ) == ()


def test_owned_game_search_uses_at_most_two_queries(
    database_session: Session,
) -> None:
    profile = _profile(1)
    game = Game(
        steam_app_id=10,
        name="Portal",
        igdb_status="ready",
    )
    database_session.add(_ownership(profile, game))
    database_session.commit()

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
        search_owned_games(database_session, profile.id, "Portal")
    finally:
        event.remove(bind, "before_cursor_execute", record_select)

    assert len(statements) <= 2


def test_orders_exact_prefix_and_substring_match_tiers(
    database_session: Session,
) -> None:
    profile = _profile(1)
    games = [
        Game(steam_app_id=90, name="Portal", igdb_status="ready"),
        Game(steam_app_id=80, name="Portal 2", igdb_status="ready"),
        Game(
            steam_app_id=70,
            name="Portal Stories",
            igdb_status="ready",
        ),
        Game(
            steam_app_id=60,
            name="Portal Stories",
            igdb_status="ready",
        ),
        Game(
            steam_app_id=75,
            name="Portal Reloaded",
            igdb_status="ready",
        ),
        Game(
            steam_app_id=50,
            name="Aperture Portal",
            igdb_status="ready",
        ),
        Game(
            steam_app_id=40,
            name="The Portal",
            igdb_status="ready",
        ),
    ]
    database_session.add_all(
        [_ownership(profile, game) for game in games]
    )
    database_session.commit()

    results = search_owned_games(
        database_session,
        profile.id,
        "portal",
    )

    assert [
        result.steam_app_id for result in results
    ] == [90, 80, 75, 60, 70, 50, 40]


def test_treats_sql_wildcards_as_literal_text(
    database_session: Session,
) -> None:
    profile = _profile(1)
    games = [
        Game(
            steam_app_id=10,
            name="100% Orange Juice",
            igdb_status="ready",
        ),
        Game(
            steam_app_id=20,
            name="100X Orange Juice",
            igdb_status="ready",
        ),
        Game(
            steam_app_id=30,
            name="Under_score",
            igdb_status="ready",
        ),
        Game(
            steam_app_id=40,
            name="UnderXscore",
            igdb_status="ready",
        ),
    ]
    database_session.add_all(
        [_ownership(profile, game) for game in games]
    )
    database_session.commit()

    percent_results = search_owned_games(
        database_session,
        profile.id,
        "%",
    )
    underscore_results = search_owned_games(
        database_session,
        profile.id,
        "_",
    )

    assert [
        result.steam_app_id for result in percent_results
    ] == [10]
    assert [
        result.steam_app_id for result in underscore_results
    ] == [30]


def test_limits_owned_game_suggestions_to_ten(
    database_session: Session,
) -> None:
    profile = _profile(1)
    games = [
        Game(
            steam_app_id=100 + index,
            name=f"Portal {index:02d}",
            igdb_status="ready",
        )
        for index in range(12)
    ]
    database_session.add_all(
        [_ownership(profile, game) for game in games]
    )
    database_session.commit()

    results = search_owned_games(
        database_session,
        profile.id,
        "Portal",
    )

    assert len(results) == 10
    assert [
        result.steam_app_id for result in results
    ] == list(range(100, 110))


@pytest.mark.parametrize(
    ("stored_status", "expected_status"),
    [
        ("pending", MetadataStatus.PENDING),
        ("ready", MetadataStatus.READY),
        ("missing", MetadataStatus.MISSING),
        ("ambiguous", MetadataStatus.AMBIGUOUS),
    ],
)
def test_projects_every_factual_metadata_status(
    database_session: Session,
    stored_status: str,
    expected_status: MetadataStatus,
) -> None:
    profile = _profile(1)
    game = Game(
        steam_app_id=10,
        name="Portal",
        igdb_status=stored_status,
    )
    database_session.add(_ownership(profile, game))
    database_session.commit()

    results = search_owned_games(
        database_session,
        profile.id,
        "Portal",
    )

    assert results[0].metadata_status is expected_status


def _term(
    kind: str,
    igdb_id: int,
    name: str,
) -> GameIGDBMetadataTerm:
    return GameIGDBMetadataTerm(
        term=IGDBMetadataTerm(
            kind=kind,
            igdb_id=igdb_id,
            name=name,
        )
    )


def test_loads_ready_reference_details_with_sorted_direct_facets(
    database_session: Session,
) -> None:
    profile = _profile(1)
    game = Game(
        steam_app_id=10,
        name="Reference Game",
        igdb_status="ready",
        cover_image_id="co6abc",
    )
    game.metadata_term_links.extend(
        [
            _term("genre", 2, "Adventure"),
            _term("genre", 3, "action"),
            _term("genre", 5, "Action"),
            _term("theme", 20, "Fantasy"),
            _term("game_mode", 30, "Single player"),
            _term("keyword", 40, "Ignored keyword"),
        ]
    )
    database_session.add(_ownership(profile, game))
    database_session.commit()

    result = load_reference_details(
        database_session,
        profile.id,
        game.steam_app_id,
    )

    assert result == ReferenceDetails(
        steam_app_id=10,
        name="Reference Game",
        cover_url=(
            "https://images.igdb.com/igdb/image/upload/"
            "t_cover_big/co6abc.jpg"
        ),
        metadata_status=MetadataStatus.READY,
        facets=ReferenceFacets(
            genres=(
                FacetOption(id=5, name="Action"),
                FacetOption(id=3, name="action"),
                FacetOption(id=2, name="Adventure"),
            ),
            themes=(
                FacetOption(id=20, name="Fantasy"),
            ),
            game_modes=(
                FacetOption(id=30, name="Single player"),
            ),
        ),
    )


def test_ready_reference_preserves_empty_optional_facets(
    database_session: Session,
) -> None:
    profile = _profile(1)
    game = Game(
        steam_app_id=10,
        name="Sparse Reference",
        igdb_status="ready",
    )
    game.metadata_term_links.append(
        _term("genre", 2, "Adventure")
    )
    database_session.add(_ownership(profile, game))
    database_session.commit()

    result = load_reference_details(
        database_session,
        profile.id,
        game.steam_app_id,
    )

    assert result.cover_url is None
    assert result.facets.themes == ()
    assert result.facets.game_modes == ()


def test_reference_detail_rejects_unknown_profile(
    database_session: Session,
) -> None:
    with pytest.raises(ProfileNotFoundError):
        load_reference_details(database_session, 999, 10)


def test_reference_detail_rejects_unowned_or_unknown_game(
    database_session: Session,
) -> None:
    selected_profile = _profile(1)
    other_profile = _profile(2)
    unowned_game = Game(
        steam_app_id=10,
        name="Other Library Game",
        igdb_status="ready",
    )
    database_session.add_all(
        [
            selected_profile,
            _ownership(other_profile, unowned_game),
        ]
    )
    database_session.commit()

    for steam_app_id in (10, 999):
        with pytest.raises(ReferenceNotOwnedError) as caught:
            load_reference_details(
                database_session,
                selected_profile.id,
                steam_app_id,
            )

        assert caught.value.code == "reference_not_owned"
        assert caught.value.field == "steam_app_id"
        assert str(caught.value) == (
            "The selected reference game is not owned by this profile."
        )


@pytest.mark.parametrize(
    "metadata_status",
    ["pending", "missing", "ambiguous"],
)
def test_reference_detail_rejects_unavailable_metadata(
    database_session: Session,
    metadata_status: str,
) -> None:
    profile = _profile(1)
    game = Game(
        steam_app_id=10,
        name="Unavailable Reference",
        igdb_status=metadata_status,
    )
    database_session.add(_ownership(profile, game))
    database_session.commit()

    with pytest.raises(
        ReferenceMetadataUnavailableError
    ) as caught:
        load_reference_details(
            database_session,
            profile.id,
            game.steam_app_id,
        )

    assert caught.value.code == "reference_metadata_unavailable"
    assert caught.value.field == "steam_app_id"
    assert str(caught.value) == (
        "Factual metadata is unavailable for this reference game."
    )


def test_reference_detail_uses_at_most_three_queries(
    database_session: Session,
) -> None:
    profile = _profile(1)
    game = Game(
        steam_app_id=10,
        name="Reference Game",
        igdb_status="ready",
    )
    game.metadata_term_links.extend(
        [
            _term("genre", 2, "Adventure"),
            _term("theme", 20, "Fantasy"),
            _term("game_mode", 30, "Single player"),
        ]
    )
    database_session.add(_ownership(profile, game))
    database_session.commit()

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
        load_reference_details(
            database_session,
            profile.id,
            game.steam_app_id,
        )
    finally:
        event.remove(bind, "before_cursor_execute", record_select)

    assert len(statements) <= 3


def test_searches_keywords_scoped_to_exact_owned_reference(
    database_session: Session,
) -> None:
    profile = _profile(1)
    reference = Game(
        steam_app_id=10,
        name="Reference Game",
        igdb_status="ready",
    )
    reference.metadata_term_links.extend(
        [
            _term("keyword", 10, "Farm"),
            _term("keyword", 40, "Farm"),
            _term("keyword", 20, "Farming"),
            _term("keyword", 30, "Space Farm"),
            _term("genre", 50, "Farm"),
        ]
    )
    other_game = Game(
        steam_app_id=20,
        name="Other Reference",
        igdb_status="ready",
    )
    other_game.metadata_term_links.append(
        _term("keyword", 60, "Farm")
    )
    database_session.add_all(
        [
            _ownership(profile, reference),
            _ownership(profile, other_game),
        ]
    )
    database_session.commit()

    results = search_reference_keywords(
        database_session,
        profile.id,
        reference.steam_app_id,
        " \tFARM ",
    )

    assert results == (
        FacetOption(id=10, name="Farm"),
        FacetOption(id=40, name="Farm"),
        FacetOption(id=20, name="Farming"),
        FacetOption(id=30, name="Space Farm"),
    )


def test_ready_reference_without_keywords_returns_empty_tuple(
    database_session: Session,
) -> None:
    profile = _profile(1)
    reference = Game(
        steam_app_id=10,
        name="Reference Game",
        igdb_status="ready",
    )
    reference.metadata_term_links.append(
        _term("genre", 2, "Adventure")
    )
    database_session.add(_ownership(profile, reference))
    database_session.commit()

    assert search_reference_keywords(
        database_session,
        profile.id,
        reference.steam_app_id,
        "Farm",
    ) == ()


def test_keyword_search_rejects_unknown_profile(
    database_session: Session,
) -> None:
    with pytest.raises(ProfileNotFoundError):
        search_reference_keywords(
            database_session,
            999,
            10,
            "Farm",
        )


def test_keyword_search_rejects_unowned_reference(
    database_session: Session,
) -> None:
    selected_profile = _profile(1)
    other_profile = _profile(2)
    reference = Game(
        steam_app_id=10,
        name="Other Reference",
        igdb_status="ready",
    )
    database_session.add_all(
        [
            selected_profile,
            _ownership(other_profile, reference),
        ]
    )
    database_session.commit()

    with pytest.raises(ReferenceNotOwnedError):
        search_reference_keywords(
            database_session,
            selected_profile.id,
            reference.steam_app_id,
            "Farm",
        )


@pytest.mark.parametrize(
    "metadata_status",
    ["pending", "missing", "ambiguous"],
)
def test_keyword_search_rejects_unavailable_metadata(
    database_session: Session,
    metadata_status: str,
) -> None:
    profile = _profile(1)
    reference = Game(
        steam_app_id=10,
        name="Unavailable Reference",
        igdb_status=metadata_status,
    )
    database_session.add(_ownership(profile, reference))
    database_session.commit()

    with pytest.raises(ReferenceMetadataUnavailableError):
        search_reference_keywords(
            database_session,
            profile.id,
            reference.steam_app_id,
            "Farm",
        )


def test_keyword_search_uses_at_most_three_queries(
    database_session: Session,
) -> None:
    profile = _profile(1)
    reference = Game(
        steam_app_id=10,
        name="Reference Game",
        igdb_status="ready",
    )
    reference.metadata_term_links.append(
        _term("keyword", 10, "Farm")
    )
    database_session.add(_ownership(profile, reference))
    database_session.commit()

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
        search_reference_keywords(
            database_session,
            profile.id,
            reference.steam_app_id,
            "Farm",
        )
    finally:
        event.remove(bind, "before_cursor_execute", record_select)

    assert len(statements) <= 3


def test_keyword_search_treats_sql_wildcards_as_literals(
    database_session: Session,
) -> None:
    profile = _profile(1)
    reference = Game(
        steam_app_id=10,
        name="Reference Game",
        igdb_status="ready",
    )
    reference.metadata_term_links.extend(
        [
            _term("keyword", 10, "100% Complete"),
            _term("keyword", 20, "100X Complete"),
            _term("keyword", 30, "Under_score"),
            _term("keyword", 40, "UnderXscore"),
        ]
    )
    database_session.add(_ownership(profile, reference))
    database_session.commit()

    percent_results = search_reference_keywords(
        database_session,
        profile.id,
        reference.steam_app_id,
        "%",
    )
    underscore_results = search_reference_keywords(
        database_session,
        profile.id,
        reference.steam_app_id,
        "_",
    )

    assert percent_results == (
        FacetOption(id=10, name="100% Complete"),
    )
    assert underscore_results == (
        FacetOption(id=30, name="Under_score"),
    )


def test_limits_keyword_suggestions_to_ten(
    database_session: Session,
) -> None:
    profile = _profile(1)
    reference = Game(
        steam_app_id=10,
        name="Reference Game",
        igdb_status="ready",
    )
    reference.metadata_term_links.extend(
        _term(
            "keyword",
            100 + index,
            f"Tag {index:02d}",
        )
        for index in range(12)
    )
    database_session.add(_ownership(profile, reference))
    database_session.commit()

    results = search_reference_keywords(
        database_session,
        profile.id,
        reference.steam_app_id,
        "Tag",
    )

    assert len(results) == 10
    assert [
        result.id for result in results
    ] == list(range(100, 110))


def test_read_results_are_immutable(
    database_session: Session,
) -> None:
    profile = _profile(1)
    reference = Game(
        steam_app_id=10,
        name="Reference Game",
        igdb_status="ready",
    )
    database_session.add(_ownership(profile, reference))
    database_session.commit()

    result = search_owned_games(
        database_session,
        profile.id,
        "Reference",
    )[0]

    with pytest.raises(FrozenInstanceError):
        result.name = "Changed"


def test_reference_reads_do_not_flush_commit_or_roll_back(
    database_session: Session,
) -> None:
    profile = _profile(1)
    reference = Game(
        steam_app_id=10,
        name="Reference Game",
        igdb_status="ready",
    )
    reference.metadata_term_links.extend(
        [
            _term("genre", 2, "Adventure"),
            _term("keyword", 10, "Farm"),
        ]
    )
    database_session.add(_ownership(profile, reference))
    database_session.commit()

    transaction_events: list[str] = []

    def record_flush(
        session: Session,
        flush_context: object,
        instances: object,
    ) -> None:
        transaction_events.append("flush")

    def record_commit(session: Session) -> None:
        transaction_events.append("commit")

    def record_rollback(session: Session) -> None:
        transaction_events.append("rollback")

    event.listen(database_session, "before_flush", record_flush)
    event.listen(database_session, "after_commit", record_commit)
    event.listen(database_session, "after_rollback", record_rollback)

    try:
        search_owned_games(
            database_session,
            profile.id,
            "Reference",
        )
        load_reference_details(
            database_session,
            profile.id,
            reference.steam_app_id,
        )
        search_reference_keywords(
            database_session,
            profile.id,
            reference.steam_app_id,
            "Farm",
        )
    finally:
        event.remove(database_session, "before_flush", record_flush)
        event.remove(database_session, "after_commit", record_commit)
        event.remove(
            database_session,
            "after_rollback",
            record_rollback,
        )

    assert transaction_events == []
    assert not database_session.new
    assert not database_session.dirty
    assert not database_session.deleted
