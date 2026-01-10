"""task-989: Rename platform_id to platform_community_server_id

Standardizes naming convention for platform-specific identifiers in the
community_servers table. This rename clarifies that the field contains the
platform-specific community server ID (e.g., Discord guild ID, subreddit name)
rather than a generic platform identifier.

Migration steps:
1. Drop the old single-column auto-index (from index=True)
2. Drop the old unique composite index
3. Rename the column platform_id -> platform_community_server_id
4. Create the new single-column auto-index
5. Create the new unique composite index with updated column name

Revision ID: task989a1b2c3d
Revises: 8669929ca521
Create Date: 2026-01-09 22:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "task989a1b2c3d"
down_revision: str | Sequence[str] | None = "8669929ca521"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Step 1: Drop the old single-column auto-index (from index=True on column)
    op.drop_index(
        "ix_community_servers_platform_id",
        table_name="community_servers",
    )

    # Step 2: Drop the old unique composite index
    op.drop_index(
        "idx_community_servers_platform_id",
        table_name="community_servers",
    )

    # Step 3: Rename the column
    op.alter_column(
        "community_servers",
        "platform_id",
        new_column_name="platform_community_server_id",
    )

    # Step 4: Create new single-column auto-index
    op.create_index(
        "ix_community_servers_platform_community_server_id",
        "community_servers",
        ["platform_community_server_id"],
        unique=False,
    )

    # Step 5: Create new unique composite index with updated column name
    op.create_index(
        "idx_community_servers_platform_community_server_id",
        "community_servers",
        ["platform", "platform_community_server_id"],
        unique=True,
    )


def downgrade() -> None:
    # Drop new unique composite index
    op.drop_index(
        "idx_community_servers_platform_community_server_id",
        table_name="community_servers",
    )

    # Drop new single-column auto-index
    op.drop_index(
        "ix_community_servers_platform_community_server_id",
        table_name="community_servers",
    )

    # Rename column back
    op.alter_column(
        "community_servers",
        "platform_community_server_id",
        new_column_name="platform_id",
    )

    # Recreate old single-column auto-index
    op.create_index(
        "ix_community_servers_platform_id",
        "community_servers",
        ["platform_id"],
        unique=False,
    )

    # Recreate old unique composite index
    op.create_index(
        "idx_community_servers_platform_id",
        "community_servers",
        ["platform", "platform_id"],
        unique=True,
    )
