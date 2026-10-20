"""add per-profile achievement counts and their Steam budget category

Revision ID: c8d1f4a6e2b7
Revises: b4c7e2d91f35
Create Date: 2026-10-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c8d1f4a6e2b7"
down_revision: Union[str, Sequence[str], None] = "b4c7e2d91f35"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD_CATEGORIES = "category IN ('session_create', 'provider_call', 'refresh')"
_NEW_CATEGORIES = (
    "category IN ("
    "'session_create', 'provider_call', 'refresh', 'achievement_call'"
    ")"
)


def upgrade() -> None:
    """Add aggregate achievement counts and allow achievement budget events."""
    op.create_table(
        "profile_game_achievements",
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("steam_app_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("unlocked_count", sa.Integer(), nullable=True),
        sa.Column("total_count", sa.Integer(), nullable=True),
        sa.Column("playtime_minutes_at_fetch", sa.BigInteger(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('ok', 'no_achievements', 'private', 'error')",
            name="ck_profile_game_achievements_status",
        ),
        sa.CheckConstraint(
            "unlocked_count IS NULL OR unlocked_count >= 0",
            name="ck_profile_game_achievements_unlocked_nonnegative",
        ),
        sa.CheckConstraint(
            "total_count IS NULL OR total_count >= 0",
            name="ck_profile_game_achievements_total_nonnegative",
        ),
        sa.CheckConstraint(
            "unlocked_count IS NULL OR total_count IS NULL "
            "OR unlocked_count <= total_count",
            name="ck_profile_game_achievements_unlocked_within_total",
        ),
        sa.CheckConstraint(
            "playtime_minutes_at_fetch >= 0",
            name="ck_profile_game_achievements_playtime_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["profile_id", "steam_app_id"],
            ["profile_games.profile_id", "profile_games.steam_app_id"],
            ondelete="CASCADE",
            name="fk_profile_game_achievements_profile_game",
        ),
        sa.PrimaryKeyConstraint("profile_id", "steam_app_id"),
    )
    with op.batch_alter_table("steam_usage_events") as batch_op:
        batch_op.drop_constraint("ck_steam_usage_events_category", type_="check")
        batch_op.create_check_constraint(
            "ck_steam_usage_events_category",
            _NEW_CATEGORIES,
        )


def downgrade() -> None:
    """Remove achievement counts and their budget events."""
    op.execute(
        "DELETE FROM steam_usage_events WHERE category = 'achievement_call'"
    )
    with op.batch_alter_table("steam_usage_events") as batch_op:
        batch_op.drop_constraint("ck_steam_usage_events_category", type_="check")
        batch_op.create_check_constraint(
            "ck_steam_usage_events_category",
            _OLD_CATEGORIES,
        )
    op.drop_table("profile_game_achievements")
