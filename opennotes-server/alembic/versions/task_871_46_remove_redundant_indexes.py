"""task-871.46: Remove redundant indexes from previously_seen_messages

Remove indexes that were marked as redundant in the code review:
- ix_previously_seen_messages_id: Primary key already has implicit index
- ix_previously_seen_messages_community_server_id: Covered by composite index
- ix_previously_seen_messages_original_message_id: Covered by composite index
- ix_previously_seen_messages_published_note_id: Foreign key with unique constraint

Revision ID: 87146a1b2c3d
Revises: 87118a1b2c3d
Create Date: 2025-12-26 22:30:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "87146a1b2c3d"
down_revision: str | Sequence[str] | None = "87118a1b2c3d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop redundant indexes from previously_seen_messages table."""
    op.drop_index("ix_previously_seen_messages_id", table_name="previously_seen_messages")
    op.drop_index(
        "ix_previously_seen_messages_community_server_id", table_name="previously_seen_messages"
    )
    op.drop_index(
        "ix_previously_seen_messages_original_message_id", table_name="previously_seen_messages"
    )
    op.drop_index(
        "ix_previously_seen_messages_published_note_id", table_name="previously_seen_messages"
    )


def downgrade() -> None:
    """Recreate the redundant indexes if needed."""
    op.create_index(
        "ix_previously_seen_messages_published_note_id",
        "previously_seen_messages",
        ["published_note_id"],
        unique=False,
    )
    op.create_index(
        "ix_previously_seen_messages_original_message_id",
        "previously_seen_messages",
        ["original_message_id"],
        unique=False,
    )
    op.create_index(
        "ix_previously_seen_messages_community_server_id",
        "previously_seen_messages",
        ["community_server_id"],
        unique=False,
    )
    op.create_index(
        "ix_previously_seen_messages_id",
        "previously_seen_messages",
        ["id"],
        unique=False,
    )
