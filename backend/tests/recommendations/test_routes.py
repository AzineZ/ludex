from collections.abc import Generator
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_database_session
from app.main import app
from app.models import (
    Game,
    GameIGDBMetadataTerm,
    IGDBMetadataTerm,
    Profile,
    ProfileGame,
)
from app.recommendations.routes import router


@dataclass(frozen=True)
class RecommendationAPI:
    """Provide the HTTP client and database handles used by route tests."""

    client: TestClient
    database_session: Session
    engine: Engine


@pytest.fixture
def recommendation_api() -> Generator[RecommendationAPI, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )
    Base.metadata.create_all(engine)

    def override_database_session() -> Generator[Session, None, None]:
        with session_factory() as database_session:
            yield database_session

    app.dependency_overrides[
        get_database_session
    ] = override_database_session

    try:
        with session_factory() as database_session:
            with TestClient(app) as client:
                yield RecommendationAPI(
                    client=client,
                    database_session=database_session,
                    engine=engine,
                )
    finally:
        app.dependency_overrides.pop(get_database_session, None)
        engine.dispose()


def _profile(profile_id: int = 1) -> Profile:
    return Profile(
        id=profile_id,
        steam_id=str(76561198000000000 + profile_id),
        display_name=f"Player {profile_id}",
    )


def _term_link(
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


def _owned_game(
    profile: Profile,
    steam_app_id: int,
    name: str,
    *,
    status: str = "ready",
    cover_image_id: str | None = None,
    playtime_minutes: int = 0,
    normal_completion_seconds: int | None = None,
    links: tuple[GameIGDBMetadataTerm, ...] = (),
) -> Game:
    game = Game(
        steam_app_id=steam_app_id,
        name=name,
        igdb_status=status,
        cover_image_id=cover_image_id,
        time_to_beat_normally_seconds=normal_completion_seconds,
    )
    game.metadata_term_links.extend(links)
    game.profile_games.append(
        ProfileGame(
            profile=profile,
            playtime_minutes=playtime_minutes,
        )
    )
    return game


def _valid_preference_body(
    steam_app_id: int = 100,
    *,
    genre_ids: list[int] | None = None,
) -> dict[str, Any]:
    return {
        "references": [
            {
                "steam_app_id": steam_app_id,
                "facets": {
                    "genre_ids": genre_ids or [10],
                    "theme_ids": [],
                    "keyword_ids": [],
                    "game_mode_ids": [],
                },
            }
        ],
        "constraints": {
            "maximum_completion_minutes": None,
            "play_status": "either",
        },
    }


def _valid_refinement_body(
    rejected_steam_app_ids: list[object] | None = None,
) -> dict[str, Any]:
    return {
        "preference": _valid_preference_body(),
        "rejected_steam_app_ids": rejected_steam_app_ids or [],
    }


def _assert_error(
    response: Any,
    *,
    status_code: int,
    code: str,
    field: str,
    message: str,
) -> None:
    assert response.status_code == status_code
    assert response.json() == {
        "error": {
            "code": code,
            "field": field,
            "message": message,
        }
    }


def test_router_uses_confirmed_profile_scoped_prefix() -> None:
    assert router.prefix == "/profiles/{profile_id}/recommendations"
    assert router.tags == ["recommendations"]


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
        "/profiles/1/recommendations/references",
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
        "/profiles/1/recommendations/references",
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
        "/profiles/1/recommendations/references/100"
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
        "/profiles/1/recommendations/references/100/keywords",
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
        "/profiles/1/recommendations/references/100/keywords/browse"
    )

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {"id": 20, "name": "Atmospheric"},
            {"id": 30, "name": "story rich"},
        ],
        "truncated": False,
    }


def test_validate_preference_returns_canonical_direct_object(
    recommendation_api: RecommendationAPI,
) -> None:
    profile = _profile()
    recommendation_api.database_session.add(
        _owned_game(
            profile,
            100,
            "Reference Game",
            links=(
                _term_link("genre", 10, "Adventure"),
                _term_link("genre", 20, "Role-playing"),
            ),
        )
    )
    recommendation_api.database_session.commit()
    request_body = _valid_preference_body(
        genre_ids=[20, 10]
    )

    response = recommendation_api.client.post(
        "/profiles/1/recommendations/preferences/validate",
        json=request_body,
    )

    assert response.status_code == 200
    assert response.json() == {
        "references": [
            {
                "steam_app_id": 100,
                "facets": {
                    "genre_ids": [10, 20],
                    "theme_ids": [],
                    "keyword_ids": [],
                    "game_mode_ids": [],
                },
            }
        ],
        "constraints": {
            "maximum_completion_minutes": None,
            "play_status": "either",
        },
    }


def _add_recommendation_library(
    recommendation_api: RecommendationAPI,
    candidate_count: int,
) -> None:
    profile = _profile()
    genre = IGDBMetadataTerm(
        kind="genre",
        igdb_id=10,
        name="Adventure",
    )
    reference = _owned_game(
        profile,
        100,
        "Reference Game",
        links=(GameIGDBMetadataTerm(term=genre),),
    )
    candidates = tuple(
        _owned_game(
            profile,
            200 + index,
            f"Candidate {index}",
            cover_image_id=("candidate-cover" if index == 1 else None),
            playtime_minutes=index,
            normal_completion_seconds=3_600,
            links=(GameIGDBMetadataTerm(term=genre),),
        )
        for index in range(1, candidate_count + 1)
    )
    recommendation_api.database_session.add_all(
        (reference, *candidates)
    )
    recommendation_api.database_session.commit()


@pytest.mark.parametrize(
    ("candidate_count", "expected_outcome"),
    [
        (0, "empty"),
        (2, "sparse"),
        (6, "complete"),
    ],
)
def test_final_recommendation_endpoint_returns_every_success_outcome(
    recommendation_api: RecommendationAPI,
    candidate_count: int,
    expected_outcome: str,
) -> None:
    _add_recommendation_library(recommendation_api, candidate_count)

    response = recommendation_api.client.post(
        "/profiles/1/recommendations",
        json=_valid_preference_body(),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["outcome"] == expected_outcome
    assert payload["eligible_count"] == candidate_count
    assert payload["returned_count"] == candidate_count
    assert [item["rank"] for item in payload["items"]] == list(
        range(1, candidate_count + 1)
    )
    assert [item["steam_app_id"] for item in payload["items"]] == list(
        range(201, 201 + candidate_count)
    )
    if payload["items"]:
        first = payload["items"][0]
        assert first["title"] == "Candidate 1"
        assert first["profile_playtime_minutes"] == 1
        assert first["normal_completion_seconds"] == 3_600
        assert first["factual_evidence"] == {
            "version": "factual-overlap-v1",
            "score_basis_points": 10_000,
            "active_budget": 30,
            "contributions": [
                {
                    "reference_steam_app_id": 100,
                    "facet_kind": "genre",
                    "facet_igdb_id": 10,
                    "match_state": "matched",
                    "points_numerator": 10_000,
                    "points_denominator": 1,
                }
            ],
        }
        assert first["facet_labels"] == [
            {
                "facet_kind": "genre",
                "facet_igdb_id": 10,
                "name": "Adventure",
            }
        ]
        assert first["match_summary"] == {
            "reasons": [
                {
                    "facet_kind": "genre",
                    "facet_igdb_id": 10,
                    "name": "Adventure",
                    "reference_steam_app_ids": [100],
                    "points_numerator": 10_000,
                    "points_denominator": 1,
                }
            ],
            "additional_match_count": 0,
            "text": "Matches your Adventure preference.",
        }
        assert first["tradeoff"] is None


def test_refinement_endpoint_excludes_rejected_games(
    recommendation_api: RecommendationAPI,
) -> None:
    _add_recommendation_library(recommendation_api, 6)

    response = recommendation_api.client.post(
        "/profiles/1/recommendations/refine",
        json=_valid_refinement_body([201, 203]),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["outcome"] == "sparse"
    assert payload["eligible_count"] == 4
    assert payload["returned_count"] == 4
    assert [item["steam_app_id"] for item in payload["items"]] == [
        202,
        204,
        205,
        206,
    ]


def test_refinement_endpoint_accepts_an_empty_exclusion_set(
    recommendation_api: RecommendationAPI,
) -> None:
    _add_recommendation_library(recommendation_api, 2)

    response = recommendation_api.client.post(
        "/profiles/1/recommendations/refine",
        json=_valid_refinement_body(),
    )

    assert response.status_code == 200
    assert response.json()["returned_count"] == 2


def test_refinement_endpoint_accepts_exactly_thirty_exclusions(
    recommendation_api: RecommendationAPI,
) -> None:
    _add_recommendation_library(recommendation_api, 2)

    response = recommendation_api.client.post(
        "/profiles/1/recommendations/refine",
        json=_valid_refinement_body(list(range(1_000, 1_030))),
    )

    assert response.status_code == 200
    assert response.json()["returned_count"] == 2


@pytest.mark.parametrize(
    (
        "rejected_steam_app_ids",
        "expected_code",
        "expected_field",
        "expected_message",
    ),
    [
        (
            [201, 201],
            "duplicate_rejected_game",
            "rejected_steam_app_ids[1]",
            "Rejected game IDs must be unique.",
        ),
        (
            list(range(1, 32)),
            "too_many_rejected_games",
            "rejected_steam_app_ids",
            "A session may exclude at most 30 rejected games.",
        ),
        (
            [True],
            "invalid_type",
            "rejected_steam_app_ids[0]",
            "This field has an invalid type.",
        ),
        (
            [0],
            "invalid_value",
            "rejected_steam_app_ids[0]",
            "IDs must be positive integers.",
        ),
    ],
)
def test_refinement_rejects_invalid_exclusion_lists(
    recommendation_api: RecommendationAPI,
    rejected_steam_app_ids: list[object],
    expected_code: str,
    expected_field: str,
    expected_message: str,
) -> None:
    response = recommendation_api.client.post(
        "/profiles/1/recommendations/refine",
        json=_valid_refinement_body(rejected_steam_app_ids),
    )

    _assert_error(
        response,
        status_code=422,
        code=expected_code,
        field=expected_field,
        message=expected_message,
    )


def test_refinement_requires_the_bounded_exclusion_field(
    recommendation_api: RecommendationAPI,
) -> None:
    response = recommendation_api.client.post(
        "/profiles/1/recommendations/refine",
        json={"preference": _valid_preference_body()},
    )

    _assert_error(
        response,
        status_code=422,
        code="missing_field",
        field="rejected_steam_app_ids",
        message="This field is required.",
    )


def test_final_recommendation_endpoint_maps_preference_failure(
    recommendation_api: RecommendationAPI,
) -> None:
    response = recommendation_api.client.post(
        "/profiles/999/recommendations",
        json=_valid_preference_body(),
    )

    _assert_error(
        response,
        status_code=404,
        code="profile_not_found",
        field="profile_id",
        message="The selected profile does not exist.",
    )


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/profiles/1/recommendations", _valid_preference_body()),
        (
            "/profiles/1/recommendations/refine",
            _valid_refinement_body([201]),
        ),
    ],
)
def test_recommendation_requests_are_bounded_read_only_and_cache_only(
    recommendation_api: RecommendationAPI,
    path: str,
    body: dict[str, Any],
) -> None:
    _add_recommendation_library(recommendation_api, 6)
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
            path,
            json=body,
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
    writes = [
        statement
        for statement in statements
        if statement.lstrip().upper().startswith(
            ("INSERT", "UPDATE", "DELETE")
        )
    ]
    assert len(selects) == 5
    assert writes == []
    combined_sql = " ".join(statement.lower() for statement in selects)
    assert "game_trait" not in combined_sql
    assert "gemini" not in combined_sql


def test_search_rejects_unknown_profile(
    recommendation_api: RecommendationAPI,
) -> None:
    response = recommendation_api.client.get(
        "/profiles/999/recommendations/references",
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
        "/profiles/1/recommendations/references",
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
            "/profiles/1/recommendations/references/"
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
        "/profiles/1/recommendations/references/100",
        (
            "/profiles/1/recommendations/references/100/keywords"
            "?query=game"
        ),
        (
            "/profiles/1/recommendations/references/100/"
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


def test_validation_maps_unknown_profile_to_not_found(
    recommendation_api: RecommendationAPI,
) -> None:
    response = recommendation_api.client.post(
        "/profiles/999/recommendations/preferences/validate",
        json=_valid_preference_body(),
    )

    _assert_error(
        response,
        status_code=404,
        code="profile_not_found",
        field="profile_id",
        message="The selected profile does not exist.",
    )


def test_validation_maps_unowned_reference_to_not_found(
    recommendation_api: RecommendationAPI,
) -> None:
    recommendation_api.database_session.add(_profile())
    recommendation_api.database_session.commit()

    response = recommendation_api.client.post(
        "/profiles/1/recommendations/preferences/validate",
        json=_valid_preference_body(),
    )

    _assert_error(
        response,
        status_code=404,
        code="reference_not_owned",
        field="references[0].steam_app_id",
        message=(
            "The selected reference game is not owned by this profile."
        ),
    )


def test_validation_maps_unavailable_metadata_to_conflict(
    recommendation_api: RecommendationAPI,
) -> None:
    profile = _profile()
    recommendation_api.database_session.add(
        _owned_game(
            profile,
            100,
            "Unavailable Reference",
            status="pending",
        )
    )
    recommendation_api.database_session.commit()

    response = recommendation_api.client.post(
        "/profiles/1/recommendations/preferences/validate",
        json=_valid_preference_body(),
    )

    _assert_error(
        response,
        status_code=409,
        code="reference_metadata_unavailable",
        field="references[0].steam_app_id",
        message=(
            "Factual metadata is unavailable for this reference game."
        ),
    )


def test_validation_maps_invalid_membership_to_unprocessable(
    recommendation_api: RecommendationAPI,
) -> None:
    profile = _profile()
    recommendation_api.database_session.add(
        _owned_game(profile, 100, "Reference Game")
    )
    recommendation_api.database_session.commit()

    response = recommendation_api.client.post(
        "/profiles/1/recommendations/preferences/validate",
        json=_valid_preference_body(),
    )

    _assert_error(
        response,
        status_code=422,
        code="facet_not_on_reference",
        field="references[0].facets.genre_ids[0]",
        message=(
            "The selected facet does not belong to this reference game."
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
            "/profiles/not-an-id/recommendations/references?query=a",
            "invalid_type",
            "profile_id",
            "This field has an invalid type.",
        ),
        (
            "/profiles/0/recommendations/references?query=a",
            "invalid_value",
            "profile_id",
            "IDs must be positive integers.",
        ),
        (
            "/profiles/1/recommendations/references/not-an-id",
            "invalid_type",
            "steam_app_id",
            "This field has an invalid type.",
        ),
        (
            "/profiles/1/recommendations/references/-1",
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
        "/profiles/1/recommendations/references",
        (
            "/profiles/1/recommendations/references/100/keywords"
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


def _structural_request_case(case_name: str) -> object:
    body = deepcopy(_valid_preference_body())
    reference = body["references"][0]
    facets = reference["facets"]
    constraints = body["constraints"]

    if case_name == "missing_references":
        del body["references"]
    elif case_name == "unexpected_top_level":
        body["unexpected"] = True
    elif case_name == "references_wrong_type":
        body["references"] = "not-a-list"
    elif case_name == "invalid_reference_count":
        body["references"] = []
    elif case_name == "duplicate_reference":
        body["references"].append(deepcopy(reference))
    elif case_name == "steam_id_wrong_type":
        reference["steam_app_id"] = True
    elif case_name == "steam_id_not_positive":
        reference["steam_app_id"] = 0
    elif case_name == "missing_facet_array":
        del facets["theme_ids"]
    elif case_name == "unexpected_facet":
        facets["unexpected"] = []
    elif case_name == "facet_id_wrong_type":
        facets["genre_ids"] = [True]
    elif case_name == "facet_id_not_positive":
        facets["genre_ids"] = [0]
    elif case_name == "duplicate_facet":
        facets["genre_ids"] = [10, 10]
    elif case_name == "empty_facets":
        facets["genre_ids"] = []
    elif case_name == "too_many_keywords":
        facets["genre_ids"] = []
        facets["keyword_ids"] = [1, 2, 3, 4]
    elif case_name == "missing_constraint":
        del constraints["maximum_completion_minutes"]
    elif case_name == "completion_wrong_type":
        constraints["maximum_completion_minutes"] = True
    elif case_name == "completion_out_of_range":
        constraints["maximum_completion_minutes"] = 29
    elif case_name == "invalid_play_status":
        constraints["play_status"] = "sometimes"
    elif case_name == "unexpected_constraint":
        constraints["unexpected"] = True
    elif case_name == "non_object_body":
        return []
    else:
        raise AssertionError(f"Unknown structural case: {case_name}")

    return body


@pytest.mark.parametrize(
    (
        "case_name",
        "expected_code",
        "expected_field",
        "expected_message",
    ),
    [
        (
            "missing_references",
            "missing_field",
            "references",
            "This field is required.",
        ),
        (
            "unexpected_top_level",
            "unexpected_field",
            "unexpected",
            "Unexpected fields are not allowed.",
        ),
        (
            "references_wrong_type",
            "invalid_type",
            "references",
            "This field has an invalid type.",
        ),
        (
            "invalid_reference_count",
            "invalid_reference_count",
            "references",
            "Select between one and three reference games.",
        ),
        (
            "duplicate_reference",
            "duplicate_reference",
            "references[1].steam_app_id",
            "Reference games must be unique.",
        ),
        (
            "steam_id_wrong_type",
            "invalid_type",
            "references[0].steam_app_id",
            "This field has an invalid type.",
        ),
        (
            "steam_id_not_positive",
            "invalid_value",
            "references[0].steam_app_id",
            "IDs must be positive integers.",
        ),
        (
            "missing_facet_array",
            "missing_field",
            "references[0].facets.theme_ids",
            "This field is required.",
        ),
        (
            "unexpected_facet",
            "unexpected_field",
            "references[0].facets.unexpected",
            "Unexpected fields are not allowed.",
        ),
        (
            "facet_id_wrong_type",
            "invalid_type",
            "references[0].facets.genre_ids[0]",
            "This field has an invalid type.",
        ),
        (
            "facet_id_not_positive",
            "invalid_value",
            "references[0].facets.genre_ids[0]",
            "IDs must be positive integers.",
        ),
        (
            "duplicate_facet",
            "duplicate_facet",
            "references[0].facets.genre_ids[1]",
            "Facet IDs must be unique within their category.",
        ),
        (
            "empty_facets",
            "empty_reference_facets",
            "references[0].facets",
            "Select at least one facet from this reference game.",
        ),
        (
            "too_many_keywords",
            "too_many_keywords",
            "references[0].facets.keyword_ids",
            "Select no more than three keywords per reference game.",
        ),
        (
            "missing_constraint",
            "missing_field",
            "constraints.maximum_completion_minutes",
            "This field is required.",
        ),
        (
            "completion_wrong_type",
            "invalid_type",
            "constraints.maximum_completion_minutes",
            "This field has an invalid type.",
        ),
        (
            "completion_out_of_range",
            "invalid_value",
            "constraints.maximum_completion_minutes",
            (
                "Maximum completion time must be between 30 and "
                "60000 minutes."
            ),
        ),
        (
            "invalid_play_status",
            "invalid_value",
            "constraints.play_status",
            (
                "Play status must be unplayed, previously_played, "
                "or either."
            ),
        ),
        (
            "unexpected_constraint",
            "unexpected_field",
            "constraints.unexpected",
            "Unexpected fields are not allowed.",
        ),
        (
            "non_object_body",
            "invalid_type",
            "body",
            "The request body must be a JSON object.",
        ),
    ],
)
def test_validation_translates_structural_request_failures(
    recommendation_api: RecommendationAPI,
    case_name: str,
    expected_code: str,
    expected_field: str,
    expected_message: str,
) -> None:
    response = recommendation_api.client.post(
        "/profiles/1/recommendations/preferences/validate",
        json=_structural_request_case(case_name),
    )

    _assert_error(
        response,
        status_code=422,
        code=expected_code,
        field=expected_field,
        message=expected_message,
    )


def test_validation_rejects_missing_body(
    recommendation_api: RecommendationAPI,
) -> None:
    response = recommendation_api.client.post(
        "/profiles/1/recommendations/preferences/validate"
    )

    _assert_error(
        response,
        status_code=422,
        code="missing_field",
        field="body",
        message="This field is required.",
    )


def test_validation_rejects_invalid_json(
    recommendation_api: RecommendationAPI,
) -> None:
    response = recommendation_api.client.post(
        "/profiles/1/recommendations/preferences/validate",
        content=b'{"references": [}',
        headers={"content-type": "application/json"},
    )

    _assert_error(
        response,
        status_code=422,
        code="invalid_type",
        field="body",
        message="The request body must be a JSON object.",
    )


def test_routes_are_read_only(
    recommendation_api: RecommendationAPI,
) -> None:
    profile = _profile()
    recommendation_api.database_session.add(
        _owned_game(
            profile,
            100,
            "Reference Game",
            links=(
                _term_link("genre", 10, "Adventure"),
                _term_link("keyword", 20, "Exploration"),
            ),
        )
    )
    recommendation_api.database_session.commit()

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

    event.listen(Session, "before_flush", record_flush)
    event.listen(Session, "after_commit", record_commit)
    event.listen(Session, "after_rollback", record_rollback)

    try:
        responses = [
            recommendation_api.client.get(
                "/profiles/1/recommendations/references",
                params={"query": "reference"},
            ),
            recommendation_api.client.get(
                "/profiles/1/recommendations/references/100"
            ),
            recommendation_api.client.get(
                (
                    "/profiles/1/recommendations/references/100/"
                    "keywords"
                ),
                params={"query": "explore"},
            ),
            recommendation_api.client.get(
                (
                    "/profiles/1/recommendations/references/100/"
                    "keywords/browse"
                )
            ),
            recommendation_api.client.post(
                (
                    "/profiles/1/recommendations/preferences/"
                    "validate"
                ),
                json=_valid_preference_body(),
            ),
        ]
    finally:
        event.remove(Session, "before_flush", record_flush)
        event.remove(Session, "after_commit", record_commit)
        event.remove(Session, "after_rollback", record_rollback)

    assert [response.status_code for response in responses] == [
        200,
        200,
        200,
        200,
        200,
    ]
    assert transaction_events == []


def test_openapi_declares_recommendation_contracts(
    recommendation_api: RecommendationAPI,
) -> None:
    schema = recommendation_api.client.get("/openapi.json").json()
    paths = schema["paths"]

    search = paths[
        "/profiles/{profile_id}/recommendations/references"
    ]["get"]
    detail = paths[
        (
            "/profiles/{profile_id}/recommendations/references/"
            "{steam_app_id}"
        )
    ]["get"]
    keywords = paths[
        (
            "/profiles/{profile_id}/recommendations/references/"
            "{steam_app_id}/keywords"
        )
    ]["get"]
    keyword_browse = paths[
        (
            "/profiles/{profile_id}/recommendations/references/"
            "{steam_app_id}/keywords/browse"
        )
    ]["get"]
    validation = paths[
        (
            "/profiles/{profile_id}/recommendations/preferences/"
            "validate"
        )
    ]["post"]
    refinement = paths[
        "/profiles/{profile_id}/recommendations/refine"
    ]["post"]

    assert set(search["responses"]) == {"200", "404", "422"}
    assert set(detail["responses"]) == {
        "200",
        "404",
        "409",
        "422",
    }
    assert set(keywords["responses"]) == {
        "200",
        "404",
        "409",
        "422",
    }
    assert set(keyword_browse["responses"]) == {
        "200",
        "404",
        "409",
        "422",
    }
    assert set(validation["responses"]) == {
        "200",
        "404",
        "409",
        "422",
    }
    assert set(refinement["responses"]) == {
        "200",
        "404",
        "409",
        "422",
    }

    validation_request_schema = validation["requestBody"][
        "content"
    ]["application/json"]["schema"]
    validation_success_schema = validation["responses"]["200"][
        "content"
    ]["application/json"]["schema"]

    assert validation_request_schema["$ref"].endswith(
        "/RecommendationPreference"
    )
    assert validation_success_schema["$ref"].endswith(
        "/RecommendationPreference"
    )
    refinement_request_schema = refinement["requestBody"][
        "content"
    ]["application/json"]["schema"]
    refinement_success_schema = refinement["responses"]["200"][
        "content"
    ]["application/json"]["schema"]
    assert refinement_request_schema["$ref"].endswith(
        "/RecommendationRefinementRequest"
    )
    assert refinement_success_schema["$ref"].endswith(
        "/FinalRecommendationResponse"
    )

    assert all(
        response["content"]["application/json"]["schema"][
            "$ref"
        ].endswith("/RecommendationErrorResponse")
        for operation in (
            search,
            detail,
            keywords,
            validation,
            refinement,
        )
        for status_code, response in operation["responses"].items()
        if status_code != "200"
    )
