"""add durable Gemini provider circuit

Revision ID: 7c4f1e2a9b06
Revises: 3f2d8b7c1a90
Create Date: 2026-09-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7c4f1e2a9b06"
down_revision: Union[str, Sequence[str], None] = "3f2d8b7c1a90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add an identifier-free stop time to one prompt usage event."""
    with op.batch_alter_table("gemini_prompt_usage_events") as batch_op:
        batch_op.add_column(sa.Column(
            "provider_limited_until",
            sa.DateTime(timezone=True),
            nullable=True,
        ))
        batch_op.create_check_constraint(
            "ck_gemini_prompt_usage_events_provider_limit_order",
            "provider_limited_until IS NULL "
            "OR provider_limited_until >= created_at",
        )
        batch_op.create_index(
            "ix_gemini_prompt_usage_events_limited_until",
            ["provider_limited_until"],
            unique=False,
        )


def downgrade() -> None:
    """Remove only the provider-circuit marker."""
    with op.batch_alter_table("gemini_prompt_usage_events") as batch_op:
        batch_op.drop_index(
            "ix_gemini_prompt_usage_events_limited_until"
        )
        batch_op.drop_constraint(
            "ck_gemini_prompt_usage_events_provider_limit_order",
            type_="check",
        )
        batch_op.drop_column("provider_limited_until")
