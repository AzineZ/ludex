from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.abuse.steam import RateLimitExceeded
from app.database import Base
from app.integrations.steam.achievements import (
    ACHIEVEMENT_GAMES_PER_TRIGGER,
    run_achievement_fetch,
    select_achievement_games,
)
from app.integrations.steam.client import (
    SteamAchievementStatus,
    SteamAchievementSummary,
    SteamAPIError,
)
from app.maintenance.retention import apply_profile_retention_cleanup
from app.models import Profile, ProfileGameAchievement, SteamAccessSession
from app.recommendations.automatic import load_played_games, rank_played_games
from tests.recommendations.recommendation_api_support import _owned_game


NOW = datetime(2026, 10, 19, tzinfo=UTC)
HMAC_KEY = b"test-rate-limit-key-with-32-bytes!!"


class FakeSteam:
    """Answer achievement requests from a table and record each call."""

    def __init__(self, answers: dict[int, object]) -> None:
        self.answers = answers
        self.calls: list[tuple[str, int]] = []
        self.closed = False

    def get_player_achievements(
        self,
        steam_id: str,
        steam_app_id: int,
    ) -> SteamAchievementSummary:
        self.calls.append((steam_id, steam_app_id))
        answer = self.answers.get(
            steam_app_id,
            SteamAchievementSummary(SteamAchievementStatus.NO_ACHIEVEMENTS),
        )
        if isinstance(answer, Exception):
            raise answer
        return answer

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def session_factory() -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, expire_on_commit=False)
    engine.dispose()


def _add_library(
    factory: sessionmaker[Session],
    game_count: int = 3,
) -> int:
    with factory() as session:
        profile = Profile(
            id=1,
            steam_id="76561198000000001",
            display_name="Player",
        )
        session.add_all(
            _owned_game(
                profile,
                100 + index,
                f"Game {index}",
                playtime_minutes=600 - index,
                last_played_at=NOW - timedelta(days=index),
            )
            for index in range(game_count)
        )
        session.commit()
        return profile.id


def _run(
    factory: sessionmaker[Session],
    steam: FakeSteam,
    *,
    reserve=lambda *args, **kwargs: None,
) -> int:
    return run_achievement_fetch(
        1,
        hmac_key=HMAC_KEY,
        enabled=True,
        session_factory=factory,
        client_factory=lambda: steam,
        reserve=reserve,
        clock=lambda: NOW,
    )


def _stored(factory: sessionmaker[Session]) -> dict[int, tuple]:
    with factory() as session:
        return {
            row.steam_app_id: (
                row.status,
                row.unlocked_count,
                row.total_count,
                row.playtime_minutes_at_fetch,
            )
            for row in session.scalars(select(ProfileGameAchievement))
        }


def test_disabled_fetch_does_nothing(
    session_factory: sessionmaker[Session],
) -> None:
    _add_library(session_factory)
    steam = FakeSteam({})

    assert run_achievement_fetch(
        1,
        hmac_key=HMAC_KEY,
        enabled=False,
        session_factory=session_factory,
        client_factory=lambda: steam,
    ) == 0
    assert steam.calls == []


def test_fetch_stores_only_counts_for_each_outcome(
    session_factory: sessionmaker[Session],
) -> None:
    _add_library(session_factory)
    steam = FakeSteam(
        {
            100: SteamAchievementSummary(
                SteamAchievementStatus.OK,
                unlocked_count=35,
                total_count=42,
            ),
            101: SteamAchievementSummary(SteamAchievementStatus.PRIVATE),
            102: SteamAPIError("Steam rejected the achievement request."),
        }
    )

    stored = _run(session_factory, steam)

    assert stored == 3
    assert steam.closed
    assert [call[1] for call in steam.calls] == [100, 101, 102]
    assert _stored(session_factory) == {
        100: ("ok", 35, 42, 600),
        101: ("private", None, None, 599),
        102: ("error", None, None, 598),
    }


def test_only_top_twenty_and_changed_or_failed_games_are_refetched(
    session_factory: sessionmaker[Session],
) -> None:
    _add_library(session_factory, game_count=ACHIEVEMENT_GAMES_PER_TRIGGER + 5)
    with session_factory() as session:
        first = select_achievement_games(session, 1, now=NOW)
    assert len(first) == ACHIEVEMENT_GAMES_PER_TRIGGER

    _run(session_factory, FakeSteam({102: SteamAPIError("failed")}))
    with session_factory() as session:
        # Unchanged games are skipped; the failed one is retried.
        assert select_achievement_games(session, 1, now=NOW) == [(102, 598)]
        session.get(ProfileGameAchievement, (1, 100)).playtime_minutes_at_fetch = 500
        session.commit()
        assert [game[0] for game in select_achievement_games(session, 1, now=NOW)] == [
            100,
            102,
        ]


def test_spent_budget_stops_the_run_quietly(
    session_factory: sessionmaker[Session],
) -> None:
    _add_library(session_factory)
    steam = FakeSteam({})
    reservations: list[int] = []

    def reserve(*args: object, **kwargs: object) -> None:
        if len(reservations) == 1:
            raise RateLimitExceeded(60)
        reservations.append(1)

    assert _run(session_factory, steam, reserve=reserve) == 1
    assert [call[1] for call in steam.calls] == [100]


def test_unexpected_failures_never_escape(
    session_factory: sessionmaker[Session],
) -> None:
    _add_library(session_factory)

    def broken_client() -> FakeSteam:
        raise RuntimeError("misconfigured")

    assert run_achievement_fetch(
        1,
        hmac_key=HMAC_KEY,
        enabled=True,
        session_factory=session_factory,
        client_factory=broken_client,
        reserve=lambda *args, **kwargs: None,
        clock=lambda: NOW,
    ) == 0


def test_achievement_share_raises_interest_gradually(
    session_factory: sessionmaker[Session],
) -> None:
    _add_library(session_factory, game_count=2)
    _run(
        session_factory,
        FakeSteam(
            {
                101: SteamAchievementSummary(
                    SteamAchievementStatus.OK,
                    unlocked_count=10,
                    total_count=10,
                ),
            }
        ),
    )

    with session_factory() as session:
        games = {
            game.steam_app_id: game for game in load_played_games(session, 1)
        }
        ranked = rank_played_games(tuple(games.values()), NOW)

    assert games[100].achievement_share is None
    assert games[101].achievement_share == 1.0
    without_achievements = replace(games[101], achievement_share=None)
    assert games[101].interest_score(NOW) == pytest.approx(
        1.5 * without_achievements.interest_score(NOW)
    )
    assert replace(games[101], achievement_share=0.4).interest_score(
        NOW
    ) == pytest.approx(1.2 * without_achievements.interest_score(NOW))
    # 100% achievements outweighs one more day and minute of play.
    assert [game.steam_app_id for game in ranked] == [101, 100]


def test_retention_deletes_achievement_counts_with_the_profile(
    session_factory: sessionmaker[Session],
) -> None:
    _add_library(session_factory, game_count=1)
    _run(
        session_factory,
        FakeSteam(
            {
                100: SteamAchievementSummary(
                    SteamAchievementStatus.OK,
                    unlocked_count=1,
                    total_count=2,
                )
            }
        ),
    )

    with session_factory() as session:
        session.add(
            SteamAccessSession(
                token_digest=b"x" * 32,
                profile_id=1,
                created_at=NOW - timedelta(days=60),
                expires_at=NOW - timedelta(days=53),
            )
        )
        session.commit()
        apply_profile_retention_cleanup(session, clock=lambda: NOW)

    assert _stored(session_factory) == {}
