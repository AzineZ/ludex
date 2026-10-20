"""Fetch achievement counts for a visitor's top games in the background."""

from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime
import logging
import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.abuse.steam import RateLimitExceeded, reserve_achievement_call
from app.config import settings
from app.database import SessionLocal
from app.integrations.steam.client import SteamAPIError, SteamClient
from app.models import Profile, ProfileGameAchievement
from app.recommendations.automatic import load_played_games, rank_played_games

ACHIEVEMENT_GAMES_PER_TRIGGER = 20

SessionFactory = Callable[[], Session]
ClientFactory = Callable[[], SteamClient]
Reserve = Callable[..., None]

# Logged under uvicorn's error logger so lines reach the Render log, like the
# Checkpoint 14 IGDB run.
STEAM_ACHIEVEMENTS_LOGGER = "uvicorn.error.ludex.steam_achievements"
_LOGGER = logging.getLogger(STEAM_ACHIEVEMENTS_LOGGER)
_LOGGER.setLevel(logging.INFO)


def select_achievement_games(
    session: Session,
    profile_id: int,
    *,
    now: datetime,
) -> list[tuple[int, int]]:
    """Return ``(steam_app_id, playtime_minutes)`` for top games to fetch.

    Only the top 20 played games are considered. A game is fetched when it
    has never been fetched, the last attempt failed, or its playtime has
    grown since the last fetch.
    """
    ranked = rank_played_games(load_played_games(session, profile_id), now)
    top = ranked[:ACHIEVEMENT_GAMES_PER_TRIGGER]
    if not top:
        return []

    existing = {
        row.steam_app_id: row
        for row in session.scalars(
            select(ProfileGameAchievement).where(
                ProfileGameAchievement.profile_id == profile_id,
                ProfileGameAchievement.steam_app_id.in_(
                    [game.steam_app_id for game in top]
                ),
            )
        )
    }
    selected: list[tuple[int, int]] = []
    for game in top:
        row = existing.get(game.steam_app_id)
        if (
            row is None
            or row.status == "error"
            or row.playtime_minutes_at_fetch < game.playtime_minutes
        ):
            selected.append((game.steam_app_id, game.playtime_minutes))
    return selected


def _create_steam_client() -> SteamClient:
    return SteamClient(settings.steam_api_key.get_secret_value())


def run_achievement_fetch(
    profile_id: int,
    *,
    hmac_key: bytes,
    enabled: bool | None = None,
    session_factory: SessionFactory = SessionLocal,
    client_factory: ClientFactory = _create_steam_client,
    reserve: Reserve = reserve_achievement_call,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> int:
    """Fetch and store achievement counts for one profile, never raising.

    Each call first reserves the separate daily achievement budget; when it
    is spent the run stops and the next sign-in or refresh resumes. Only
    counts are stored. Returns the number of games stored.
    """
    if not (
        settings.steam_achievements_enabled if enabled is None else enabled
    ):
        return 0

    started_at = time.monotonic()
    outcomes: Counter[str] = Counter()
    stop_reason = "complete"
    client: SteamClient | None = None
    try:
        with session_factory() as session:
            steam_id = session.scalar(
                select(Profile.steam_id).where(Profile.id == profile_id)
            )
            if steam_id is None:
                return 0
            games = select_achievement_games(session, profile_id, now=clock())

            for steam_app_id, playtime_minutes in games:
                try:
                    reserve(session, hmac_key, now=clock())
                except RateLimitExceeded:
                    stop_reason = "budget_exhausted"
                    break

                if client is None:
                    client = client_factory()
                try:
                    summary = client.get_player_achievements(
                        steam_id,
                        steam_app_id,
                    )
                    status = summary.status.value
                    unlocked, total = summary.unlocked_count, summary.total_count
                except SteamAPIError:
                    status, unlocked, total = "error", None, None

                session.merge(
                    ProfileGameAchievement(
                        profile_id=profile_id,
                        steam_app_id=steam_app_id,
                        status=status,
                        unlocked_count=unlocked,
                        total_count=total,
                        playtime_minutes_at_fetch=playtime_minutes,
                        fetched_at=clock(),
                    )
                )
                session.commit()
                outcomes[status] += 1
    except Exception as error:
        _LOGGER.warning(
            "event=steam_achievements_failed error_category=%s "
            "stored=%d duration_ms=%d",
            type(error).__name__,
            sum(outcomes.values()),
            round((time.monotonic() - started_at) * 1000),
        )
        return sum(outcomes.values())
    finally:
        if client is not None:
            client.close()

    _LOGGER.info(
        "event=steam_achievements_completed stop_reason=%s stored=%d "
        "ok=%d no_achievements=%d private=%d error=%d duration_ms=%d",
        stop_reason,
        sum(outcomes.values()),
        outcomes["ok"],
        outcomes["no_achievements"],
        outcomes["private"],
        outcomes["error"],
        round((time.monotonic() - started_at) * 1000),
    )
    return sum(outcomes.values())
