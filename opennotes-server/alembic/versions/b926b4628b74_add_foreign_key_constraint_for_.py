"""add_foreign_key_constraint_for_community_config_community_server_id

Add foreign key constraint from community_config.community_server_id to
community_servers.id. This ensures referential integrity and prevents orphaned
configuration records.

The community_config table originally used String(64) for community_server_id,
but the community_servers table uses UUID primary keys. This migration:

1. Adds a new UUID column (community_server_id_new)
2. Performs data migration from string to UUID by joining with community_servers
3. Removes the old string column
4. Renames the new UUID column to community_server_id
5. Adds the foreign key constraint with ON DELETE CASCADE
6. Recreates all indexes and constraints

Revision ID: b926b4628b74
Revises: 0a912528f6a9
Create Date: 2025-10-30 13:34:14.253546

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b926b4628b74"
down_revision: str | Sequence[str] | None = "0a912528f6a9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add foreign key constraint for community_config.community_server_id."""

    # Step 1: Drop the unique composite index to allow column modifications
    op.execute("DROP INDEX IF EXISTS ix_community_config_community_server_id_key")

    # Step 2: Add new UUID column
    op.add_column(
        "community_config",
        sa.Column("community_server_id_new", postgresql.UUID(as_uuid=True), nullable=True),
    )

    # Step 3: Migrate data from string to UUID
    # Join with community_servers table to get the UUID for each community_server_id
    op.execute("""
        UPDATE community_config cc
        SET community_server_id_new = cs.id
        FROM community_servers cs
        WHERE cc.community_server_id = cs.platform_id
           OR cc.community_server_id = cs.id::text
    """)

    # Step 4: Drop old string column and rename new column
    op.drop_column("community_config", "community_server_id")
    op.alter_column(
        "community_config",
        "community_server_id_new",
        new_column_name="community_server_id",
        nullable=False,
    )

    # Step 5: Recreate indexes
    op.create_index(
        "ix_community_config_community_server_id",
        "community_config",
        ["community_server_id"],
        unique=False,
    )

    op.create_index(
        "ix_community_config_community_server_id_key",
        "community_config",
        ["community_server_id", "config_key"],
        unique=True,
    )

    # Step 6: Add foreign key constraint with ON DELETE CASCADE
    op.create_foreign_key(
        "fk_community_config_community_server_id",
        "community_config",
        "community_servers",
        ["community_server_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    """Remove foreign key constraint and revert to string column."""

    # Step 1: Drop foreign key constraint
    op.drop_constraint(
        "fk_community_config_community_server_id", "community_config", type_="foreignkey"
    )

    # Step 2: Drop indexes
    op.execute("DROP INDEX IF EXISTS ix_community_config_community_server_id_key")
    op.execute("DROP INDEX IF EXISTS ix_community_config_community_server_id")

    # Step 3: Add back string column
    op.add_column(
        "community_config", sa.Column("community_server_id_old", sa.String(64), nullable=True)
    )

    # Step 4: Migrate data back to string
    # Use platform_id for the round-trip back to string identifier
    op.execute("""
        UPDATE community_config cc
        SET community_server_id_old = cs.platform_id
        FROM community_servers cs
        WHERE cc.community_server_id = cs.id
    """)

    # Step 5: Drop UUID column and rename string column back
    op.drop_column("community_config", "community_server_id")
    op.alter_column(
        "community_config",
        "community_server_id_old",
        new_column_name="community_server_id",
        nullable=False,
    )

    # Step 6: Recreate original indexes
    op.create_index(
        "ix_community_config_community_id",
        "community_config",
        ["community_server_id"],
        unique=False,
    )

    op.create_index(
        "ix_community_config_community_id_key",
        "community_config",
        ["community_server_id", "config_key"],
        unique=True,
    )
