import argparse
from collections.abc import Callable, Sequence
from datetime import datetime
from io import TextIOBase
import json
import sys

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.retention_cleanup import (
    Clock,
    ProfileRetentionReport,
    _utc_now,
    apply_profile_retention_cleanup,
    report_profile_retention_candidates,
)


SessionFactory = Callable[[], Session]


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
        "candidate_profiles": [
            {
                "profile_id": candidate.profile_id,
                "last_session_ended_at": (
                    candidate.last_session_ended_at.isoformat()
                ),
                "session_count": candidate.session_count,
                "ownership_count": candidate.ownership_count,
            }
            for candidate in report.candidates
        ],
    }


def run_retention_cleanup_command(
    arguments: Sequence[str],
    *,
    session_factory: SessionFactory = SessionLocal,
    clock: Clock = _utc_now,
    output: TextIOBase = sys.stdout,
) -> int:
    """Run report-only by default and require --apply for deletion."""
    options = _parser().parse_args(arguments)

    with session_factory() as database_session:
        if options.apply:
            report = apply_profile_retention_cleanup(
                database_session,
                clock=clock,
            )
        else:
            report = report_profile_retention_candidates(
                database_session,
                clock=clock,
            )

    json.dump(
        _report_payload(report, applied=options.apply),
        output,
        indent=2,
        sort_keys=True,
    )
    output.write("\n")
    return 0


def main() -> None:
    raise SystemExit(run_retention_cleanup_command(sys.argv[1:]))


if __name__ == "__main__":
    main()
