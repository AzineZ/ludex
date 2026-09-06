from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session

from app.database import Base
from app.maintenance.retention import (
    PROFILE_RETENTION_PERIOD,
    ProfileRetentionCandidate,
    apply_profile_retention_cleanup,
    report_profile_retention_candidates,
)
from app.models import (
    Game,
    GameIGDBMetadataTerm,
    IGDBMetadataTerm,
    Profile,
    ProfileGame,
    SteamAccessSession,
)


NOW = datetime(2026, 9, 2, 12, tzinfo=UTC)


def _foreign_key_engine():
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _) -> None:
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    return engine


def _profile(session: Session, suffix: int) -> Profile:
    profile = Profile(
        steam_id=f"7656119800000{suffix:04d}",
        display_name=f"Player {suffix}",
    )
    session.add(profile)
    session.flush()
    return profile


def _expired_session(
    profile: Profile,
    digest_byte: int,
    ended_at: datetime,
) -> SteamAccessSession:
    return SteamAccessSession(
        token_digest=bytes([digest_byte]) * 32,
        profile=profile,
        created_at=ended_at - timedelta(days=7),
        expires_at=ended_at,
    )


def _revoked_session(
    profile: Profile,
    digest_byte: int,
    ended_at: datetime,
) -> SteamAccessSession:
    return SteamAccessSession(
        token_digest=bytes([digest_byte]) * 32,
        profile=profile,
        created_at=ended_at - timedelta(days=1),
        expires_at=ended_at + timedelta(days=6),
        revoked_at=ended_at,
    )


def _active_session(
    profile: Profile,
    digest_byte: int,
) -> SteamAccessSession:
    return SteamAccessSession(
        token_digest=bytes([digest_byte]) * 32,
        profile=profile,
        created_at=NOW - timedelta(days=1),
        expires_at=NOW + timedelta(days=6),
    )


def test_report_identifies_only_profiles_past_the_retention_boundary() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        legacy = _profile(session, 1)
        active = _profile(session, 2)
        recent = _profile(session, 3)
        exact_boundary = _profile(session, 4)
        old_revoked = _profile(session, 5)
        recent_after_old = _profile(session, 6)

        session.add_all(
            [
                _expired_session(
                    active,
                    1,
                    NOW - timedelta(days=45),
                ),
                _active_session(active, 2),
                _expired_session(
                    recent,
                    3,
                    NOW - timedelta(days=29),
                ),
                _expired_session(
                    exact_boundary,
                    4,
                    NOW - PROFILE_RETENTION_PERIOD,
                ),
                _revoked_session(
                    old_revoked,
                    5,
                    NOW - timedelta(days=31),
                ),
                _expired_session(
                    recent_after_old,
                    6,
                    NOW - timedelta(days=60),
                ),
                _revoked_session(
                    recent_after_old,
                    7,
                    NOW - timedelta(days=2),
                ),
            ]
        )
        session.commit()

        report = report_profile_retention_candidates(
            session,
            clock=lambda: NOW,
        )

        assert report.generated_at == NOW
        assert report.retention_period == timedelta(days=30)
        assert report.candidates == (
            ProfileRetentionCandidate(
                profile_id=exact_boundary.id,
                last_session_ended_at=NOW - timedelta(days=30),
                session_count=1,
                ownership_count=0,
            ),
            ProfileRetentionCandidate(
                profile_id=old_revoked.id,
                last_session_ended_at=NOW - timedelta(days=31),
                session_count=1,
                ownership_count=0,
            ),
        )
        assert report.candidate_profile_count == 2
        assert report.candidate_session_count == 2
        assert report.candidate_ownership_count == 0
        assert legacy.id not in {
            candidate.profile_id for candidate in report.candidates
        }

    engine.dispose()


def test_report_counts_candidate_sessions_and_profile_ownerships() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        candidate = _profile(session, 1)
        retained = _profile(session, 2)
        shared_game = Game(steam_app_id=10, name="Shared Game")
        candidate_only_game = Game(steam_app_id=20, name="Candidate Game")
        session.add_all(
            [
                shared_game,
                candidate_only_game,
                ProfileGame(profile=candidate, game=shared_game),
                ProfileGame(profile=candidate, game=candidate_only_game),
                ProfileGame(profile=retained, game=shared_game),
                _expired_session(
                    candidate,
                    1,
                    NOW - timedelta(days=50),
                ),
                _revoked_session(
                    candidate,
                    2,
                    NOW - timedelta(days=40),
                ),
                _active_session(retained, 3),
            ]
        )
        session.commit()

        report = report_profile_retention_candidates(
            session,
            clock=lambda: NOW,
        )

        assert report.candidates == (
            ProfileRetentionCandidate(
                profile_id=candidate.id,
                last_session_ended_at=NOW - timedelta(days=40),
                session_count=2,
                ownership_count=2,
            ),
        )
        assert report.candidate_session_count == 2
        assert report.candidate_ownership_count == 2

    engine.dispose()


def test_report_is_read_only_for_profiles_sessions_ownerships_and_games() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        candidate = _profile(session, 1)
        game = Game(steam_app_id=10, name="Reusable Game")
        session.add_all(
            [
                game,
                ProfileGame(profile=candidate, game=game),
                _expired_session(
                    candidate,
                    1,
                    NOW - timedelta(days=31),
                ),
            ]
        )
        session.commit()

        report_profile_retention_candidates(session, clock=lambda: NOW)

        assert not session.deleted
        assert not session.dirty
        assert session.scalar(select(func.count()).select_from(Profile)) == 1
        assert session.scalar(
            select(func.count()).select_from(SteamAccessSession)
        ) == 1
        assert session.scalar(
            select(func.count()).select_from(ProfileGame)
        ) == 1
        assert session.scalar(select(func.count()).select_from(Game)) == 1

    engine.dispose()


def test_report_orders_candidates_by_internal_profile_id() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        profiles = [_profile(session, suffix) for suffix in range(1, 4)]
        session.add_all(
            [
                _expired_session(
                    profile,
                    suffix,
                    NOW - timedelta(days=30 + suffix),
                )
                for suffix, profile in enumerate(profiles, start=1)
            ]
        )
        session.commit()

        report = report_profile_retention_candidates(
            session,
            clock=lambda: NOW,
        )

        assert tuple(
            candidate.profile_id for candidate in report.candidates
        ) == tuple(profile.id for profile in profiles)

    engine.dispose()


def test_report_uses_one_bounded_aggregate_read() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        for suffix in range(1, 21):
            profile = _profile(session, suffix)
            session.add(
                _expired_session(
                    profile,
                    suffix,
                    NOW - timedelta(days=31 + suffix),
                )
            )
        session.commit()

        statements: list[str] = []

        def count_selects(_, __, statement, ___, ____, _____) -> None:
            if statement.lstrip().upper().startswith("SELECT"):
                statements.append(statement)

        event.listen(engine, "before_cursor_execute", count_selects)
        try:
            report = report_profile_retention_candidates(
                session,
                clock=lambda: NOW,
            )
        finally:
            event.remove(engine, "before_cursor_execute", count_selects)

        assert report.candidate_profile_count == 20
        assert len(statements) == 1

    engine.dispose()


def test_report_rejects_a_timezone_naive_clock() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        with pytest.raises(
            ValueError,
            match="retention-cleanup clock must be timezone-aware",
        ):
            report_profile_retention_candidates(
                session,
                clock=lambda: NOW.replace(tzinfo=None),
            )

    engine.dispose()


def test_apply_deletes_only_eligible_profile_specific_rows() -> None:
    engine = _foreign_key_engine()

    with Session(engine) as session:
        candidate = _profile(session, 1)
        active = _profile(session, 2)
        legacy = _profile(session, 3)
        shared_game = Game(
            steam_app_id=10,
            name="Shared Factual Game",
            igdb_status="ready",
        )
        candidate_game = Game(
            steam_app_id=20,
            name="Candidate Factual Game",
            igdb_status="ready",
        )
        genre = IGDBMetadataTerm(
            kind="genre",
            igdb_id=5,
            name="Shooter",
        )
        session.add_all(
            [
                shared_game,
                candidate_game,
                genre,
                ProfileGame(profile=candidate, game=shared_game),
                ProfileGame(profile=candidate, game=candidate_game),
                ProfileGame(profile=active, game=shared_game),
                GameIGDBMetadataTerm(game=candidate_game, term=genre),
                _expired_session(
                    candidate,
                    1,
                    NOW - timedelta(days=31),
                ),
                _active_session(active, 2),
            ]
        )
        session.flush()
        candidate_id = candidate.id
        active_id = active.id
        legacy_id = legacy.id
        session.commit()

        result = apply_profile_retention_cleanup(
            session,
            clock=lambda: NOW,
        )

        assert result.candidate_profile_count == 1
        assert result.candidate_session_count == 1
        assert result.candidate_ownership_count == 2
        assert session.get(Profile, candidate_id) is None
        assert session.get(Profile, active_id) is not None
        assert session.get(Profile, legacy_id) is not None
        assert session.scalar(
            select(func.count()).select_from(SteamAccessSession)
        ) == 1
        assert session.scalar(
            select(func.count()).select_from(ProfileGame)
        ) == 1
        assert session.scalar(select(func.count()).select_from(Game)) == 2
        assert session.scalar(
            select(func.count()).select_from(IGDBMetadataTerm)
        ) == 1
        assert session.scalar(
            select(func.count()).select_from(GameIGDBMetadataTerm)
        ) == 1

    engine.dispose()


def test_apply_rolls_back_every_delete_when_the_transaction_fails() -> None:
    engine = _foreign_key_engine()

    with Session(engine) as session:
        candidate = _profile(session, 1)
        game = Game(steam_app_id=10, name="Reusable Game")
        session.add_all(
            [
                game,
                ProfileGame(profile=candidate, game=game),
                _expired_session(
                    candidate,
                    1,
                    NOW - timedelta(days=31),
                ),
            ]
        )
        session.commit()

        def fail_profile_delete(_, __, statement, ___, ____, _____) -> None:
            if statement.lstrip().upper().startswith("DELETE FROM PROFILES"):
                raise RuntimeError("simulated cleanup failure")

        event.listen(engine, "before_cursor_execute", fail_profile_delete)
        try:
            with pytest.raises(
                RuntimeError,
                match="simulated cleanup failure",
            ):
                apply_profile_retention_cleanup(
                    session,
                    clock=lambda: NOW,
                )
        finally:
            event.remove(engine, "before_cursor_execute", fail_profile_delete)

        assert session.scalar(select(func.count()).select_from(Profile)) == 1
        assert session.scalar(
            select(func.count()).select_from(SteamAccessSession)
        ) == 1
        assert session.scalar(
            select(func.count()).select_from(ProfileGame)
        ) == 1
        assert session.scalar(select(func.count()).select_from(Game)) == 1

    engine.dispose()


def test_apply_with_no_candidates_performs_no_deletes() -> None:
    engine = _foreign_key_engine()

    with Session(engine) as session:
        active = _profile(session, 1)
        session.add(_active_session(active, 1))
        session.commit()
        delete_statements: list[str] = []

        def count_deletes(_, __, statement, ___, ____, _____) -> None:
            if statement.lstrip().upper().startswith("DELETE"):
                delete_statements.append(statement)

        event.listen(engine, "before_cursor_execute", count_deletes)
        try:
            result = apply_profile_retention_cleanup(
                session,
                clock=lambda: NOW,
            )
        finally:
            event.remove(engine, "before_cursor_execute", count_deletes)

        assert result.candidates == ()
        assert delete_statements == []

    engine.dispose()
