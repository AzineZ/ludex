"""add cached IGDB ratings to games

Revision ID: b4c7e2d91f35
Revises: 8e1a4c9d7b20
Create Date: 2026-10-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b4c7e2d91f35"
down_revision: Union[str, Sequence[str], None] = "8e1a4c9d7b20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CHECK_CONSTRAINTS = (
    (
        "ck_games_igdb_total_rating_range",
        "igdb_total_rating IS NULL "
        "OR (igdb_total_rating >= 0 AND igdb_total_rating <= 100)",
    ),
    (
        "ck_games_igdb_aggregated_rating_range",
        "igdb_aggregated_rating IS NULL "
        "OR (igdb_aggregated_rating >= 0 AND igdb_aggregated_rating <= 100)",
    ),
    (
        "ck_games_igdb_total_rating_count_nonnegative",
        "igdb_total_rating_count IS NULL OR igdb_total_rating_count >= 0",
    ),
    (
        "ck_games_igdb_aggregated_rating_count_nonnegative",
        "igdb_aggregated_rating_count IS NULL "
        "OR igdb_aggregated_rating_count >= 0",
    ),
)


def upgrade() -> None:
    """Add nullable display-only IGDB ratings and their fetch time."""
    with op.batch_alter_table("games") as batch_op:
        batch_op.add_column(
            sa.Column("igdb_total_rating", sa.Float(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("igdb_total_rating_count", sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("igdb_aggregated_rating", sa.Float(), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "igdb_aggregated_rating_count",
                sa.Integer(),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "igdb_ratings_checked_at",
                sa.DateTime(timezone=True),
                nullable=True,
            )
        )
        for name, condition in _CHECK_CONSTRAINTS:
            batch_op.create_check_constraint(name, condition)


def downgrade() -> None:
    """Remove only the cached ratings."""
    with op.batch_alter_table("games") as batch_op:
        for name, _ in reversed(_CHECK_CONSTRAINTS):
            batch_op.drop_constraint(name, type_="check")
        batch_op.drop_column("igdb_ratings_checked_at")
        batch_op.drop_column("igdb_aggregated_rating_count")
        batch_op.drop_column("igdb_aggregated_rating")
        batch_op.drop_column("igdb_total_rating_count")
        batch_op.drop_column("igdb_total_rating")
