from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.integrations.igdb.coverage import (
    IGDBMetadataCoverage,
    get_igdb_metadata_coverage,
)
from app.models import Game, Profile, ProfileGame


def test_empty_library_has_zero_metadata_coverage() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        coverage = get_igdb_metadata_coverage(session)

        assert coverage == IGDBMetadataCoverage(
            total_games=0,
            pending_games=0,
            ready_games=0,
            missing_games=0,
            ambiguous_games=0,
            attempted_games=0,
            error_games=0,
        )
        assert coverage.definitive_games == 0
        assert coverage.completion_ratio == 0.0
        assert coverage.match_ratio == 0.0

    engine.dispose()


def test_reports_coverage_across_unique_owned_games() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    attempted_at = datetime(2026, 8, 10, tzinfo=UTC)

    with Session(engine) as session:
        first_profile = Profile(
            steam_id="76561198000000001",
            display_name="First Player",
        )
        second_profile = Profile(
            steam_id="76561198000000002",
            display_name="Second Player",
        )

        ready_game = Game(
            steam_app_id=1,
            name="Ready Game",
            igdb_status="ready",
            igdb_game_id=101,
            igdb_last_attempted_at=attempted_at,
        )
        missing_game = Game(
            steam_app_id=2,
            name="Missing Game",
            igdb_status="missing",
            igdb_last_attempted_at=attempted_at,
        )
        ambiguous_game = Game(
            steam_app_id=3,
            name="Ambiguous Game",
            igdb_status="ambiguous",
            igdb_last_attempted_at=attempted_at,
        )
        failed_pending_game = Game(
            steam_app_id=4,
            name="Failed Pending Game",
            igdb_status="pending",
            igdb_last_attempted_at=attempted_at,
            igdb_last_error="IGDB is unavailable.",
        )
        unattempted_game = Game(
            steam_app_id=5,
            name="Unattempted Game",
            igdb_status="pending",
        )
        orphaned_game = Game(
            steam_app_id=6,
            name="Unowned Cached Game",
            igdb_status="ready",
            igdb_game_id=106,
            igdb_last_attempted_at=attempted_at,
            igdb_last_error="This row must not be counted.",
        )

        session.add_all(
            [
                first_profile,
                second_profile,
                ready_game,
                missing_game,
                ambiguous_game,
                failed_pending_game,
                unattempted_game,
                orphaned_game,
            ]
        )
        session.flush()

        session.add_all(
            [
                ProfileGame(
                    profile=first_profile,
                    game=ready_game,
                ),
                ProfileGame(
                    profile=second_profile,
                    game=ready_game,
                ),
                ProfileGame(
                    profile=first_profile,
                    game=missing_game,
                ),
                ProfileGame(
                    profile=second_profile,
                    game=ambiguous_game,
                ),
                ProfileGame(
                    profile=first_profile,
                    game=failed_pending_game,
                ),
                ProfileGame(
                    profile=second_profile,
                    game=unattempted_game,
                ),
            ]
        )
        session.commit()

        coverage = get_igdb_metadata_coverage(session)

        assert coverage == IGDBMetadataCoverage(
            total_games=5,
            pending_games=2,
            ready_games=1,
            missing_games=1,
            ambiguous_games=1,
            attempted_games=4,
            error_games=1,
        )
        assert coverage.definitive_games == 3
        assert coverage.completion_ratio == pytest.approx(3 / 5)
        assert coverage.match_ratio == pytest.approx(1 / 3)

    engine.dispose()
