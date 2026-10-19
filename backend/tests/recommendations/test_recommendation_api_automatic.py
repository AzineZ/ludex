from datetime import UTC, datetime
from typing import Any

from sqlalchemy import event

from app.main import app
from app.models import GameIGDBMetadataTerm, IGDBMetadataTerm
from app.recommendations.automatic import PlayedGame, rank_played_games
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


def _played(
    steam_app_id: int,
    playtime_minutes: int,
    *,
    recent_playtime_minutes: int | None = None,
    last_played_at: datetime | None = None,
) -> PlayedGame:
    return PlayedGame(
        steam_app_id=steam_app_id,
        title=f"Game {steam_app_id}",
        cover_url=None,
        igdb_status="ready",
        playtime_minutes=playtime_minutes,
        recent_playtime_minutes=recent_playtime_minutes,
        last_played_at=last_played_at,
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
            links=links(adventure, single_player),
        ),
        _owned_game(
            profile,
            102,
            "Beta",
            status=beta_status,
            playtime_minutes=300,
            recent_playtime_minutes=100,
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
            links=links(adventure),
        ),
        _owned_game(
            profile,
            104,
            "Delta",
            status="missing",
            playtime_minutes=400,
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


def test_ranking_weights_recent_play_and_breaks_ties_deterministically() -> None:
    earlier = datetime(2026, 10, 1, tzinfo=UTC)
    later = datetime(2026, 10, 10, tzinfo=UTC)
    ranked = rank_played_games(
        (
            _played(1, 600),
            _played(2, 300, recent_playtime_minutes=100),
            _played(3, 500, last_played_at=earlier),
            _played(4, 500, last_played_at=later),
            _played(5, 500),
            _played(6, 400),
            _played(7, 59, recent_playtime_minutes=1_000),
        )
    )

    assert [game.steam_app_id for game in ranked] == [2, 1, 4, 3, 5, 6]


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
        },
        {
            "steam_app_id": 101,
            "title": "Alpha",
            "cover_url": None,
            "playtime_minutes": 600,
        },
        {
            "steam_app_id": 103,
            "title": "Gamma",
            "cover_url": None,
            "playtime_minutes": 500,
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
                    "game_mode_ids": [30],
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


def test_source_keywords_prefer_those_most_shared_in_the_library(
    recommendation_api: RecommendationAPI,
) -> None:
    profile = _profile()
    keywords = {
        keyword_id: IGDBMetadataTerm(
            kind="keyword",
            igdb_id=keyword_id,
            name=f"Keyword {keyword_id}",
        )
        for keyword_id in (40, 41, 42, 43, 44)
    }
    other_owner_counts = {40: 2, 41: 3, 42: 3, 43: 0, 44: 2}
    games = [
        _owned_game(
            profile,
            101,
            "Source",
            playtime_minutes=600,
            links=tuple(
                GameIGDBMetadataTerm(term=term)
                for term in keywords.values()
            ),
        )
    ]
    for index in range(3):
        games.append(
            _owned_game(
                profile,
                200 + index,
                f"Candidate {index}",
                links=tuple(
                    GameIGDBMetadataTerm(term=keywords[keyword_id])
                    for keyword_id, count in other_owner_counts.items()
                    if index < count
                ),
            )
        )
    recommendation_api.database_session.add_all(games)
    recommendation_api.database_session.commit()

    response = recommendation_api.client.post(
        "/recommendations/automatic",
        json=_automatic_body(),
    )

    reference = response.json()["suggested_preference"]["references"][0]
    assert reference["facets"]["keyword_ids"] == [40, 41, 42]


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
    # Ranking and facets need three; each row needs at most five.
    assert len(selects) <= 18
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
        message="More like this may exclude at most 60 shown games.",
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
