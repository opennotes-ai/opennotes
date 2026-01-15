"""task-1002: add btree index on fact_check_items.created_at

Revision ID: 5584986dda58
Revises: 8fe3e5d9be26
Create Date: 2026-01-15

Adds a B-tree index on the fact_check_items.created_at column as
recommended by Supabase index advisor to improve query performance.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "5584986dda58"
down_revision: str | Sequence[str] | None = "8fe3e5d9be26"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add btree index on fact_check_items.created_at column."""
    op.create_index(
        "idx_fact_check_items_created_at",
        "fact_check_items",
        ["created_at"],
        unique=False,
        postgresql_using="btree",
    )


def downgrade() -> None:
    """Remove btree index on fact_check_items.created_at column."""
    op.drop_index("idx_fact_check_items_created_at", table_name="fact_check_items")
