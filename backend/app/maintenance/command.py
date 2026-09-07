import argparse
import json
import sys
from collections.abc import Callable, Iterator, Sequence
from contextlib import AbstractContextManager, contextmanager
from datetime import datetime
from io import TextIOBase

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import SessionLocal, engine
from app.maintenance.retention import (
    Clock,
    ProfileRetentionReport,
    _utc_now,
    apply_profile_retention_cleanup,
    report_profile_retention_candidates,
)


SessionFactory = Callable[[], Session]
ApplyLock = Callable[[], AbstractContextManager[bool]]


RETENTION_CLEANUP_ADVISORY_LOCK_KEY = 0x4C55444558524554


@contextmanager
def _retention_cleanup_apply_lock() -> Iterator[bool]:
    """Hold one transaction-scoped PostgreSQL lock for an apply run."""
    with engine.connect() as connection:
        with connection.begin():
            acquired = connection.scalar(
                text("SELECT pg_try_advisory_xact_lock(:lock_key)"),
                {"lock_key": RETENTION_CLEANUP_ADVISORY_LOCK_KEY},
            )
            yield bool(acquired)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Report expired Ludex profile data, or delete it with --apply."
        )
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Delete the reported profile-specific data in one transaction.",
    )
    return parser


def _report_payload(
    report: ProfileRetentionReport,
    *,
    applied: bool,
) -> dict[str, object]:
    return {
        "mode": "applied" if applied else "report-only",
        "generated_at": report.generated_at.isoformat(),
        "retention_days": report.retention_period.days,
        "candidate_profile_count": report.candidate_profile_count,
        "candidate_session_count": report.candidate_session_count,
        "candidate_ownership_count": report.candidate_ownership_count,
    }


def _write_payload(payload: dict[str, object], output: TextIOBase) -> None:
    json.dump(payload, output, indent=2, sort_keys=True)
    output.write("\n")


def run_retention_cleanup_command(
    arguments: Sequence[str],
    *,
    session_factory: SessionFactory = SessionLocal,
    clock: Clock = _utc_now,
    apply_lock: ApplyLock = _retention_cleanup_apply_lock,
    output: TextIOBase = sys.stdout,
    error_output: TextIOBase = sys.stderr,
) -> int:
    """Run report-only by default and require --apply for deletion."""
    options = _parser().parse_args(arguments)

    try:
        if options.apply:
            with apply_lock() as lock_acquired:
                if not lock_acquired:
                    _write_payload(
                        {
                            "mode": "blocked",
                            "detail": (
                                "Profile retention cleanup is already running."
                            ),
                        },
                        error_output,
                    )
                    return 2

                with session_factory() as database_session:
                    report = apply_profile_retention_cleanup(
                        database_session,
                        clock=clock,
                    )
        else:
            with session_factory() as database_session:
                report = report_profile_retention_candidates(
                    database_session,
                    clock=clock,
                )
    except Exception:
        _write_payload(
            {
                "mode": "failed",
                "detail": (
                    "Profile retention cleanup did not complete."
                    if options.apply
                    else "Profile retention preview did not complete."
                ),
            },
            error_output,
        )
        return 1

    _write_payload(
        _report_payload(report, applied=options.apply),
        output,
    )
    return 0


def main() -> None:
    raise SystemExit(run_retention_cleanup_command(sys.argv[1:]))


if __name__ == "__main__":
    main()
