"""add_channel_id_to_notes

Revision ID: bb8ab8967add
Revises: 2b136e8f32cf
Create Date: 2025-10-29 15:22:55.618573

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "bb8ab8967add"
down_revision: str | Sequence[str] | None = "2b136e8f32cf"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add channel_id column to notes table for faster message lookups."""
    op.add_column("notes", sa.Column("channel_id", sa.String(length=255), nullable=True))
    op.create_index("idx_notes_channel_id", "notes", ["channel_id"], unique=False)


def downgrade() -> None:
    """Remove channel_id column from notes table."""
    op.drop_index("idx_notes_channel_id", table_name="notes")
    op.drop_column("notes", "channel_id")
