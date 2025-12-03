"""add_timestamps_to_requests_table

Revision ID: 0bbaec94d025
Revises: bb8ab8967add
Create Date: 2025-10-29 16:44:32.749579

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0bbaec94d025"
down_revision: str | Sequence[str] | None = "bb8ab8967add"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add created_at and updated_at timestamp columns to requests table."""
    # Add created_at column with default value for existing rows
    op.add_column(
        "requests",
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=False),
    )

    # Add updated_at column with default value for existing rows
    op.add_column(
        "requests",
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True),
    )


def downgrade() -> None:
    """Remove created_at and updated_at timestamp columns from requests table."""
    op.drop_column("requests", "updated_at")
    op.drop_column("requests", "created_at")
