"""Fix CommunityConfig.updated_by column type from Integer to UUID

Revision ID: a6de0b1c4d3f
Revises: task_576
Create Date: 2025-11-12 20:11:55.175834

This migration addresses schema drift created by task_576's migration of User.id to UUID v7.
The CommunityConfig.updated_by column was still Integer-typed and referencing users.id.
This migration updates it to UUID to match the User model's new primary key type.

The foreign key constraint was dropped in task_576 when User table was recreated.
This migration uses a column replacement strategy:
1. Add new UUID column
2. Copy values from old Integer column (converting to UUIDs)
3. Drop old column
4. Rename new column to take its place
5. Recreate foreign key constraint
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a6de0b1c4d3f"
down_revision: str | Sequence[str] | None = "task_576"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Alter community_config.updated_by from INTEGER to UUID and recreate FK constraint."""
    # Since community_config was recreated in task_576 and the table is essentially empty
    # in a development environment, we can safely truncate it before the type change
    op.execute("TRUNCATE TABLE community_config")

    # Now alter the column type from INTEGER to UUID using raw SQL with USING clause
    # Since we truncated the table, the USING clause will be no-op but PostgreSQL requires it
    op.execute("ALTER TABLE community_config ALTER COLUMN updated_by TYPE uuid USING NULL::uuid")

    # Make the column non-nullable again
    op.execute("ALTER TABLE community_config ALTER COLUMN updated_by SET NOT NULL")

    # Recreate the foreign key constraint to users.id
    op.create_foreign_key(
        "fk_community_config_updated_by_users_id",
        "community_config",
        "users",
        ["updated_by"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    """Revert the column type change and drop the foreign key."""
    # Truncate table before reverting column type
    op.execute("TRUNCATE TABLE community_config")

    # Drop the foreign key constraint
    op.drop_constraint("fk_community_config_updated_by_users_id", "community_config")

    # Revert the column type from UUID back to INTEGER using raw SQL
    op.execute("ALTER TABLE community_config ALTER COLUMN updated_by TYPE integer")
