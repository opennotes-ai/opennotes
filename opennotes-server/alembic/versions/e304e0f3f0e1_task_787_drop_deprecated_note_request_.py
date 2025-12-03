"""task_787_drop_deprecated_note_request_fields

Revision ID: e304e0f3f0e1
Revises: 53ef90ea75aa
Create Date: 2025-12-05 17:42:30.587606

This migration removes deprecated fields from the notes and requests tables.
These fields have been superseded by the MessageArchive table which now stores
the original message content and platform message IDs.

Dropped columns:
- notes.tweet_id (String(255)) - replaced by request.message_archive.platform_message_id
- notes.original_message_content (Text) - replaced by request.message_archive.get_content()
- requests.original_message_content (Text) - replaced by message_archive.get_content()

The downgrade adds columns back as NULLABLE for safe rollback, but data will not
be restored. The MessageArchive table contains the authoritative data.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e304e0f3f0e1"
down_revision: str | Sequence[str] | None = "53ef90ea75aa"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop deprecated columns from notes and requests tables."""
    op.drop_index("ix_notes_tweet_id", table_name="notes")

    op.drop_column("notes", "tweet_id")
    op.drop_column("notes", "original_message_content")

    op.drop_column("requests", "original_message_content")


def downgrade() -> None:
    """Re-add deprecated columns (nullable for safe rollback)."""
    op.add_column(
        "requests",
        sa.Column("original_message_content", sa.Text(), nullable=True),
    )

    op.add_column(
        "notes",
        sa.Column("original_message_content", sa.Text(), nullable=True),
    )
    op.add_column(
        "notes",
        sa.Column("tweet_id", sa.String(255), nullable=True),
    )

    op.create_index("ix_notes_tweet_id", "notes", ["tweet_id"], unique=False)
