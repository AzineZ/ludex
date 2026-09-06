from dataclasses import FrozenInstanceError

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.models import Game
from app.recommendations.reference_reads import (
    KeywordBrowse,
    browse_reference_keywords,
    load_reference_details,
    search_owned_games,
    search_reference_keywords,
)
from tests.recommendations.reference_read_support import (
    database_session,
    _ownership,
    _profile,
    _term,
)


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

    keyword_browse = KeywordBrowse(items=(), truncated=False)
    with pytest.raises(FrozenInstanceError):
        keyword_browse.truncated = True

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
        browse_reference_keywords(
            database_session,
            profile.id,
            reference.steam_app_id,
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
