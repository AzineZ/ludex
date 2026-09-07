import json
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from io import StringIO
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

import app.maintenance.command as command
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
        "candidate_session_count": 1,
        "generated_at": "2026-09-02T12:00:00+00:00",
        "mode": "report-only",
        "retention_days": 30,
    }
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Profile)) == 1

    engine.dispose()


def test_apply_lock_uses_one_transaction_scoped_postgres_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_engine = MagicMock()
    connection = MagicMock()
    database_engine.connect.return_value.__enter__.return_value = connection
    connection.scalar.return_value = True
    monkeypatch.setattr(command, "engine", database_engine)

    with command._retention_cleanup_apply_lock() as acquired:
        assert acquired is True

    statement, parameters = connection.scalar.call_args.args
    assert str(statement) == (
        "SELECT pg_try_advisory_xact_lock(:lock_key)"
    )
    assert parameters == {
        "lock_key": command.RETENTION_CLEANUP_ADVISORY_LOCK_KEY,
    }
    connection.begin.return_value.__enter__.assert_called_once_with()
    connection.begin.return_value.__exit__.assert_called_once()


def test_report_only_does_not_acquire_apply_lock() -> None:
    engine, factory = _database()
    apply_lock = MagicMock()

    exit_code = run_retention_cleanup_command(
        [],
        session_factory=factory,
        clock=lambda: NOW,
        apply_lock=apply_lock,
        output=StringIO(),
    )

    assert exit_code == 0
    apply_lock.assert_not_called()
    engine.dispose()


def test_command_requires_apply_flag_before_deleting() -> None:
    engine, factory = _database()
    output = StringIO()

    exit_code = run_retention_cleanup_command(
        ["--apply"],
        session_factory=factory,
        clock=lambda: NOW,
        apply_lock=lambda: nullcontext(True),
        output=output,
    )

    payload = json.loads(output.getvalue())
    assert exit_code == 0
    assert payload["mode"] == "applied"
    assert payload["candidate_profile_count"] == 1
    assert "candidate_profiles" not in payload
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Profile)) == 0
        assert session.scalar(
            select(func.count()).select_from(SteamAccessSession)
        ) == 0

    engine.dispose()


def test_apply_exits_safely_when_another_cleanup_holds_the_lock() -> None:
    session_factory = MagicMock()
    output = StringIO()
    error_output = StringIO()

    exit_code = run_retention_cleanup_command(
        ["--apply"],
        session_factory=session_factory,
        apply_lock=lambda: nullcontext(False),
        output=output,
        error_output=error_output,
    )

    assert exit_code == 2
    assert output.getvalue() == ""
    assert json.loads(error_output.getvalue()) == {
        "detail": "Profile retention cleanup is already running.",
        "mode": "blocked",
    }
    session_factory.assert_not_called()


@pytest.mark.parametrize(
    ("arguments", "expected_detail"),
    [
        ([], "Profile retention preview did not complete."),
        (["--apply"], "Profile retention cleanup did not complete."),
    ],
)
def test_command_failure_is_nonzero_and_sanitized(
    arguments: list[str],
    expected_detail: str,
) -> None:
    sensitive_detail = "database failure with private SQL parameters"
    session_context = MagicMock()
    session_context.__enter__.side_effect = RuntimeError(sensitive_detail)
    session_factory = MagicMock(return_value=session_context)
    output = StringIO()
    error_output = StringIO()

    exit_code = run_retention_cleanup_command(
        arguments,
        session_factory=session_factory,
        apply_lock=lambda: nullcontext(True),
        output=output,
        error_output=error_output,
    )

    assert exit_code == 1
    assert output.getvalue() == ""
    assert json.loads(error_output.getvalue()) == {
        "detail": expected_detail,
        "mode": "failed",
    }
    assert sensitive_detail not in error_output.getvalue()


def test_command_report_does_not_expose_profile_details() -> None:
    engine, factory = _database()
    output = StringIO()

    exit_code = run_retention_cleanup_command(
        [],
        session_factory=factory,
        clock=lambda: NOW,
        output=output,
    )

    report = output.getvalue()
    assert exit_code == 0
    assert "profile_id" not in report
    assert "steam_id" not in report
    assert "Expired Player" not in report
    assert "2026-07-31" not in report
    engine.dispose()
