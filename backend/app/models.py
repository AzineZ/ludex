from __future__ import annotations
from datetime import datetime
from sqlalchemy import BigInteger, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Profile(Base):
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
    __tablename__ = "games"
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

    profile_games: Mapped[list[ProfileGame]] = relationship(
        back_populates="game",
        passive_deletes=True,
    )


class ProfileGame(Base):
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
