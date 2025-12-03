"""task-593.21: drop btree index on embedding column to fix btree size limit error

Revision ID: f9fec89fa9be
Revises: 47b2c9e7dc9b
Create Date: 2025-11-17 15:26:53.200305

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f9fec89fa9be"
down_revision: str | Sequence[str] | None = "47b2c9e7dc9b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema.

    Drop the problematic composite btree index idx_previously_seen_messages_server_embedding
    which exceeds PostgreSQL's btree index size limit (6176 bytes > 2704 byte limit).

    The index is not needed for queries because:
    1. Vector similarity queries use the ivfflat index on the embedding column
    2. Filtering by community_server_id uses the separate btree index on community_server_id
    3. The composite index cannot be used by pgvector's <=> operator anyway

    Relevant error:
    asyncpg.exceptions.ProgramLimitExceededError: index row size 6176 exceeds btree
    version 4 maximum 2704 for index "idx_previously_seen_messages_server_embedding"
    """
    op.drop_index(
        "idx_previously_seen_messages_server_embedding",
        table_name="previously_seen_messages",
        if_exists=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.create_index(
        "idx_previously_seen_messages_server_embedding",
        "previously_seen_messages",
        ["community_server_id", "embedding"],
        unique=False,
    )
