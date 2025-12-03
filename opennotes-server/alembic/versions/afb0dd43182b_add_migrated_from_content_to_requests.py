"""add_migrated_from_content_to_requests

Revision ID: afb0dd43182b
Revises: 0f34e2cd94ca
Create Date: 2025-10-29 12:11:16.059212

Adds migrated_from_content boolean column to requests table to track whether
the request was migrated from legacy original_message_content field.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "afb0dd43182b"
down_revision: str | Sequence[str] | None = "0f34e2cd94ca"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add migrated_from_content column to requests table."""
    op.add_column(
        "requests",
        sa.Column("migrated_from_content", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    """Remove migrated_from_content column from requests table."""
    op.drop_column("requests", "migrated_from_content")
