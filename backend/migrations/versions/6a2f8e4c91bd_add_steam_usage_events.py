"""add expiring Steam usage events

Revision ID: 6a2f8e4c91bd
Revises: d52e7a91c304
Create Date: 2026-09-06 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "6a2f8e4c91bd"
down_revision: Union[str, Sequence[str], None] = "d52e7a91c304"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add opaque, expiring durable counters for hosted Steam actions."""
    op.create_table(
        "steam_usage_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("subject_digest", sa.LargeBinary(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "category IN ('session_create', 'provider_call', 'refresh')",
            name="ck_steam_usage_events_category",
        ),
        sa.CheckConstraint(
            "expires_at > created_at",
            name="ck_steam_usage_events_expiration_order",
        ),
        sa.CheckConstraint(
            "length(subject_digest) = 32",
            name="ck_steam_usage_events_subject_digest_length",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_steam_usage_events_category_created_at",
        "steam_usage_events",
        ["category", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_steam_usage_events_expires_at",
        "steam_usage_events",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_steam_usage_events_subject_created_at",
        "steam_usage_events",
        ["category", "subject_digest", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Remove only hosted Steam usage events."""
    op.drop_index(
        "ix_steam_usage_events_subject_created_at",
        table_name="steam_usage_events",
    )
    op.drop_index(
        "ix_steam_usage_events_expires_at",
        table_name="steam_usage_events",
    )
    op.drop_index(
        "ix_steam_usage_events_category_created_at",
        table_name="steam_usage_events",
    )
    op.drop_table("steam_usage_events")
