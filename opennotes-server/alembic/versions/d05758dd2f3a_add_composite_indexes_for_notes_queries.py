"""add_composite_indexes_for_notes_queries

Revision ID: d05758dd2f3a
Revises: bb1298120943
Create Date: 2025-10-31 15:19:37.813688

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d05758dd2f3a"
down_revision: str | Sequence[str] | None = "bb1298120943"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add composite indexes for common note query patterns."""
    # Composite index for filtering by tweet_id + status
    op.create_index("ix_notes_tweet_status", "notes", ["tweet_id", "status"], unique=False)

    # Composite index for filtering by classification + status
    op.create_index(
        "ix_notes_classification_status", "notes", ["classification", "status"], unique=False
    )

    # Composite index for ordering by created_at with status filter
    op.create_index("ix_notes_created_status", "notes", ["created_at", "status"], unique=False)


def downgrade() -> None:
    """Remove composite indexes."""
    op.drop_index("ix_notes_created_status", table_name="notes")
    op.drop_index("ix_notes_classification_status", table_name="notes")
    op.drop_index("ix_notes_tweet_status", table_name="notes")
