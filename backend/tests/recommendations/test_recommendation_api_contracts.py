from sqlalchemy import event
from sqlalchemy.orm import Session

from tests.recommendations.recommendation_api_support import (
    RecommendationAPI,
    _owned_game,
    _profile,
    _term_link,
    _valid_preference_body,
    recommendation_api,
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
                "/recommendations/references",
                params={"query": "reference"},
            ),
            recommendation_api.client.get(
                "/recommendations/references/100"
            ),
            recommendation_api.client.get(
                (
                    "/recommendations/references/100/"
                    "keywords"
                ),
                params={"query": "explore"},
            ),
            recommendation_api.client.get(
                (
                    "/recommendations/references/100/"
                    "keywords/browse"
                )
            ),
            recommendation_api.client.post(
                (
                    "/recommendations/preferences/"
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

    recommendation = paths["/recommendations"]["post"]
    search = paths[
        "/recommendations/references"
    ]["get"]
    detail = paths[
        (
            "/recommendations/references/"
            "{steam_app_id}"
        )
    ]["get"]
    keywords = paths[
        (
            "/recommendations/references/"
            "{steam_app_id}/keywords"
        )
    ]["get"]
    keyword_browse = paths[
        (
            "/recommendations/references/"
            "{steam_app_id}/keywords/browse"
        )
    ]["get"]
    validation = paths[
        (
            "/recommendations/preferences/"
            "validate"
        )
    ]["post"]
    refinement = paths[
        "/recommendations/refine"
    ]["post"]

    assert set(recommendation["responses"]) == {
        "200",
        "401",
        "404",
        "409",
        "422",
        "503",
    }
    assert set(search["responses"]) == {
        "200",
        "401",
        "404",
        "422",
        "503",
    }
    assert set(detail["responses"]) == {
        "200",
        "401",
        "404",
        "409",
        "422",
        "503",
    }
    assert set(keywords["responses"]) == {
        "200",
        "401",
        "404",
        "409",
        "422",
        "503",
    }
    assert set(keyword_browse["responses"]) == {
        "200",
        "401",
        "404",
        "409",
        "422",
        "503",
    }
    assert set(validation["responses"]) == {
        "200",
        "401",
        "404",
        "409",
        "422",
        "503",
    }
    assert set(refinement["responses"]) == {
        "200",
        "401",
        "404",
        "409",
        "422",
        "503",
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
            recommendation,
            search,
            detail,
            keywords,
            keyword_browse,
            validation,
            refinement,
        )
        for status_code, response in operation["responses"].items()
        if status_code not in {"200", "401"}
    )
