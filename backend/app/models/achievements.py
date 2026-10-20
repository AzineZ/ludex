"""Store per-profile Steam achievement counts for top played games."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ProfileGameAchievement(Base):
    """Hold only aggregate achievement counts for one owned game.

    Individual achievement names are never stored. Rows belong to the owned
    game link, so removing a game from a library or deleting the profile
    removes them too.
    """

    __tablename__ = "profile_game_achievements"
    __table_args__ = (
        ForeignKeyConstraint(
            ["profile_id", "steam_app_id"],
            ["profile_games.profile_id", "profile_games.steam_app_id"],
            ondelete="CASCADE",
            name="fk_profile_game_achievements_profile_game",
        ),
        CheckConstraint(
            "status IN ('ok', 'no_achievements', 'private', 'error')",
            name="ck_profile_game_achievements_status",
        ),
        CheckConstraint(
            "unlocked_count IS NULL OR unlocked_count >= 0",
            name="ck_profile_game_achievements_unlocked_nonnegative",
        ),
        CheckConstraint(
            "total_count IS NULL OR total_count >= 0",
            name="ck_profile_game_achievements_total_nonnegative",
        ),
        CheckConstraint(
            "unlocked_count IS NULL OR total_count IS NULL "
            "OR unlocked_count <= total_count",
            name="ck_profile_game_achievements_unlocked_within_total",
        ),
        CheckConstraint(
            "playtime_minutes_at_fetch >= 0",
            name="ck_profile_game_achievements_playtime_nonnegative",
        ),
    )

    profile_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    steam_app_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    status: Mapped[str] = mapped_column(String(20))
    unlocked_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    playtime_minutes_at_fetch: Mapped[int] = mapped_column(BigInteger)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
