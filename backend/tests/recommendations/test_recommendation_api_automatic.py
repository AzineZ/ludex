from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import event

from app.main import app
from app.models import GameIGDBMetadataTerm, IGDBMetadataTerm
from app.recommendations.automatic import (
    PlayedGame,
    is_meta_keyword,
    rank_played_games,
)
from app.sessions.http import require_access_session
from tests.recommendations.recommendation_api_support import (
    RecommendationAPI,
    _assert_error,
    _owned_game,
    _profile,
    recommendation_api,
)


def _constraints(
    play_status: str = "unplayed",
    maximum_completion_minutes: int | None = None,
) -> dict[str, Any]:
    return {
        "maximum_completion_minutes": maximum_completion_minutes,
        "play_status": play_status,
    }


def _automatic_body(
    *,
    play_status: str = "unplayed",
    maximum_completion_minutes: int | None = None,
    rejected_steam_app_ids: list[object] | None = None,
    wait_for_pending: bool = True,
) -> dict[str, Any]:
    return {
        "constraints": _constraints(
            play_status,
            maximum_completion_minutes,
        ),
        "rejected_steam_app_ids": rejected_steam_app_ids or [],
        "wait_for_pending": wait_for_pending,
    }


def _more_like_body(
    steam_app_id: int,
    excluded_steam_app_ids: list[object] | None = None,
) -> dict[str, Any]:
    return {
        "steam_app_id": steam_app_id,
        "constraints": _constraints(),
        "excluded_steam_app_ids": excluded_steam_app_ids or [],
    }


REFERENCE_TIME = datetime(2026, 10, 1, tzinfo=UTC)


def _days_before_reference(days: int) -> datetime:
    return REFERENCE_TIME - timedelta(days=days)


def _played(
    steam_app_id: int,
    playtime_minutes: int,
    *,
    days_since_played: int | None = 0,
    normal_completion_hours: int | None = None,
) -> PlayedGame:
    return PlayedGame(
        steam_app_id=steam_app_id,
        title=f"Game {steam_app_id}",
        cover_url=None,
        igdb_status="ready",
        playtime_minutes=playtime_minutes,
        last_played_at=(
            None
            if days_since_played is None
            else _days_before_reference(days_since_played)
        ),
        normal_completion_seconds=(
            None
            if normal_completion_hours is None
            else normal_completion_hours * 3_600
        ),
    )


def _add_played_library(
    recommendation_api: RecommendationAPI,
    *,
    beta_status: str = "ready",
    candidate_count: int = 20,
) -> None:
    profile = _profile()
    adventure = IGDBMetadataTerm(kind="genre", igdb_id=10, name="Adventure")
    single_player = IGDBMetadataTerm(
        kind="game_mode",
        igdb_id=30,
        name="Single player",
    )

    def links(*terms: IGDBMetadataTerm) -> tuple[GameIGDBMetadataTerm, ...]:
        return tuple(GameIGDBMetadataTerm(term=term) for term in terms)

    games = [
        _owned_game(
            profile,
            101,
            "Alpha",
            playtime_minutes=600,
            last_played_at=_days_before_reference(90),
            links=links(adventure, single_player),
        ),
        _owned_game(
            profile,
            102,
            "Beta",
            status=beta_status,
            playtime_minutes=300,
            last_played_at=_days_before_reference(0),
            links=(
                links(adventure)
                if beta_status == "ready"
                else ()
            ),
        ),
        _owned_game(
            profile,
            103,
            "Gamma",
            playtime_minutes=500,
            last_played_at=_days_before_reference(180),
            links=links(adventure),
        ),
        _owned_game(
            profile,
            104,
            "Delta",
            status="missing",
            playtime_minutes=400,
            last_played_at=_days_before_reference(1),
        ),
        _owned_game(
            profile,
            105,
            "Barely Played",
            playtime_minutes=30,
            links=links(adventure),
        ),
    ]
    games.extend(
        _owned_game(
            profile,
            200 + index,
            f"Candidate {index}",
            normal_completion_seconds=3_600 * index,
            links=links(adventure),
        )
        for index in range(1, candidate_count + 1)
    )
    recommendation_api.database_session.add_all(games)
    recommendation_api.database_session.commit()


def _row_ids(row: dict[str, Any]) -> list[int]:
    return [
        item["steam_app_id"]
        for item in row["recommendations"]["items"]
    ]


def test_ranking_favours_recent_and_finished_games_over_old_hours() -> None:
    ranked = rank_played_games(
        (
            _played(1, 600),
            _played(2, 6_000, days_since_played=365),
            _played(3, 300, normal_completion_hours=4),
            _played(4, 300, normal_completion_hours=10),
            _played(6, 120, days_since_played=90),
            _played(7, 120, days_since_played=90),
            _played(8, 6_000, days_since_played=None),
            _played(9, 59),
        ),
        REFERENCE_TIME,
    )

    # 5 h just finished > 10 h today > 5 h unfinished today > 2 h three
    # months ago > 100 h a year ago > no play date; under an hour is ignored.
    assert [game.steam_app_id for game in ranked] == [3, 1, 4, 6, 7, 2, 8]


def test_interest_halves_every_ninety_days_and_rewards_a_finish() -> None:
    today = _played(1, 420)
    three_months = _played(1, 420, days_since_played=90)
    finished = _played(1, 420, normal_completion_hours=7)
    played_after_sync = PlayedGame(
        steam_app_id=1,
        title="Game 1",
        cover_url=None,
        igdb_status="ready",
        playtime_minutes=420,
        last_played_at=REFERENCE_TIME + timedelta(days=3),
        normal_completion_seconds=None,
    )

    assert today.interest_score(REFERENCE_TIME) == 3.0
    assert three_months.interest_score(REFERENCE_TIME) == 1.5
    assert finished.looks_finished
    assert finished.interest_score(REFERENCE_TIME) == 4.5
    assert played_after_sync.interest_score(REFERENCE_TIME) == 3.0
    assert not _played(1, 420, normal_completion_hours=0).looks_finished


def test_automatic_rows_follow_top_played_games_without_repeats(
    recommendation_api: RecommendationAPI,
) -> None:
    _add_played_library(recommendation_api)

    response = recommendation_api.client.post(
        "/recommendations/automatic",
        json=_automatic_body(),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert [row["source_game"] for row in payload["rows"]] == [
        {
            "steam_app_id": 102,
            "title": "Beta",
            "cover_url": None,
            "playtime_minutes": 300,
            "achievement_percent": None,
        },
        {
            "steam_app_id": 101,
            "title": "Alpha",
            "cover_url": None,
            "playtime_minutes": 600,
            "achievement_percent": None,
        },
        {
            "steam_app_id": 103,
            "title": "Gamma",
            "cover_url": None,
            "playtime_minutes": 500,
            "achievement_percent": None,
        },
    ]
    row_ids = [_row_ids(row) for row in payload["rows"]]
    assert row_ids == [
        list(range(201, 207)),
        list(range(207, 213)),
        list(range(213, 219)),
    ]
    assert payload["suggested_preference"] == {
        "references": [
            {
                "steam_app_id": 102,
                "facets": {
                    "genre_ids": [10],
                    "theme_ids": [],
                    "keyword_ids": [],
                    "game_mode_ids": [],
                },
            },
            {
                "steam_app_id": 101,
                "facets": {
                    "genre_ids": [10],
                    "theme_ids": [],
                    "keyword_ids": [],
                    "game_mode_ids": [],
                },
            },
            {
                "steam_app_id": 103,
                "facets": {
                    "genre_ids": [10],
                    "theme_ids": [],
                    "keyword_ids": [],
                    "game_mode_ids": [],
                },
            },
        ],
        "constraints": _constraints(),
    }


def test_automatic_rows_are_deterministic_and_restore_after_toggling(
    recommendation_api: RecommendationAPI,
) -> None:
    _add_played_library(recommendation_api)

    first = recommendation_api.client.post(
        "/recommendations/automatic",
        json=_automatic_body(),
    ).json()
    limited = recommendation_api.client.post(
        "/recommendations/automatic",
        json=_automatic_body(maximum_completion_minutes=300),
    ).json()
    restored = recommendation_api.client.post(
        "/recommendations/automatic",
        json=_automatic_body(),
    ).json()

    assert restored == first
    assert [_row_ids(row) for row in limited["rows"]] == [
        [201, 202, 203, 204, 205],
        [],
        [],
    ]
    assert limited["suggested_preference"]["constraints"] == _constraints(
        maximum_completion_minutes=300
    )


def test_automatic_rows_apply_play_status_and_rejected_games(
    recommendation_api: RecommendationAPI,
) -> None:
    _add_played_library(recommendation_api)

    response = recommendation_api.client.post(
        "/recommendations/automatic",
        json=_automatic_body(
            play_status="previously_played",
            rejected_steam_app_ids=[105],
        ),
    )

    assert response.status_code == 200
    # Only played games remain, and every played game is a source,
    # rejected, or unknown to the IGDB facets.
    assert [_row_ids(row) for row in response.json()["rows"]] == [
        [104],
        [],
        [],
    ]


def test_pending_top_game_reports_preparing_until_waiting_is_declined(
    recommendation_api: RecommendationAPI,
) -> None:
    _add_played_library(recommendation_api, beta_status="pending")

    waiting = recommendation_api.client.post(
        "/recommendations/automatic",
        json=_automatic_body(),
    )
    not_waiting = recommendation_api.client.post(
        "/recommendations/automatic",
        json=_automatic_body(wait_for_pending=False),
    )

    assert waiting.status_code == 200
    assert waiting.json() == {
        "status": "preparing",
        "rows": [],
        "suggested_preference": None,
    }
    assert [
        row["source_game"]["steam_app_id"]
        for row in not_waiting.json()["rows"]
    ] == [101, 103]


def test_library_without_qualifying_played_games_is_unavailable(
    recommendation_api: RecommendationAPI,
) -> None:
    profile = _profile()
    recommendation_api.database_session.add_all(
        (
            _owned_game(profile, 101, "Short", playtime_minutes=59),
            _owned_game(
                profile,
                102,
                "No facets",
                playtime_minutes=600,
            ),
            _owned_game(
                profile,
                103,
                "Missing",
                status="missing",
                playtime_minutes=600,
            ),
        )
    )
    recommendation_api.database_session.commit()

    response = recommendation_api.client.post(
        "/recommendations/automatic",
        json=_automatic_body(),
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "unavailable",
        "rows": [],
        "suggested_preference": None,
    }


def _add_facet_library(
    recommendation_api: RecommendationAPI,
    source_terms: tuple[IGDBMetadataTerm, ...],
    other_game_terms: tuple[tuple[IGDBMetadataTerm, ...], ...],
) -> None:
    profile = _profile()
    games = [
        _owned_game(
            profile,
            101,
            "Source",
            playtime_minutes=600,
            links=tuple(GameIGDBMetadataTerm(term=term) for term in source_terms),
        )
    ]
    games.extend(
        _owned_game(
            profile,
            200 + index,
            f"Candidate {index}",
            links=tuple(GameIGDBMetadataTerm(term=term) for term in terms),
        )
        for index, terms in enumerate(other_game_terms)
    )
    recommendation_api.database_session.add_all(games)
    recommendation_api.database_session.commit()


def _source_facets(recommendation_api: RecommendationAPI) -> dict[str, Any]:
    response = recommendation_api.client.post(
        "/recommendations/automatic",
        json=_automatic_body(),
    )
    assert response.status_code == 200
    return response.json()["suggested_preference"]["references"][0]["facets"]


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("steam achievements", True),
        ("achievements", True),
        ("the game awards - best audio design - winner", True),
        ("xbox one x enhanced", True),
        ("regional censorship", True),
        ("steam deck", True),
        ("controller support", True),
        ("steampunk", False),
        ("wild west", False),
        ("cowboys", False),
    ],
)
def test_store_and_platform_keywords_are_recognised(
    name: str,
    expected: bool,
) -> None:
    assert is_meta_keyword(name) is expected


def test_source_keywords_prefer_the_rarest_shared_play_keywords(
    recommendation_api: RecommendationAPI,
) -> None:
    def keyword(igdb_id: int, name: str) -> IGDBMetadataTerm:
        return IGDBMetadataTerm(kind="keyword", igdb_id=igdb_id, name=name)

    western = keyword(40, "western")
    cowboys = keyword(41, "cowboys")
    achievements = keyword(42, "steam achievements")
    unique = keyword(43, "unique to the source")
    action = keyword(44, "action-adventure")
    bear = keyword(45, "bear")
    steampunk = keyword(46, "steampunk")
    _add_facet_library(
        recommendation_api,
        (western, cowboys, achievements, unique, action, bear, steampunk),
        (
            (western, cowboys, achievements, action, bear, steampunk),
            (cowboys, achievements, action, bear, steampunk),
            (action, bear),
            (),
        ),
    )

    # Other owners: western 1, cowboys 2, steampunk 2, action and bear 3.
    assert _source_facets(recommendation_api)["keyword_ids"] == [40, 41, 46]


def test_source_facets_drop_library_wide_genres_themes_and_game_modes(
    recommendation_api: RecommendationAPI,
) -> None:
    adventure = IGDBMetadataTerm(kind="genre", igdb_id=10, name="Adventure")
    shooter = IGDBMetadataTerm(kind="genre", igdb_id=11, name="Shooter")
    action = IGDBMetadataTerm(kind="theme", igdb_id=20, name="Action")
    western = IGDBMetadataTerm(kind="theme", igdb_id=21, name="Western")
    single_player = IGDBMetadataTerm(
        kind="game_mode",
        igdb_id=30,
        name="Single player",
    )
    _add_facet_library(
        recommendation_api,
        (adventure, shooter, action, western, single_player),
        (
            (adventure, action, single_player),
            (adventure, action, single_player),
            (adventure, shooter, western, single_player),
        ),
    )

    # Adventure and Action are on all four ready games; exactly half is kept.
    assert _source_facets(recommendation_api) == {
        "genre_ids": [11],
        "theme_ids": [21],
        "keyword_ids": [],
        "game_mode_ids": [],
    }


def test_source_facets_fall_back_to_common_genres_and_themes(
    recommendation_api: RecommendationAPI,
) -> None:
    adventure = IGDBMetadataTerm(kind="genre", igdb_id=10, name="Adventure")
    action = IGDBMetadataTerm(kind="theme", igdb_id=20, name="Action")
    _add_facet_library(
        recommendation_api,
        (adventure, action),
        ((adventure, action), (adventure, action)),
    )

    assert _source_facets(recommendation_api) == {
        "genre_ids": [10],
        "theme_ids": [20],
        "keyword_ids": [],
        "game_mode_ids": [],
    }


def test_game_with_only_game_modes_is_not_a_source(
    recommendation_api: RecommendationAPI,
) -> None:
    single_player = IGDBMetadataTerm(
        kind="game_mode",
        igdb_id=30,
        name="Single player",
    )
    _add_facet_library(
        recommendation_api,
        (single_player,),
        ((single_player,),),
    )

    response = recommendation_api.client.post(
        "/recommendations/automatic",
        json=_automatic_body(),
    )

    assert response.json()["status"] == "unavailable"


def test_automatic_rows_use_a_bounded_number_of_selects(
    recommendation_api: RecommendationAPI,
) -> None:
    _add_played_library(recommendation_api)
    statements: list[str] = []

    def record_statement(
        connection: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        statements.append(statement)

    event.listen(
        recommendation_api.engine,
        "before_cursor_execute",
        record_statement,
    )
    try:
        response = recommendation_api.client.post(
            "/recommendations/automatic",
            json=_automatic_body(),
        )
    finally:
        event.remove(
            recommendation_api.engine,
            "before_cursor_execute",
            record_statement,
        )

    assert response.status_code == 200
    selects = [
        statement
        for statement in statements
        if statement.lstrip().upper().startswith("SELECT")
    ]
    # Ranking and facets need four; each row needs at most five.
    assert len(selects) <= 19
    assert len(statements) == len(selects)


def test_more_like_this_uses_one_game_and_skips_shown_games(
    recommendation_api: RecommendationAPI,
) -> None:
    _add_played_library(recommendation_api)

    response = recommendation_api.client.post(
        "/recommendations/automatic/more-like-this",
        json=_more_like_body(203, [201, 202, 204]),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source_game"] == {
        "steam_app_id": 203,
        "title": "Candidate 3",
        "cover_url": None,
        "playtime_minutes": 0,
        "achievement_percent": None,
    }
    assert _row_ids(payload) == [205, 206, 207, 208, 209, 210]


def test_more_like_this_rejects_unowned_and_unready_games(
    recommendation_api: RecommendationAPI,
) -> None:
    _add_played_library(recommendation_api, beta_status="pending")

    unowned = recommendation_api.client.post(
        "/recommendations/automatic/more-like-this",
        json=_more_like_body(999),
    )
    pending = recommendation_api.client.post(
        "/recommendations/automatic/more-like-this",
        json=_more_like_body(102),
    )

    _assert_error(
        unowned,
        status_code=404,
        code="reference_not_owned",
        field="steam_app_id",
        message="The selected reference game is not owned by this profile.",
    )
    _assert_error(
        pending,
        status_code=409,
        code="reference_metadata_unavailable",
        field="steam_app_id",
        message="Factual metadata is unavailable for this reference game.",
    )


def test_automatic_requests_validate_bounded_exclusions(
    recommendation_api: RecommendationAPI,
) -> None:
    too_many_rejected = recommendation_api.client.post(
        "/recommendations/automatic",
        json=_automatic_body(
            rejected_steam_app_ids=list(range(1, 32)),
        ),
    )
    too_many_excluded = recommendation_api.client.post(
        "/recommendations/automatic/more-like-this",
        json=_more_like_body(101, list(range(1, 62))),
    )
    duplicate_excluded = recommendation_api.client.post(
        "/recommendations/automatic/more-like-this",
        json=_more_like_body(101, [5, 6, 5]),
    )
    invalid_excluded = recommendation_api.client.post(
        "/recommendations/automatic/more-like-this",
        json=_more_like_body(101, [0]),
    )
    non_boolean_wait = recommendation_api.client.post(
        "/recommendations/automatic",
        json={**_automatic_body(), "wait_for_pending": "yes"},
    )

    _assert_error(
        too_many_rejected,
        status_code=422,
        code="too_many_rejected_games",
        field="rejected_steam_app_ids",
        message="A session may exclude at most 30 rejected games.",
    )
    _assert_error(
        too_many_excluded,
        status_code=422,
        code="too_many_excluded_games",
        field="excluded_steam_app_ids",
        message="A request may exclude at most 60 shown games.",
    )
    _assert_error(
        duplicate_excluded,
        status_code=422,
        code="duplicate_excluded_game",
        field="excluded_steam_app_ids[2]",
        message="Excluded game IDs must be unique.",
    )
    _assert_error(
        invalid_excluded,
        status_code=422,
        code="invalid_value",
        field="excluded_steam_app_ids[0]",
        message="IDs must be positive integers.",
    )
    _assert_error(
        non_boolean_wait,
        status_code=422,
        code="invalid_type",
        field="wait_for_pending",
        message="This field has an invalid type.",
    )


def test_automatic_routes_require_access_session(
    recommendation_api: RecommendationAPI,
) -> None:
    app.dependency_overrides.pop(require_access_session, None)
    try:
        automatic = recommendation_api.client.post(
            "/recommendations/automatic",
            json=_automatic_body(),
        )
        more_like = recommendation_api.client.post(
            "/recommendations/automatic/more-like-this",
            json=_more_like_body(101),
        )
    finally:
        app.dependency_overrides[
            require_access_session
        ] = recommendation_api.access_session_override

    assert automatic.status_code == 401
    assert more_like.status_code == 401
