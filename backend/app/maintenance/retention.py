from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import and_, case, delete, func, select
from sqlalchemy.orm import Session

from app.clock import Clock, read_utc_time, stored_utc_time, utc_now
from app.models import Profile, ProfileGame, SteamAccessSession


PROFILE_RETENTION_PERIOD = timedelta(days=30)


@dataclass(frozen=True)
class ProfileRetentionCandidate:
    """Summarize one profile eligible for later destructive cleanup."""

    profile_id: int
    last_session_ended_at: datetime
    session_count: int
    ownership_count: int


@dataclass(frozen=True)
class ProfileRetentionReport:
    """Describe cleanup candidates without changing persisted data."""

    generated_at: datetime
    retention_period: timedelta
    candidates: tuple[ProfileRetentionCandidate, ...]

    @property
    def candidate_profile_count(self) -> int:
        return len(self.candidates)

    @property
    def candidate_session_count(self) -> int:
        return sum(candidate.session_count for candidate in self.candidates)

    @property
    def candidate_ownership_count(self) -> int:
        return sum(
            candidate.ownership_count for candidate in self.candidates
        )


def report_profile_retention_candidates(
    database_session: Session,
    *,
    clock: Clock = utc_now,
) -> ProfileRetentionReport:
    """Report profiles whose most recent ended session is at least 30 days old."""
    generated_at = read_utc_time(clock, clock_name="retention-cleanup")
    retention_cutoff = generated_at - PROFILE_RETENTION_PERIOD

    session_ended_at = case(
        (
            SteamAccessSession.revoked_at.is_not(None),
            SteamAccessSession.revoked_at,
        ),
        else_=SteamAccessSession.expires_at,
    )
    active_session_count = func.sum(
        case(
            (
                and_(
                    SteamAccessSession.revoked_at.is_(None),
                    SteamAccessSession.expires_at > generated_at,
                ),
                1,
            ),
            else_=0,
        )
    )
    session_summary = (
        select(
            SteamAccessSession.profile_id.label("profile_id"),
            func.max(session_ended_at).label("last_session_ended_at"),
            func.count(SteamAccessSession.id).label("session_count"),
            active_session_count.label("active_session_count"),
        )
        .group_by(SteamAccessSession.profile_id)
        .subquery()
    )
    ownership_summary = (
        select(
            ProfileGame.profile_id.label("profile_id"),
            func.count().label("ownership_count"),
        )
        .group_by(ProfileGame.profile_id)
        .subquery()
    )
    statement = (
        select(
            Profile.id,
            session_summary.c.last_session_ended_at,
            session_summary.c.session_count,
            func.coalesce(
                ownership_summary.c.ownership_count,
                0,
            ),
        )
        .join(
            session_summary,
            session_summary.c.profile_id == Profile.id,
        )
        .outerjoin(
            ownership_summary,
            ownership_summary.c.profile_id == Profile.id,
        )
        .where(
            session_summary.c.active_session_count == 0,
            session_summary.c.last_session_ended_at <= retention_cutoff,
        )
        .order_by(Profile.id)
    )

    candidates = tuple(
        ProfileRetentionCandidate(
            profile_id=profile_id,
            last_session_ended_at=stored_utc_time(last_session_ended_at),
            session_count=session_count,
            ownership_count=ownership_count,
        )
        for (
            profile_id,
            last_session_ended_at,
            session_count,
            ownership_count,
        ) in database_session.execute(statement)
    )
    return ProfileRetentionReport(
        generated_at=generated_at,
        retention_period=PROFILE_RETENTION_PERIOD,
        candidates=candidates,
    )


def apply_profile_retention_cleanup(
    database_session: Session,
    *,
    clock: Clock = utc_now,
) -> ProfileRetentionReport:
    """Delete currently eligible profile-specific rows in one transaction."""
    with database_session.begin():
        report = report_profile_retention_candidates(
            database_session,
            clock=clock,
        )
        candidate_ids = tuple(
            candidate.profile_id for candidate in report.candidates
        )
        if not candidate_ids:
            return report

        database_session.execute(
            delete(ProfileGame).where(
                ProfileGame.profile_id.in_(candidate_ids)
            )
        )
        database_session.execute(
            delete(SteamAccessSession).where(
                SteamAccessSession.profile_id.in_(candidate_ids)
            )
        )
        database_session.execute(
            delete(Profile).where(Profile.id.in_(candidate_ids))
        )

    return report
