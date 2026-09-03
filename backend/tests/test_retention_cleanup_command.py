import json
from datetime import UTC, datetime, timedelta
from io import StringIO

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models import Profile, SteamAccessSession
from app.retention_cleanup_command import run_retention_cleanup_command


NOW = datetime(2026, 9, 2, 12, tzinfo=UTC)


def _database():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as session:
        profile = Profile(
            steam_id="76561198000000000",
            display_name="Expired Player",
        )
        profile.access_sessions.append(
            SteamAccessSession(
                token_digest=b"x" * 32,
                created_at=NOW - timedelta(days=40),
                expires_at=NOW - timedelta(days=33),
            )
        )
        session.add(profile)
        session.commit()
    return engine, factory


def test_command_defaults_to_json_report_without_deleting() -> None:
    engine, factory = _database()
    output = StringIO()

    exit_code = run_retention_cleanup_command(
        [],
        session_factory=factory,
        clock=lambda: NOW,
        output=output,
    )

    payload = json.loads(output.getvalue())
    assert exit_code == 0
    assert payload == {
        "candidate_ownership_count": 0,
        "candidate_profile_count": 1,
        "candidate_profiles": [
            {
                "last_session_ended_at": "2026-07-31T12:00:00+00:00",
                "profile_id": 1,
                "session_count": 1,
                "ownership_count": 0,
            }
        ],
        "candidate_session_count": 1,
        "generated_at": "2026-09-02T12:00:00+00:00",
        "mode": "report-only",
        "retention_days": 30,
    }
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Profile)) == 1

    engine.dispose()


def test_command_requires_apply_flag_before_deleting() -> None:
    engine, factory = _database()
    output = StringIO()

    exit_code = run_retention_cleanup_command(
        ["--apply"],
        session_factory=factory,
        clock=lambda: NOW,
        output=output,
    )

    payload = json.loads(output.getvalue())
    assert exit_code == 0
    assert payload["mode"] == "applied"
    assert payload["candidate_profile_count"] == 1
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Profile)) == 0
        assert session.scalar(
            select(func.count()).select_from(SteamAccessSession)
        ) == 0

    engine.dispose()
