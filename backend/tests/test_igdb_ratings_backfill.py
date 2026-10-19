from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from io import StringIO
import json
from typing import Any

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.integrations.igdb.client import IGDBAPIError, IGDBResponseError
from app.integrations.igdb.ratings_backfill import (
    RATINGS_BATCH_PAUSE_SECONDS,
    UncheckedRatingGame,
    backfill_game_ratings,
    fetch_game_ratings,
    get_unchecked_rating_games,
)
from app.integrations.igdb.ratings_command import (
    run_igdb_ratings_backfill_command,
)
from app.models import Game, GameIGDBMetadataTerm, IGDBMetadataTerm


CHECKED_AT = datetime(2026, 10, 19, tzinfo=UTC)


class FakeIGDBClient:
    """Answer rating queries from a fixed table and record each query."""

    def __init__(
        self,
        ratings: dict[int, dict[str, Any]],
        *,
        failure: Exception | None = None,
    ) -> None:
        self.ratings = ratings
        self.failure = failure
        self.queries: list[tuple[str, str]] = []

    def query(self, endpoint: str, body: str) -> list[dict[str, Any]]:
        self.queries.append((endpoint, body))
        if self.failure is not None:
            raise self.failure
        requested = {
            int(value)
            for value in body.split("where id = (")[1].split(")")[0].split(",")
        }
        return [
            {"id": igdb_id, **values}
            for igdb_id, values in self.ratings.items()
            if igdb_id in requested
        ]

    def __enter__(self) -> "FakeIGDBClient":
        return self

    def __exit__(self, *_: object) -> None:
        return None


@pytest.fixture
def session_factory() -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, expire_on_commit=False)
    engine.dispose()


def _add_games(factory: sessionmaker[Session]) -> None:
    shooter = IGDBMetadataTerm(kind="genre", igdb_id=5, name="Shooter")
    with factory() as session:
        session.add_all(
            [
                Game(
                    steam_app_id=10,
                    name="Ready",
                    igdb_status="ready",
                    igdb_game_id=1,
                    metadata_term_links=[GameIGDBMetadataTerm(term=shooter)],
                ),
                Game(
                    steam_app_id=20,
                    name="Ready, no IGDB ratings",
                    igdb_status="ready",
                    igdb_game_id=2,
                ),
                Game(
                    steam_app_id=30,
                    name="Already checked",
                    igdb_status="ready",
                    igdb_game_id=3,
                    igdb_ratings_checked_at=CHECKED_AT,
                ),
                Game(steam_app_id=40, name="Pending", igdb_status="pending"),
                Game(
                    steam_app_id=50,
                    name="Missing",
                    igdb_status="missing",
                    igdb_game_id=None,
                ),
            ]
        )
        session.commit()


RATINGS = {
    1: {
        "total_rating": 87.4,
        "total_rating_count": 1_204,
        "aggregated_rating": 91.0,
        "aggregated_rating_count": 12,
    },
}


def test_only_ready_matched_unchecked_games_are_selected(
    session_factory: sessionmaker[Session],
) -> None:
    _add_games(session_factory)

    with session_factory() as session:
        assert get_unchecked_rating_games(session) == [
            UncheckedRatingGame(steam_app_id=10, igdb_game_id=1),
            UncheckedRatingGame(steam_app_id=20, igdb_game_id=2),
        ]


def test_fetch_requests_only_rating_fields_and_fills_missing_games() -> None:
    client = FakeIGDBClient(RATINGS)

    ratings = fetch_game_ratings(client, [1, 2])

    assert client.queries == [
        (
            "games",
            "fields id,total_rating,total_rating_count,aggregated_rating,"
            "aggregated_rating_count; where id = (1,2); limit 500;",
        )
    ]
    assert ratings[1].total_rating == 87.4
    assert ratings[2].total_rating is None


class _UnexpectedClient(FakeIGDBClient):
    """Return a game that was never requested."""

    def __init__(self) -> None:
        super().__init__({})

    def query(self, endpoint: str, body: str) -> list[dict[str, Any]]:
        return [{"id": 999, "total_rating": 50}]


def test_fetch_rejects_unexpected_games_and_oversized_batches() -> None:
    with pytest.raises(IGDBResponseError):
        fetch_game_ratings(_UnexpectedClient(), [1])
    with pytest.raises(ValueError):
        fetch_game_ratings(FakeIGDBClient({}), list(range(1, 102)))


def test_backfill_stores_ratings_without_touching_status_or_facets(
    session_factory: sessionmaker[Session],
) -> None:
    _add_games(session_factory)
    pauses: list[float] = []

    with session_factory() as session:
        updated = backfill_game_ratings(
            session,
            FakeIGDBClient(RATINGS),
            get_unchecked_rating_games(session),
            clock=lambda: CHECKED_AT,
            sleeper=pauses.append,
        )

    assert updated == 2
    assert pauses == []
    with session_factory() as session:
        rated = session.get(Game, 10)
        unrated = session.get(Game, 20)
        assert (
            rated.igdb_status,
            rated.igdb_total_rating,
            rated.igdb_total_rating_count,
            rated.igdb_aggregated_rating,
            rated.igdb_aggregated_rating_count,
            rated.igdb_ratings_checked_at.replace(tzinfo=UTC),
        ) == ("ready", 87.4, 1_204, 91.0, 12, CHECKED_AT)
        assert [link.term.name for link in rated.metadata_term_links] == [
            "Shooter"
        ]
        assert unrated.igdb_total_rating is None
        assert unrated.igdb_ratings_checked_at is not None
        assert get_unchecked_rating_games(session) == []


def test_backfill_pauses_between_batches(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        session.add_all(
            Game(
                steam_app_id=1_000 + index,
                name=f"Game {index}",
                igdb_status="ready",
                igdb_game_id=index + 1,
            )
            for index in range(150)
        )
        session.commit()
    pauses: list[float] = []
    client = FakeIGDBClient({})

    with session_factory() as session:
        updated = backfill_game_ratings(
            session,
            client,
            get_unchecked_rating_games(session),
            clock=lambda: CHECKED_AT,
            sleeper=pauses.append,
        )

    assert updated == 150
    assert len(client.queries) == 2
    assert pauses == [RATINGS_BATCH_PAUSE_SECONDS]


@contextmanager
def _lock(acquired: bool) -> Iterator[bool]:
    yield acquired


def _run(
    factory: sessionmaker[Session],
    arguments: list[str],
    client: FakeIGDBClient,
    *,
    lock_acquired: bool = True,
) -> tuple[int, dict[str, Any], dict[str, Any] | None]:
    output = StringIO()
    error_output = StringIO()
    code = run_igdb_ratings_backfill_command(
        arguments,
        session_factory=factory,
        client_factory=lambda: client,
        apply_lock=lambda: _lock(lock_acquired),
        output=output,
        error_output=error_output,
    )
    payload = json.loads(output.getvalue()) if output.getvalue() else {}
    error = (
        json.loads(error_output.getvalue())
        if error_output.getvalue()
        else None
    )
    return code, payload, error


def test_command_reports_by_default_without_calling_igdb(
    session_factory: sessionmaker[Session],
) -> None:
    _add_games(session_factory)
    client = FakeIGDBClient(RATINGS)

    code, payload, error = _run(session_factory, [], client)

    assert code == 0
    assert error is None
    assert payload == {
        "mode": "report-only",
        "selected_game_count": 2,
        "selected_batch_count": 1,
    }
    assert client.queries == []


def test_command_applies_once_and_is_idempotent(
    session_factory: sessionmaker[Session],
) -> None:
    _add_games(session_factory)

    first = _run(session_factory, ["--apply"], FakeIGDBClient(RATINGS))
    second_client = FakeIGDBClient(RATINGS)
    second = _run(session_factory, ["--apply"], second_client)

    assert first[0] == 0
    assert first[1] == {
        "mode": "applied",
        "selected_game_count": 2,
        "selected_batch_count": 1,
        "updated_game_count": 2,
        "remaining_game_count": 0,
    }
    assert second[1]["updated_game_count"] == 0
    assert second_client.queries == []


def test_command_stops_when_another_igdb_run_holds_the_lock(
    session_factory: sessionmaker[Session],
) -> None:
    _add_games(session_factory)
    client = FakeIGDBClient(RATINGS)

    code, payload, error = _run(
        session_factory,
        ["--apply"],
        client,
        lock_acquired=False,
    )

    assert code == 2
    assert payload == {}
    assert error is not None and error["mode"] == "blocked"
    assert client.queries == []


def test_command_reports_an_igdb_failure_and_leaves_games_unchecked(
    session_factory: sessionmaker[Session],
) -> None:
    _add_games(session_factory)

    code, payload, error = _run(
        session_factory,
        ["--apply"],
        FakeIGDBClient(RATINGS, failure=IGDBAPIError("IGDB is down.")),
    )

    assert code == 1
    assert payload == {}
    assert error == {
        "mode": "failed",
        "detail": "The IGDB ratings backfill did not complete.",
        "selected_game_count": 2,
        "selected_batch_count": 1,
        "remaining_game_count": 2,
    }
    with session_factory() as session:
        assert session.scalars(
            select(Game.igdb_ratings_checked_at).where(
                Game.steam_app_id.in_([10, 20])
            )
        ).all() == [None, None]
