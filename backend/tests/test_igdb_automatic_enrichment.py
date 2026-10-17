import logging
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import MagicMock

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.integrations.igdb.automatic import (
    AUTOMATIC_ENRICHMENT_LOGGER,
    SharedIGDBClient,
    run_automatic_enrichment,
)
from app.integrations.igdb.client import IGDBUnavailableError
from app.integrations.igdb.enrichment import MAX_ENRICHMENT_GAMES_PER_RUN
from app.integrations.igdb.matching import IGDBMatchStatus
from app.models import Game, Profile, ProfileGame


def _database(pending_ids_by_profile: dict[str, list[int]]) -> sessionmaker[Session]:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory.begin() as session:
        for steam_id, pending_ids in pending_ids_by_profile.items():
            profile = Profile(steam_id=steam_id, display_name=steam_id)
            for steam_app_id in pending_ids:
                profile.owned_games.append(
                    ProfileGame(
                        game=Game(
                            steam_app_id=steam_app_id,
                            name=f"Game {steam_app_id}",
                        )
                    )
                )
            session.add(profile)
    return factory


def _marking_service(calls: list[list[int]]):
    """Mark requested games as definitively missing, like a real batch."""

    def enrich(session: Session, client: object, steam_app_ids):
        calls.append(list(steam_app_ids))
        for game in session.scalars(
            select(Game).where(Game.steam_app_id.in_(list(steam_app_ids)))
        ):
            game.igdb_status = "missing"
        session.commit()
        return [
            SimpleNamespace(status=IGDBMatchStatus.MISSING)
            for _ in steam_app_ids
        ]

    return enrich


def _statuses(factory: sessionmaker[Session]) -> dict[int, str]:
    with factory() as session:
        return {
            game.steam_app_id: game.igdb_status
            for game in session.scalars(select(Game))
        }


def test_disabled_run_does_not_lock_or_contact_igdb() -> None:
    lock = MagicMock()
    service = MagicMock()

    processed = run_automatic_enrichment(
        enabled=False,
        session_factory=MagicMock(),
        client_provider=MagicMock(),
        enrichment_service=service,
        enrichment_lock=lock,
    )

    assert processed == 0
    lock.assert_not_called()
    service.assert_not_called()


def test_busy_lock_skips_without_contacting_igdb() -> None:
    factory = _database({"76561198000000001": [10]})
    client_provider = MagicMock()
    service = MagicMock()

    processed = run_automatic_enrichment(
        enabled=True,
        session_factory=factory,
        client_provider=client_provider,
        enrichment_service=service,
        enrichment_lock=lambda: nullcontext(False),
    )

    assert processed == 0
    client_provider.assert_not_called()
    service.assert_not_called()
    assert _statuses(factory) == {10: "pending"}


def test_run_sweeps_pending_games_of_every_profile() -> None:
    factory = _database(
        {
            "76561198000000001": [10, 11],
            "76561198000000002": [20],
        }
    )
    calls: list[list[int]] = []

    processed = run_automatic_enrichment(
        enabled=True,
        session_factory=factory,
        client_provider=MagicMock(),
        enrichment_service=_marking_service(calls),
        enrichment_lock=lambda: nullcontext(True),
    )

    assert processed == 3
    assert calls == [[10, 11, 20]]
    assert set(_statuses(factory).values()) == {"missing"}


def test_second_pass_enriches_games_imported_during_the_run() -> None:
    factory = _database({"76561198000000001": [10]})
    calls: list[list[int]] = []
    mark = _marking_service(calls)

    def enrich_while_another_import_lands(session, client, steam_app_ids):
        results = mark(session, client, steam_app_ids)
        if len(calls) == 1:
            with factory.begin() as other_session:
                profile = Profile(
                    steam_id="76561198000000002",
                    display_name="Late Player",
                )
                profile.owned_games.append(
                    ProfileGame(game=Game(steam_app_id=30, name="Late Game"))
                )
                other_session.add(profile)
        return results

    processed = run_automatic_enrichment(
        enabled=True,
        session_factory=factory,
        client_provider=MagicMock(),
        enrichment_service=enrich_while_another_import_lands,
        enrichment_lock=lambda: nullcontext(True),
    )

    assert processed == 2
    assert calls == [[10], [30]]
    assert _statuses(factory) == {10: "missing", 30: "missing"}


def test_one_trigger_never_exceeds_the_per_run_cap() -> None:
    game_count = MAX_ENRICHMENT_GAMES_PER_RUN + 20
    factory = _database({"76561198000000001": list(range(1, game_count + 1))})
    calls: list[list[int]] = []

    processed = run_automatic_enrichment(
        enabled=True,
        session_factory=factory,
        client_provider=MagicMock(),
        enrichment_service=_marking_service(calls),
        enrichment_lock=lambda: nullcontext(True),
    )

    assert processed == MAX_ENRICHMENT_GAMES_PER_RUN
    assert sum(len(batch) for batch in calls) == MAX_ENRICHMENT_GAMES_PER_RUN
    assert list(_statuses(factory).values()).count("pending") == 20


def test_igdb_failure_is_logged_and_never_raised(caplog) -> None:
    factory = _database({"76561198000000001": [10]})
    service = MagicMock(
        side_effect=IGDBUnavailableError("IGDB is unavailable.")
    )

    with caplog.at_level(logging.WARNING, logger=AUTOMATIC_ENRICHMENT_LOGGER):
        processed = run_automatic_enrichment(
            enabled=True,
            session_factory=factory,
            client_provider=MagicMock(),
            enrichment_service=service,
            enrichment_lock=lambda: nullcontext(True),
        )

    assert processed == 0
    message = caplog.records[-1].getMessage()
    assert message.startswith(
        "event=igdb_auto_enrichment_failed failure_category=igdb_unavailable "
        "processed_game_count=0 duration_ms="
    )
    assert "IGDB is unavailable." not in message


def test_unexpected_failure_is_logged_without_details(caplog) -> None:
    def failing_lock():
        raise RuntimeError("database host is private.internal")

    with caplog.at_level(logging.ERROR, logger=AUTOMATIC_ENRICHMENT_LOGGER):
        processed = run_automatic_enrichment(
            enabled=True,
            session_factory=MagicMock(),
            client_provider=MagicMock(),
            enrichment_service=MagicMock(),
            enrichment_lock=failing_lock,
        )

    assert processed == 0
    message = caplog.records[-1].getMessage()
    assert message.startswith(
        "event=igdb_auto_enrichment_failed failure_category=unexpected_error "
        "error_type=RuntimeError processed_game_count=0 duration_ms="
    )
    assert "private.internal" not in message


def test_shared_client_is_created_once_and_closed() -> None:
    created = MagicMock()
    factory = MagicMock(return_value=created)
    shared = SharedIGDBClient(factory)

    assert shared.get() is created
    assert shared.get() is created
    factory.assert_called_once_with()

    shared.close()
    created.close.assert_called_once_with()
    assert shared.get() is created
    assert factory.call_count == 2


def test_completed_run_logs_one_line_with_outcome_counts(caplog) -> None:
    factory = _database({"76561198000000001": [10, 11, 12]})
    statuses = {
        10: IGDBMatchStatus.MATCHED,
        11: IGDBMatchStatus.MATCHED,
        12: IGDBMatchStatus.AMBIGUOUS,
    }

    def enrich(session, client, steam_app_ids):
        for game in session.scalars(select(Game)):
            game.igdb_status = (
                "ready"
                if statuses[game.steam_app_id] is IGDBMatchStatus.MATCHED
                else "ambiguous"
            )
        session.commit()
        return [SimpleNamespace(status=statuses[i]) for i in steam_app_ids]

    with caplog.at_level(logging.INFO, logger=AUTOMATIC_ENRICHMENT_LOGGER):
        run_automatic_enrichment(
            enabled=True,
            session_factory=factory,
            client_provider=MagicMock(),
            enrichment_service=enrich,
            enrichment_lock=lambda: nullcontext(True),
        )

    messages = [
        record.getMessage()
        for record in caplog.records
        if record.name == AUTOMATIC_ENRICHMENT_LOGGER
    ]
    assert len(messages) == 1
    assert messages[0].startswith(
        "event=igdb_auto_enrichment_completed processed_game_count=3 "
        "ready=2 missing=0 ambiguous=1 duration_ms="
    )


def test_skipped_and_idle_runs_log_as_expected(caplog) -> None:
    factory = _database({})

    with caplog.at_level(logging.INFO, logger=AUTOMATIC_ENRICHMENT_LOGGER):
        run_automatic_enrichment(
            enabled=True,
            session_factory=factory,
            client_provider=MagicMock(),
            enrichment_service=MagicMock(),
            enrichment_lock=lambda: nullcontext(False),
        )
        run_automatic_enrichment(
            enabled=True,
            session_factory=factory,
            client_provider=MagicMock(),
            enrichment_service=MagicMock(),
            enrichment_lock=lambda: nullcontext(True),
        )

    assert [record.getMessage() for record in caplog.records] == [
        "event=igdb_auto_enrichment_skipped "
        "skip_reason=enrichment_already_running"
    ]


def test_log_lines_reach_uvicorn_output() -> None:
    assert AUTOMATIC_ENRICHMENT_LOGGER.startswith("uvicorn.error.")
    assert logging.getLogger(AUTOMATIC_ENRICHMENT_LOGGER).isEnabledFor(
        logging.INFO
    )
