"""Store shared IGDB metadata terms and their game links."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.games import Game


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
