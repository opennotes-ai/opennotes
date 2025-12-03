"""add_updated_at_columns_to_tables

Revision ID: d3c8210eaa94
Revises: 59d60811c9a4
Create Date: 2025-10-29 18:41:05.978051

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d3c8210eaa94"
down_revision: str | Sequence[str] | None = "59d60811c9a4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add updated_at columns to tables that are missing them."""
    # Add updated_at to notes table
    op.add_column("notes", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
    # Set initial value to created_at
    op.execute("UPDATE notes SET updated_at = created_at WHERE updated_at IS NULL")

    # Add updated_at to ratings table
    op.add_column("ratings", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE ratings SET updated_at = created_at WHERE updated_at IS NULL")

    # requests table already has updated_at from a previous migration


def downgrade() -> None:
    """Remove updated_at columns."""
    op.drop_column("notes", "updated_at")
    op.drop_column("ratings", "updated_at")
    # Don't drop from requests - it was added by a different migration
