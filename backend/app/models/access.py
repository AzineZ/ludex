"""Store browser access sessions and Steam abuse-control events."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    LargeBinary,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.profiles import Profile


class SteamAccessSession(Base):
    """Authorize one browser to access one cached Steam profile."""

    __tablename__ = "steam_access_sessions"
    __table_args__ = (
        CheckConstraint(
            "length(token_digest) = 32",
            name="ck_steam_access_sessions_digest_length",
        ),
        CheckConstraint(
            "expires_at > created_at",
            name="ck_steam_access_sessions_expiration_order",
        ),
        CheckConstraint(
            "revoked_at IS NULL OR revoked_at >= created_at",
            name="ck_steam_access_sessions_revocation_order",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    token_digest: Mapped[bytes] = mapped_column(
        LargeBinary(32),
        unique=True,
        index=True,
    )
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"),
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        index=True,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    profile: Mapped[Profile] = relationship(
        back_populates="access_sessions",
    )


class SteamUsageEvent(Base):
    """Store one expiring, identifier-free hosted Steam budget event."""

    __tablename__ = "steam_usage_events"
    __table_args__ = (
        CheckConstraint(
            "category IN ('session_create', 'provider_call', 'refresh')",
            name="ck_steam_usage_events_category",
        ),
        CheckConstraint(
            "length(subject_digest) = 32",
            name="ck_steam_usage_events_subject_digest_length",
        ),
        CheckConstraint(
            "expires_at > created_at",
            name="ck_steam_usage_events_expiration_order",
        ),
        Index(
            "ix_steam_usage_events_category_created_at",
            "category",
            "created_at",
        ),
        Index(
            "ix_steam_usage_events_subject_created_at",
            "category",
            "subject_digest",
            "created_at",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(String(32))
    subject_digest: Mapped[bytes] = mapped_column(LargeBinary(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        index=True,
    )
