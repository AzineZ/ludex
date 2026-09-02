"""add steam access sessions

Revision ID: d52e7a91c304
Revises: 12154eb07460
Create Date: 2026-09-02 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d52e7a91c304"
down_revision: Union[str, Sequence[str], None] = "12154eb07460"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add digest-only browser access sessions without changing profiles."""
    op.create_table(
        "steam_access_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("token_digest", sa.LargeBinary(length=32), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "length(token_digest) = 32",
            name="ck_steam_access_sessions_digest_length",
        ),
        sa.CheckConstraint(
            "expires_at > created_at",
            name="ck_steam_access_sessions_expiration_order",
        ),
        sa.CheckConstraint(
            "revoked_at IS NULL OR revoked_at >= created_at",
            name="ck_steam_access_sessions_revocation_order",
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["profiles.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_steam_access_sessions_expires_at",
        "steam_access_sessions",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_steam_access_sessions_profile_id",
        "steam_access_sessions",
        ["profile_id"],
        unique=False,
    )
    op.create_index(
        "ix_steam_access_sessions_token_digest",
        "steam_access_sessions",
        ["token_digest"],
        unique=True,
    )


def downgrade() -> None:
    """Remove only the access-session table."""
    op.drop_index(
        "ix_steam_access_sessions_token_digest",
        table_name="steam_access_sessions",
    )
    op.drop_index(
        "ix_steam_access_sessions_profile_id",
        table_name="steam_access_sessions",
    )
    op.drop_index(
        "ix_steam_access_sessions_expires_at",
        table_name="steam_access_sessions",
    )
    op.drop_table("steam_access_sessions")
