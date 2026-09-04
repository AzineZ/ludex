import json
from datetime import UTC, datetime
from io import StringIO
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.igdb_enrichment import get_pending_owned_steam_app_ids
from app.igdb_enrichment_command import run_igdb_enrichment_command
from app.igdb_client import IGDBUnavailableError
from app.models import Game, Profile, ProfileGame


ATTEMPTED_AT = datetime(2026, 9, 3, 12, tzinfo=UTC)


def _database():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    with factory() as session:
        first_profile = Profile(
            steam_id="76561198000000001",
            display_name="First Player",
        )
        second_profile = Profile(
            steam_id="76561198000000002",
            display_name="Second Player",
        )
        games = {
            1: Game(
                steam_app_id=1,
                name="Ready",
                igdb_status="ready",
                igdb_game_id=101,
                igdb_last_attempted_at=ATTEMPTED_AT,
            ),
            2: Game(
                steam_app_id=2,
                name="Missing",
                igdb_status="missing",
                igdb_last_attempted_at=ATTEMPTED_AT,
            ),
            3: Game(
                steam_app_id=3,
                name="Retry Pending",
                igdb_status="pending",
                igdb_last_attempted_at=ATTEMPTED_AT,
                igdb_last_error="IGDB was temporarily unavailable.",
            ),
            4: Game(
                steam_app_id=4,
                name="Ambiguous",
                igdb_status="ambiguous",
                igdb_last_attempted_at=ATTEMPTED_AT,
            ),
            5: Game(
                steam_app_id=5,
                name="Unowned Pending",
                igdb_status="pending",
            ),
            9: Game(
                steam_app_id=9,
                name="New Pending",
                igdb_status="pending",
            ),
        }
        session.add_all([first_profile, second_profile, *games.values()])
        session.flush()
        session.add_all(
            [
                ProfileGame(profile=first_profile, game=games[9]),
                ProfileGame(profile=second_profile, game=games[9]),
                ProfileGame(profile=first_profile, game=games[3]),
                ProfileGame(profile=first_profile, game=games[1]),
                ProfileGame(profile=first_profile, game=games[2]),
                ProfileGame(profile=second_profile, game=games[4]),
            ]
        )
        session.commit()

    return engine, factory


def test_selects_unique_owned_pending_games_in_deterministic_order() -> None:
    engine, factory = _database()

    with factory() as session:
        assert get_pending_owned_steam_app_ids(session) == [3, 9]

    engine.dispose()


def test_report_only_command_returns_safe_aggregate_coverage() -> None:
    engine, factory = _database()
    output = StringIO()

    exit_code = run_igdb_enrichment_command(
        [],
        session_factory=factory,
        output=output,
    )

    assert exit_code == 0
    assert json.loads(output.getvalue()) == {
        "ambiguous_game_count": 1,
        "attempted_game_count": 4,
        "error_game_count": 1,
        "missing_game_count": 1,
        "mode": "report-only",
        "pending_game_count": 2,
        "ready_game_count": 1,
        "selected_pending_game_count": 2,
        "total_owned_game_count": 5,
    }

    engine.dispose()


def test_report_only_command_makes_no_provider_call_or_database_change() -> None:
    engine, factory = _database()

    with factory() as session:
        before = session.scalars(
            select(Game).order_by(Game.steam_app_id)
        ).all()
        before_state = [
            (
                game.steam_app_id,
                game.igdb_status,
                game.igdb_last_attempted_at,
                game.igdb_last_error,
            )
            for game in before
        ]

    client_factory = MagicMock()

    with patch(
        "app.igdb_enrichment.enrich_game_metadata",
        side_effect=AssertionError("IGDB enrichment must not run"),
    ) as enrichment:
        exit_code = run_igdb_enrichment_command(
            [],
            session_factory=factory,
            client_factory=client_factory,
            output=StringIO(),
        )

    assert exit_code == 0
    client_factory.assert_not_called()
    enrichment.assert_not_called()

    with factory() as session:
        after = session.scalars(
            select(Game).order_by(Game.steam_app_id)
        ).all()
        after_state = [
            (
                game.steam_app_id,
                game.igdb_status,
                game.igdb_last_attempted_at,
                game.igdb_last_error,
            )
            for game in after
        ]

    assert after_state == before_state
    engine.dispose()


def test_apply_enriches_exact_selection_and_reports_before_and_after() -> None:
    engine, factory = _database()
    output = StringIO()
    client = MagicMock()
    client_context = MagicMock()
    client_context.__enter__.return_value = client
    client_factory = MagicMock(return_value=client_context)

    def apply_metadata(session, received_client, steam_app_ids):
        assert received_client is client
        assert steam_app_ids == [3, 9]
        games = session.scalars(
            select(Game).where(Game.steam_app_id.in_(steam_app_ids))
        ).all()
        for game in games:
            game.igdb_status = "missing"
            game.igdb_last_attempted_at = ATTEMPTED_AT
            game.igdb_last_error = None
        session.commit()
        return [MagicMock(), MagicMock()]

    enrichment_service = MagicMock(side_effect=apply_metadata)

    exit_code = run_igdb_enrichment_command(
        ["--apply"],
        session_factory=factory,
        client_factory=client_factory,
        enrichment_service=enrichment_service,
        output=output,
    )

    assert exit_code == 0
    assert json.loads(output.getvalue()) == {
        "after": {
            "ambiguous_game_count": 1,
            "attempted_game_count": 5,
            "error_game_count": 0,
            "missing_game_count": 3,
            "pending_game_count": 0,
            "ready_game_count": 1,
            "total_owned_game_count": 5,
        },
        "before": {
            "ambiguous_game_count": 1,
            "attempted_game_count": 4,
            "error_game_count": 1,
            "missing_game_count": 1,
            "pending_game_count": 2,
            "ready_game_count": 1,
            "total_owned_game_count": 5,
        },
        "mode": "applied",
        "processed_game_count": 2,
        "selected_pending_game_count": 2,
    }
    client_factory.assert_called_once_with()
    client_context.__enter__.assert_called_once_with()
    client_context.__exit__.assert_called_once_with(None, None, None)
    enrichment_service.assert_called_once()

    engine.dispose()


def test_apply_with_no_pending_games_does_not_construct_client() -> None:
    engine, factory = _database()
    with factory() as session:
        pending_games = session.scalars(
            select(Game).where(Game.igdb_status == "pending")
        ).all()
        for game in pending_games:
            game.igdb_status = "missing"
            game.igdb_last_attempted_at = ATTEMPTED_AT
            game.igdb_last_error = None
        session.commit()

    output = StringIO()
    client_factory = MagicMock()
    enrichment_service = MagicMock()

    exit_code = run_igdb_enrichment_command(
        ["--apply"],
        session_factory=factory,
        client_factory=client_factory,
        enrichment_service=enrichment_service,
        output=output,
    )

    payload = json.loads(output.getvalue())
    assert exit_code == 0
    assert payload["mode"] == "applied"
    assert payload["selected_pending_game_count"] == 0
    assert payload["processed_game_count"] == 0
    assert payload["before"] == payload["after"]
    client_factory.assert_not_called()
    enrichment_service.assert_not_called()

    engine.dispose()


def test_apply_failure_is_sanitized_and_reports_preserved_progress() -> None:
    engine, factory = _database()
    output = StringIO()
    error_output = StringIO()
    client_context = MagicMock()
    client_context.__enter__.return_value = MagicMock()
    client_factory = MagicMock(return_value=client_context)

    def fail_after_progress(session, _client, steam_app_ids):
        first_game, failed_game = session.scalars(
            select(Game)
            .where(Game.steam_app_id.in_(steam_app_ids))
            .order_by(Game.steam_app_id)
        ).all()
        first_game.igdb_status = "missing"
        first_game.igdb_last_attempted_at = ATTEMPTED_AT
        first_game.igdb_last_error = None
        failed_game.igdb_last_attempted_at = ATTEMPTED_AT
        failed_game.igdb_last_error = "raw-provider-secret"
        session.commit()
        raise IGDBUnavailableError("raw-provider-secret")

    exit_code = run_igdb_enrichment_command(
        ["--apply"],
        session_factory=factory,
        client_factory=client_factory,
        enrichment_service=fail_after_progress,
        output=output,
        error_output=error_output,
    )

    payload = json.loads(error_output.getvalue())
    assert exit_code == 1
    assert output.getvalue() == ""
    assert payload == {
        "after": {
            "ambiguous_game_count": 1,
            "attempted_game_count": 5,
            "error_game_count": 1,
            "missing_game_count": 2,
            "pending_game_count": 1,
            "ready_game_count": 1,
            "total_owned_game_count": 5,
        },
        "before": {
            "ambiguous_game_count": 1,
            "attempted_game_count": 4,
            "error_game_count": 1,
            "missing_game_count": 1,
            "pending_game_count": 2,
            "ready_game_count": 1,
            "total_owned_game_count": 5,
        },
        "detail": "IGDB enrichment did not complete.",
        "mode": "failed",
        "selected_pending_game_count": 2,
    }
    assert "raw-provider-secret" not in error_output.getvalue()
    client_context.__exit__.assert_called_once()

    with factory() as session:
        assert session.get(Game, 3).igdb_status == "missing"
        assert session.get(Game, 9).igdb_status == "pending"

    engine.dispose()
