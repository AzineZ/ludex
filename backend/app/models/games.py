"""Store shared Steam games and their cached IGDB match state."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.igdb_metadata import GameIGDBMetadataTerm
    from app.models.profiles import ProfileGame


class Game(Base):
    """Represent Steam game metadata shared across local profiles."""

    __tablename__ = "games"
    __table_args__ = (
        CheckConstraint(
            "igdb_status IN "
            "('pending', 'ready', 'missing', 'ambiguous')",
            name="ck_games_igdb_status",
        ),
        CheckConstraint(
            "igdb_game_id IS NULL OR igdb_game_id > 0",
            name="ck_games_igdb_game_id_positive",
        ),
        CheckConstraint(
            "time_to_beat_hastily_seconds IS NULL "
            "OR time_to_beat_hastily_seconds >= 0",
            name="ck_games_hastily_seconds_nonnegative",
        ),
        CheckConstraint(
            "time_to_beat_normally_seconds IS NULL "
            "OR time_to_beat_normally_seconds >= 0",
            name="ck_games_normally_seconds_nonnegative",
        ),
        CheckConstraint(
            "time_to_beat_completely_seconds IS NULL "
            "OR time_to_beat_completely_seconds >= 0",
            name="ck_games_completely_seconds_nonnegative",
        ),
        CheckConstraint(
            "time_to_beat_submission_count IS NULL "
            "OR time_to_beat_submission_count >= 0",
            name="ck_games_time_submission_count_nonnegative",
        ),
    )
    steam_app_id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=False,
    )
    name: Mapped[str] = mapped_column(String(255))
    icon_url: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    igdb_game_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        index=True,
    )
    igdb_status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
        server_default="pending",
        index=True,
    )
    igdb_last_attempted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    igdb_last_error: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    igdb_enriched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    igdb_metadata_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    summary: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    first_release_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    cover_image_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    time_to_beat_hastily_seconds: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )
    time_to_beat_normally_seconds: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )
    time_to_beat_completely_seconds: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )
    time_to_beat_submission_count: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    time_to_beat_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    profile_games: Mapped[list[ProfileGame]] = relationship(
        back_populates="game",
        passive_deletes=True,
    )
    metadata_term_links: Mapped[list[GameIGDBMetadataTerm]] = relationship(
        back_populates="game",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
