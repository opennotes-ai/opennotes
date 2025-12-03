"""task-678: Convert tweet_id from BigInteger to String for platform compatibility

Revision ID: task_678_tweet_id_str
Revises: 78e946dc6f26
Create Date: 2025-11-27 00:00:00.000000

The tweet_id column is currently BigInteger which works for Twitter/X but may not
support IDs from all platforms. Converting to String(255) provides maximum
compatibility across different platforms (Discord, Reddit, etc.) that may use
non-numeric or larger IDs.

This migration safely converts existing integer values to their string representation.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "task_678_tweet_id_str"
down_revision: str | Sequence[str] | None = "78e946dc6f26"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Convert tweet_id from BigInteger to String(255)."""
    # PostgreSQL allows ALTER COLUMN TYPE with USING clause for data conversion
    # This safely converts existing integer values to their string representation
    op.alter_column(
        "notes",
        "tweet_id",
        existing_type=sa.BigInteger(),
        type_=sa.String(255),
        existing_nullable=False,
        postgresql_using="tweet_id::varchar",
    )


def downgrade() -> None:
    """Revert tweet_id from String(255) back to BigInteger."""
    # Note: This assumes all values are valid integers
    # If non-numeric strings exist, this downgrade will fail
    op.alter_column(
        "notes",
        "tweet_id",
        existing_type=sa.String(255),
        type_=sa.BigInteger(),
        existing_nullable=False,
        postgresql_using="tweet_id::bigint",
    )
