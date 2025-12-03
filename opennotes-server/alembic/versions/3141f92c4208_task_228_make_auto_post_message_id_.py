"""task_228_make_auto_post_message_id_nullable

Revision ID: 3141f92c4208
Revises: task229001
Create Date: 2025-11-01 13:25:09.144391

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3141f92c4208"
down_revision: str | Sequence[str] | None = "task229001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Make auto_post_message_id nullable and convert empty strings to NULL.

    This fixes task-228 where failed posts incorrectly stored empty strings
    instead of NULL for auto_post_message_id.
    """
    # First, update existing empty strings to NULL
    op.execute("UPDATE auto_posts SET auto_post_message_id = NULL WHERE auto_post_message_id = ''")

    # Then alter the column to be nullable
    op.alter_column(
        "auto_posts", "auto_post_message_id", existing_type=sa.String(length=64), nullable=True
    )


def downgrade() -> None:
    """Revert auto_post_message_id to NOT NULL (converts NULL to empty strings)."""
    # Convert NULL values to empty strings before making column NOT NULL
    op.execute("UPDATE auto_posts SET auto_post_message_id = '' WHERE auto_post_message_id IS NULL")

    # Alter the column back to NOT NULL
    op.alter_column(
        "auto_posts", "auto_post_message_id", existing_type=sa.String(length=64), nullable=False
    )
