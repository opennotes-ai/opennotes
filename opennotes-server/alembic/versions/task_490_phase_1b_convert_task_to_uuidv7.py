"""Convert Task model from Integer ID to UUID v7 primary key

Revision ID: task_490_phase_1b
Revises: task_490_phase_1a
Create Date: 2025-11-07 18:15:00.000000

Phase 1b: Low-risk infrastructure migration
Task table has no incoming foreign keys and is safe for independent migration.

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
2. Drop UUID primary key
3. Drop UUID column
4. Make Integer column primary key again

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "task_490_phase_1b"
down_revision: str | Sequence[str] | None = "task_490_phase_1a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Convert tasks table from Integer ID to UUID v7."""

    # Step 1: Create new UUID column with uuidv7() server default
    op.add_column(
        "tasks",
        sa.Column(
            "id_new",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuidv7()"),
            nullable=False,
        ),
    )

    # Step 2: Populate new UUID column for existing records
    op.execute("""
        UPDATE tasks
        SET id_new = uuidv7()
        WHERE id_new IS NULL
    """)

    # Step 3: Drop the old Integer ID primary key
    op.drop_constraint("tasks_pkey", "tasks", type_="primary")

    # Step 4: Drop the old Integer ID column
    op.drop_column("tasks", "id")

    # Step 5: Rename the new UUID column to 'id'
    op.alter_column(
        "tasks",
        column_name="id_new",
        new_column_name="id",
        existing_type=postgresql.UUID(as_uuid=True),
        existing_nullable=False,
        existing_server_default=sa.text("uuidv7()"),
    )

    # Step 6: Set the new 'id' column as primary key
    op.create_primary_key("tasks_pkey", "tasks", ["id"])

    # Step 7: Recreate the index on the id column
    op.create_index("ix_tasks_id", "tasks", ["id"])


def downgrade() -> None:
    """Revert tasks table from UUID v7 to Integer ID."""

    # Step 1: Drop the primary key constraint
    op.drop_constraint("tasks_pkey", "tasks", type_="primary")

    # Step 2: Drop the explicit index if it exists
    op.drop_index("ix_tasks_id", table_name="tasks")

    # Step 3: Create new Integer column to hold the old IDs (nullable first)
    op.add_column("tasks", sa.Column("id_old", sa.Integer(), nullable=True, autoincrement=True))

    # Step 4: Generate sequential integers using ROW_NUMBER
    op.execute("""
        WITH numbered_tasks AS (
            SELECT id, ROW_NUMBER() OVER (ORDER BY id) as new_id
            FROM tasks
        )
        UPDATE tasks t
        SET id_old = nt.new_id
        FROM numbered_tasks nt
        WHERE t.id = nt.id
    """)

    # Step 4b: Make the column NOT NULL after backfill
    op.alter_column("tasks", "id_old", nullable=False)

    # Step 5: Drop the UUID column
    op.drop_column("tasks", "id")

    # Step 6: Rename the old Integer column back to 'id'
    op.alter_column(
        "tasks",
        column_name="id_old",
        new_column_name="id",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    # Step 7: Set the id column as primary key again
    op.create_primary_key("tasks_pkey", "tasks", ["id"])

    # Step 8: Recreate the index
    op.create_index("ix_tasks_id", "tasks", ["id"])
