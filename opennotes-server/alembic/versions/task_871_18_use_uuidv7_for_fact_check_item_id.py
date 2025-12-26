"""task-871.18: Use uuidv7() for FactCheckItem.id server_default

Aligns FactCheckItem.id with ADR-001 UUID v7 standardization.
Changes the server_default from gen_random_uuid() to uuidv7().

This only affects NEW records - existing data is not modified.

Revision ID: 87118a1b2c3d
Revises: 87101a1b2c3d
Create Date: 2025-12-26 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "87118a1b2c3d"
down_revision: str | Sequence[str] | None = "87101a1b2c3d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Change FactCheckItem.id server_default to uuidv7()."""
    op.alter_column(
        "fact_check_items",
        "id",
        server_default=sa.text("uuidv7()"),
    )


def downgrade() -> None:
    """Revert FactCheckItem.id server_default to gen_random_uuid()."""
    op.alter_column(
        "fact_check_items",
        "id",
        server_default=sa.text("gen_random_uuid()"),
    )
