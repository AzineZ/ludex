"""remove Ludex-owned Gemini prompt counters

Revision ID: 8e1a4c9d7b20
Revises: 7c4f1e2a9b06
Create Date: 2026-09-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8e1a4c9d7b20"
down_revision: Union[str, Sequence[str], None] = "7c4f1e2a9b06"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Remove prompt counters now that Google enforces provider limits."""
    op.drop_table("gemini_prompt_usage_events")
    op.drop_table("gemini_prompt_reservations")


def downgrade() -> None:
    """Restore the former reservation, usage, and circuit schema."""
    op.create_table(
        "gemini_prompt_reservations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("access_session_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "completed_at IS NULL OR completed_at >= created_at",
            name="ck_gemini_prompt_reservations_completion_order",
        ),
        sa.CheckConstraint(
            "expires_at > created_at",
            name="ck_gemini_prompt_reservations_expiration_order",
        ),
        sa.ForeignKeyConstraint(
            ["access_session_id"],
            ["steam_access_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_gemini_prompt_reservations_session_created_at",
        "gemini_prompt_reservations",
        ["access_session_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "uq_gemini_prompt_reservations_active_session",
        "gemini_prompt_reservations",
        ["access_session_id"],
        unique=True,
        postgresql_where=sa.text("completed_at IS NULL"),
        sqlite_where=sa.text("completed_at IS NULL"),
    )

    op.create_table(
        "gemini_prompt_usage_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("reservation_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "provider_limited_until",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.CheckConstraint(
            "expires_at > created_at",
            name="ck_gemini_prompt_usage_events_expiration_order",
        ),
        sa.CheckConstraint(
            "provider_limited_until IS NULL "
            "OR provider_limited_until >= created_at",
            name="ck_gemini_prompt_usage_events_provider_limit_order",
        ),
        sa.ForeignKeyConstraint(
            ["reservation_id"],
            ["gemini_prompt_reservations.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_gemini_prompt_usage_events_created_at",
        "gemini_prompt_usage_events",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_gemini_prompt_usage_events_reservation_created_at",
        "gemini_prompt_usage_events",
        ["reservation_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_gemini_prompt_usage_events_limited_until",
        "gemini_prompt_usage_events",
        ["provider_limited_until"],
        unique=False,
    )
