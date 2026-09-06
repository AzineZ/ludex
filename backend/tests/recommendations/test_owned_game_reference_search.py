import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.models import Game
from app.recommendations.reference_reads import (
    MetadataStatus,
    OwnedGameSuggestion,
    ProfileNotFoundError,
    search_owned_games,
)
from tests.recommendations.reference_read_support import (
    database_session,
    _ownership,
    _profile,
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
