"""Convert Interaction model from Integer ID to UUID v7 primary key

Revision ID: task_490_phase_1a
Revises: task_poi_001
Create Date: 2025-11-07 18:00:00.000000

Phase 1a: Low-risk infrastructure migration
Interaction table has no incoming foreign keys and is safe for independent migration.

The migration performs the following steps:
1. Create a new UUID v7 column with native uuidv7() server default
2. Populate UUID values for existing records
3. Drop the old Integer ID column and primary key
4. Rename the UUID column to 'id'
5. Set the new column as the primary key
6. Recreate any dependent indexes

This migration is reversible (see downgrade() for rollback procedure).

Note: Uses native PostgreSQL 18+ uuidv7() function (no extension required).

Migration Rollback Procedure:
1. Re-add Integer column with sequential IDs
2. Copy UUIDs to temporary mapping table (optional)
3. Drop UUID primary key
4. Drop UUID column
5. Make Integer column primary key again

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "task_490_phase_1a"
down_revision: str | Sequence[str] | None = "task_poi_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Convert interactions table from Integer ID to UUID v7."""

    # Step 1: Create new UUID column with uuidv7() server default
    op.add_column(
        "interactions",
        sa.Column(
            "id_new",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuidv7()"),
            nullable=False,
        ),
    )

    # Step 2: Populate new UUID column for existing records
    # For existing rows that don't have a generated UUID yet, explicitly assign one
    op.execute("""
        UPDATE interactions
        SET id_new = uuidv7()
        WHERE id_new IS NULL
    """)

    # Step 3: Drop the old Integer ID primary key
    op.drop_constraint("interactions_pkey", "interactions", type_="primary")

    # Step 4: Drop the old Integer ID column
    op.drop_column("interactions", "id")

    # Step 5: Rename the new UUID column to 'id'
    op.alter_column(
        "interactions",
        column_name="id_new",
        new_column_name="id",
        existing_type=postgresql.UUID(as_uuid=True),
        existing_nullable=False,
        existing_server_default=sa.text("uuidv7()"),
    )

    # Step 6: Set the new 'id' column as primary key
    op.create_primary_key("interactions_pkey", "interactions", ["id"])

    # Step 7: Recreate the index on the id column if it existed
    # Note: Primary key automatically creates index, but we ensure it exists
    op.create_index("ix_interactions_id", "interactions", ["id"])


def downgrade() -> None:
    """Revert interactions table from UUID v7 to Integer ID."""

    # Step 1: Drop the primary key constraint
    op.drop_constraint("interactions_pkey", "interactions", type_="primary")

    # Step 2: Drop the explicit index if it exists
    op.drop_index("ix_interactions_id", table_name="interactions")

    # Step 3: Create new Integer column to hold the old IDs (nullable first)
    # Note: We generate new sequential IDs for the downgrade since we don't
    # have a mapping of original integer IDs to the new UUIDs
    op.add_column(
        "interactions", sa.Column("id_old", sa.Integer(), nullable=True, autoincrement=True)
    )

    # Step 4: Generate sequential integers using ROW_NUMBER
    op.execute("""
        WITH numbered_interactions AS (
            SELECT id, ROW_NUMBER() OVER (ORDER BY id) as new_id
            FROM interactions
        )
        UPDATE interactions i
        SET id_old = ni.new_id
        FROM numbered_interactions ni
        WHERE i.id = ni.id
    """)

    # Step 4b: Make the column NOT NULL after backfill
    op.alter_column("interactions", "id_old", nullable=False)

    # Step 5: Drop the UUID column
    op.drop_column("interactions", "id")

    # Step 6: Rename the old Integer column back to 'id'
    op.alter_column(
        "interactions",
        column_name="id_old",
        new_column_name="id",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    # Step 7: Set the id column as primary key again
    op.create_primary_key("interactions_pkey", "interactions", ["id"])

    # Step 8: Recreate the index
    op.create_index("ix_interactions_id", "interactions", ["id"])
