import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.models import Game
from app.recommendations.reference_reads import (
    KEYWORD_BROWSE_LIMIT,
    FacetOption,
    KeywordBrowse,
    ProfileNotFoundError,
    ReferenceMetadataUnavailableError,
    ReferenceNotOwnedError,
    browse_reference_keywords,
    search_reference_keywords,
)
from tests.recommendations.reference_read_support import (
    database_session,
    _ownership,
    _profile,
    _term,
)


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

def test_browses_all_reference_keywords_in_stable_name_order(
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
            _term("keyword", 30, "story rich"),
            _term("keyword", 20, "Atmospheric"),
            _term("keyword", 10, "atmospheric"),
            _term("genre", 40, "Adventure"),
        ]
    )
    other_game = Game(
        steam_app_id=20,
        name="Other Reference",
        igdb_status="ready",
    )
    other_game.metadata_term_links.append(
        _term("keyword", 50, "Other keyword")
    )
    database_session.add_all(
        [
            _ownership(profile, reference),
            _ownership(profile, other_game),
        ]
    )
    database_session.commit()

    result = browse_reference_keywords(
        database_session,
        profile.id,
        reference.steam_app_id,
    )

    assert result == KeywordBrowse(
        items=(
            FacetOption(id=20, name="Atmospheric"),
            FacetOption(id=10, name="atmospheric"),
            FacetOption(id=30, name="story rich"),
        ),
        truncated=False,
    )

def test_keyword_browse_is_bounded_and_reports_truncation(
    database_session: Session,
) -> None:
    profile = _profile(1)
    reference = Game(
        steam_app_id=10,
        name="Reference Game",
        igdb_status="ready",
    )
    reference.metadata_term_links.extend(
        _term("keyword", 1_000 + index, f"Keyword {index:03d}")
        for index in range(KEYWORD_BROWSE_LIMIT + 2)
    )
    database_session.add(_ownership(profile, reference))
    database_session.commit()

    result = browse_reference_keywords(
        database_session,
        profile.id,
        reference.steam_app_id,
    )

    assert len(result.items) == KEYWORD_BROWSE_LIMIT
    assert result.items[0].name == "Keyword 000"
    assert result.items[-1].name == "Keyword 249"
    assert result.truncated is True

def test_keyword_browse_returns_explicit_empty_collection(
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

    assert browse_reference_keywords(
        database_session,
        profile.id,
        reference.steam_app_id,
    ) == KeywordBrowse(items=(), truncated=False)

def test_keyword_browse_preserves_reference_access_boundaries(
    database_session: Session,
) -> None:
    selected_profile = _profile(1)
    other_profile = _profile(2)
    unowned = Game(
        steam_app_id=10,
        name="Other Reference",
        igdb_status="ready",
    )
    unavailable = Game(
        steam_app_id=20,
        name="Unavailable Reference",
        igdb_status="missing",
    )
    database_session.add_all(
        [
            selected_profile,
            _ownership(other_profile, unowned),
            _ownership(selected_profile, unavailable),
        ]
    )
    database_session.commit()

    with pytest.raises(ProfileNotFoundError):
        browse_reference_keywords(database_session, 999, 10)
    with pytest.raises(ReferenceNotOwnedError):
        browse_reference_keywords(database_session, 1, 10)
    with pytest.raises(ReferenceMetadataUnavailableError):
        browse_reference_keywords(database_session, 1, 20)

def test_keyword_browse_uses_at_most_three_queries(
    database_session: Session,
) -> None:
    profile = _profile(1)
    reference = Game(
        steam_app_id=10,
        name="Reference Game",
        igdb_status="ready",
    )
    reference.metadata_term_links.append(
        _term("keyword", 10, "Atmospheric")
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
        browse_reference_keywords(
            database_session,
            profile.id,
            reference.steam_app_id,
        )
    finally:
        event.remove(bind, "before_cursor_execute", record_select)

    assert len(statements) <= 3

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
