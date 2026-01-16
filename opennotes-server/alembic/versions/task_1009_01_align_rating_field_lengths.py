"""task-1009: align rating field lengths

Revision ID: task_1009_rating_len
Revises: c91286f2c37a
Create Date: 2026-01-15 18:00:00.000000

FactCheckedItemCandidate.rating was String(100) while FactCheckItem.rating was
String(50). Since candidates get promoted to FactCheckItem, we need consistent
field lengths. Increasing FactCheckItem.rating to String(100) is the safer option
as it avoids any potential data truncation.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "task_1009_rating_len"
down_revision: str | Sequence[str] | None = "c91286f2c37a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Increase fact_check_items.rating from String(50) to String(100)."""
    op.alter_column(
        "fact_check_items",
        "rating",
        existing_type=sa.String(50),
        type_=sa.String(100),
        existing_nullable=True,
    )


def downgrade() -> None:
    """Revert fact_check_items.rating from String(100) back to String(50).

    Note: This downgrade may fail if any rating values exceed 50 characters.
    """
    op.alter_column(
        "fact_check_items",
        "rating",
        existing_type=sa.String(100),
        type_=sa.String(50),
        existing_nullable=True,
    )
