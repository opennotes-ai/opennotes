"""Fix pre-existing schema drift

Aligns database with models for fact_checked_item_candidates:
- Increase rating column from VARCHAR(50) to VARCHAR(100)
- Add missing index on id column

Revision ID: cc3775845560
Revises: c5d6fa98fac1
Create Date: 2026-01-09 02:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "cc3775845560"
down_revision: str | Sequence[str] | None = "c5d6fa98fac1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Increase rating column length from 50 to 100
    op.alter_column(
        "fact_checked_item_candidates",
        "rating",
        type_=sa.String(100),
        existing_type=sa.String(50),
        existing_nullable=True,
    )

    # Add index on id column (model has index=True on id)
    # Use IF NOT EXISTS to handle cases where index already exists
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_fact_checked_item_candidates_id "
            "ON fact_checked_item_candidates (id)"
        )
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_fact_checked_item_candidates_id"))
    op.alter_column(
        "fact_checked_item_candidates",
        "rating",
        type_=sa.String(50),
        existing_type=sa.String(100),
        existing_nullable=True,
    )
