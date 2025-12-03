"""Make updated_by NOT NULL and add foreign key constraint to users

Revision ID: task180001
Revises: ac96bb16ac63
Create Date: 2025-11-01 12:00:00.000000

This migration addresses the data integrity issue where the updated_by field
in community_config allowed NULL values with no foreign key constraint.

The migration:
1. Backfills existing NULL values with user_id 1 (system user)
2. Adds a foreign key constraint to the users table
3. Makes the column NOT NULL to enforce referential integrity
"""

import sqlalchemy as sa

from alembic import op

revision = "task180001"
down_revision = "ac96bb16ac63"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Step 1: Add temporary column as STRING to handle the type change safely
    op.add_column("community_config", sa.Column("updated_by_new", sa.Integer(), nullable=True))

    # Step 2: Migrate existing data
    # First check if any NULL values exist, and backfill with user_id 1
    op.execute("""
        UPDATE community_config
        SET updated_by_new = CASE
            WHEN updated_by IS NOT NULL THEN CAST(updated_by AS INTEGER)
            ELSE 1
        END
    """)

    # Step 3: Drop the old column
    op.drop_column("community_config", "updated_by")

    # Step 4: Rename the new column to the original name
    op.alter_column(
        "community_config",
        column_name="updated_by_new",
        new_column_name="updated_by",
        existing_type=sa.Integer(),
        nullable=False,
    )

    # Step 5: Add the foreign key constraint
    op.create_foreign_key(
        "fk_community_config_updated_by_users_id",
        "community_config",
        "users",
        ["updated_by"],
        ["id"],
        ondelete="RESTRICT",
    )

    # Step 6: Create index on the updated_by column for query performance
    op.create_index("ix_community_config_updated_by", "community_config", ["updated_by"])


def downgrade() -> None:
    # Step 1: Drop the index
    op.drop_index("ix_community_config_updated_by", table_name="community_config")

    # Step 2: Drop the foreign key constraint
    op.drop_constraint(
        "fk_community_config_updated_by_users_id", "community_config", type_="foreignkey"
    )

    # Step 3: Add temporary column as STRING (original type)
    op.add_column("community_config", sa.Column("updated_by_old", sa.String(64), nullable=True))

    # Step 4: Migrate data back to STRING format
    op.execute("""
        UPDATE community_config
        SET updated_by_old = CAST(updated_by AS VARCHAR(64))
    """)

    # Step 5: Drop the INTEGER column
    op.drop_column("community_config", "updated_by")

    # Step 6: Rename back to original name
    op.alter_column(
        "community_config",
        column_name="updated_by_old",
        new_column_name="updated_by",
        existing_type=sa.String(64),
        nullable=True,
    )
