from __future__ import annotations
from datetime import datetime
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Profile(Base):
    """Represent a locally saved Steam user profile."""

    __tablename__ = "profiles"
    id: Mapped[int] = mapped_column(primary_key=True)
    steam_id: Mapped[str] = mapped_column(
        String(20),
        unique=True,
        index=True,
    )
    display_name: Mapped[str] = mapped_column(String(100))
    profile_url: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    avatar_url: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    owned_games: Mapped[list[ProfileGame]] = relationship(
        back_populates="profile",
        cascade="all, delete-orphan",
    )


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


class ProfileGame(Base):
    """Represent a profile's ownership and playtime for one game."""

    __tablename__ = "profile_games"

    profile_id: Mapped[int] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    steam_app_id: Mapped[int] = mapped_column(
        ForeignKey("games.steam_app_id", ondelete="CASCADE"),
        primary_key=True,
    )
    playtime_minutes: Mapped[int] = mapped_column(
        BigInteger,
        default=0,
        server_default="0",
    )
    recent_playtime_minutes: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )
    last_played_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    profile: Mapped[Profile] = relationship(
        back_populates="owned_games",
    )
    game: Mapped[Game] = relationship(
        back_populates="profile_games",
    )


class IGDBMetadataTerm(Base):
    """Represent a reusable named IGDB metadata value."""

    __tablename__ = "igdb_metadata_terms"
    __table_args__ = (
        UniqueConstraint(
            "kind",
            "igdb_id",
            name="uq_igdb_metadata_terms_kind_igdb_id",
        ),
        CheckConstraint(
            "kind IN ('genre', 'theme', 'keyword', 'game_mode')",
            name="ck_igdb_metadata_terms_kind",
        ),
        CheckConstraint(
            "igdb_id > 0",
            name="ck_igdb_metadata_terms_igdb_id_positive",
        ),
        Index(
            "ix_igdb_metadata_terms_kind_name",
            "kind",
            "name",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(20))
    igdb_id: Mapped[int] = mapped_column(BigInteger)
    name: Mapped[str] = mapped_column(String(255))

    game_links: Mapped[list[GameIGDBMetadataTerm]] = relationship(
        back_populates="term",
        passive_deletes=True,
    )


class GameIGDBMetadataTerm(Base):
    """Associate one shared Steam game with an IGDB metadata term."""

    __tablename__ = "game_igdb_metadata_terms"
    __table_args__ = (
        Index(
            "ix_game_igdb_metadata_terms_term_id",
            "term_id",
        ),
    )

    steam_app_id: Mapped[int] = mapped_column(
        ForeignKey("games.steam_app_id", ondelete="CASCADE"),
        primary_key=True,
    )
    term_id: Mapped[int] = mapped_column(
        ForeignKey("igdb_metadata_terms.id", ondelete="CASCADE"),
        primary_key=True,
    )

    game: Mapped[Game] = relationship(
        back_populates="metadata_term_links",
    )
    term: Mapped[IGDBMetadataTerm] = relationship(
        back_populates="game_links",
    )
