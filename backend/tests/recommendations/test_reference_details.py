import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.models import Game
from app.recommendations.reference_reads import (
    FacetOption,
    MetadataStatus,
    ProfileNotFoundError,
    ReferenceDetails,
    ReferenceFacets,
    ReferenceMetadataUnavailableError,
    ReferenceNotOwnedError,
    load_reference_details,
)
from tests.recommendations.reference_read_support import (
    database_session,
    _ownership,
    _profile,
    _term,
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
