import pytest
from sqlalchemy import event

from tests.recommendations.recommendation_api_support import (
    RecommendationAPI,
    _assert_error,
    _owned_game,
    _profile,
    _term_link,
    recommendation_api,
)


def test_search_owned_references_returns_items_envelope(
    recommendation_api: RecommendationAPI,
) -> None:
    profile = _profile()
    recommendation_api.database_session.add_all(
        [
            _owned_game(
                profile,
                100,
                "Alpha Game",
                cover_image_id="cover100",
            ),
            _owned_game(
                profile,
                200,
                "Alpha Missing",
                status="missing",
            ),
            _owned_game(profile, 300, "Unrelated"),
        ]
    )
    recommendation_api.database_session.commit()

    response = recommendation_api.client.get(
        "/recommendations/references",
        params={"query": "  alpha  "},
    )

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "steam_app_id": 100,
                "name": "Alpha Game",
                "cover_url": (
                    "https://images.igdb.com/igdb/image/upload/"
                    "t_cover_big/cover100.jpg"
                ),
                "metadata_status": "ready",
            },
            {
                "steam_app_id": 200,
                "name": "Alpha Missing",
                "cover_url": None,
                "metadata_status": "missing",
            },
        ]
    }

def test_search_owned_references_returns_empty_items(
    recommendation_api: RecommendationAPI,
) -> None:
    recommendation_api.database_session.add(_profile())
    recommendation_api.database_session.commit()

    response = recommendation_api.client.get(
        "/recommendations/references",
        params={"query": "no match"},
    )

    assert response.status_code == 200
    assert response.json() == {"items": []}

def test_get_reference_details_returns_direct_object(
    recommendation_api: RecommendationAPI,
) -> None:
    profile = _profile()
    recommendation_api.database_session.add(
        _owned_game(
            profile,
            100,
            "Reference Game",
            cover_image_id="reference-cover",
            links=(
                _term_link("genre", 10, "Adventure"),
                _term_link("theme", 20, "Fantasy"),
                _term_link("keyword", 30, "Exploration"),
                _term_link("game_mode", 40, "Single player"),
            ),
        )
    )
    recommendation_api.database_session.commit()

    response = recommendation_api.client.get(
        "/recommendations/references/100"
    )

    assert response.status_code == 200
    assert response.json() == {
        "steam_app_id": 100,
        "name": "Reference Game",
        "cover_url": (
            "https://images.igdb.com/igdb/image/upload/"
            "t_cover_big/reference-cover.jpg"
        ),
        "metadata_status": "ready",
        "facets": {
            "genres": [{"id": 10, "name": "Adventure"}],
            "themes": [{"id": 20, "name": "Fantasy"}],
            "game_modes": [
                {"id": 40, "name": "Single player"}
            ],
        },
    }

def test_search_reference_keywords_returns_items_envelope(
    recommendation_api: RecommendationAPI,
) -> None:
    profile = _profile()
    recommendation_api.database_session.add(
        _owned_game(
            profile,
            100,
            "Reference Game",
            links=(
                _term_link("keyword", 20, "Exploration"),
                _term_link("keyword", 30, "Explosive"),
                _term_link("keyword", 40, "Farming"),
            ),
        )
    )
    recommendation_api.database_session.commit()

    response = recommendation_api.client.get(
        "/recommendations/references/100/keywords",
        params={"query": "explo"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {"id": 20, "name": "Exploration"},
            {"id": 30, "name": "Explosive"},
        ]
    }

def test_browse_reference_keywords_returns_bounded_envelope(
    recommendation_api: RecommendationAPI,
) -> None:
    profile = _profile()
    recommendation_api.database_session.add(
        _owned_game(
            profile,
            100,
            "Reference Game",
            links=(
                _term_link("keyword", 30, "story rich"),
                _term_link("keyword", 20, "Atmospheric"),
                _term_link("genre", 10, "Adventure"),
            ),
        )
    )
    recommendation_api.database_session.commit()

    response = recommendation_api.client.get(
        "/recommendations/references/100/keywords/browse"
    )

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {"id": 20, "name": "Atmospheric"},
            {"id": 30, "name": "story rich"},
        ],
        "truncated": False,
    }

def test_search_rejects_unknown_profile(
    recommendation_api: RecommendationAPI,
) -> None:
    response = recommendation_api.client.get(
        "/recommendations/references",
        params={"query": "game"},
    )

    _assert_error(
        response,
        status_code=404,
        code="profile_not_found",
        field="profile_id",
        message="The selected profile does not exist.",
    )

def test_search_rejects_invalid_normalized_query(
    recommendation_api: RecommendationAPI,
) -> None:
    response = recommendation_api.client.get(
        "/recommendations/references",
        params={"query": "   \t  "},
    )

    _assert_error(
        response,
        status_code=422,
        code="invalid_query",
        field="query",
        message=(
            "Search query must contain between 1 and 100 characters."
        ),
    )

def test_reference_detail_hides_unknown_and_unowned_identically(
    recommendation_api: RecommendationAPI,
) -> None:
    selected_profile = _profile(1)
    other_profile = _profile(2)
    recommendation_api.database_session.add(
        _owned_game(
            other_profile,
            200,
            "Other Profile Game",
            links=(_term_link("genre", 10, "Adventure"),),
        )
    )
    recommendation_api.database_session.add(selected_profile)
    recommendation_api.database_session.commit()

    for steam_app_id in (200, 999):
        response = recommendation_api.client.get(
            "/recommendations/references/"
            f"{steam_app_id}"
        )

        _assert_error(
            response,
            status_code=404,
            code="reference_not_owned",
            field="steam_app_id",
            message=(
                "The selected reference game is not owned by this "
                "profile."
            ),
        )

@pytest.mark.parametrize(
    "endpoint",
    [
        "/recommendations/references/100",
        (
            "/recommendations/references/100/keywords"
            "?query=game"
        ),
        (
            "/recommendations/references/100/"
            "keywords/browse"
        ),
    ],
)
def test_reference_reads_map_unavailable_metadata_to_conflict(
    recommendation_api: RecommendationAPI,
    endpoint: str,
) -> None:
    profile = _profile()
    recommendation_api.database_session.add(
        _owned_game(
            profile,
            100,
            "Unavailable Reference",
            status="ambiguous",
        )
    )
    recommendation_api.database_session.commit()

    response = recommendation_api.client.get(endpoint)

    _assert_error(
        response,
        status_code=409,
        code="reference_metadata_unavailable",
        field="steam_app_id",
        message=(
            "Factual metadata is unavailable for this reference game."
        ),
    )

@pytest.mark.parametrize(
    (
        "path",
        "expected_code",
        "expected_field",
        "expected_message",
    ),
    [
        (
            "/recommendations/references/not-an-id",
            "invalid_type",
            "steam_app_id",
            "This field has an invalid type.",
        ),
        (
            "/recommendations/references/-1",
            "invalid_value",
            "steam_app_id",
            "IDs must be positive integers.",
        ),
    ],
)
def test_rejects_invalid_path_identifiers_without_querying(
    recommendation_api: RecommendationAPI,
    path: str,
    expected_code: str,
    expected_field: str,
    expected_message: str,
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

    event.listen(
        recommendation_api.engine,
        "before_cursor_execute",
        record_select,
    )
    try:
        response = recommendation_api.client.get(path)
    finally:
        event.remove(
            recommendation_api.engine,
            "before_cursor_execute",
            record_select,
        )

    assert statements == []
    _assert_error(
        response,
        status_code=422,
        code=expected_code,
        field=expected_field,
        message=expected_message,
    )

@pytest.mark.parametrize(
    "path",
    [
        "/recommendations/references",
        (
            "/recommendations/references/100/keywords"
        ),
    ],
)
def test_rejects_missing_search_query(
    recommendation_api: RecommendationAPI,
    path: str,
) -> None:
    response = recommendation_api.client.get(path)

    _assert_error(
        response,
        status_code=422,
        code="missing_field",
        field="query",
        message="This field is required.",
    )
