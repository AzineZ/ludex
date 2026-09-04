import json
from datetime import UTC, datetime
from io import StringIO
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.igdb_enrichment import get_pending_owned_steam_app_ids
from app.igdb_enrichment_command import run_igdb_enrichment_command
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

    with patch(
        "app.igdb_enrichment.enrich_game_metadata",
        side_effect=AssertionError("IGDB enrichment must not run"),
    ) as enrichment:
        exit_code = run_igdb_enrichment_command(
            [],
            session_factory=factory,
            output=StringIO(),
        )

    assert exit_code == 0
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
