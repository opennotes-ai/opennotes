"""Convert Webhook model from Integer ID to UUID v7 primary key

Revision ID: task_poi_001
Revises: task229001
Create Date: 2025-11-07 12:00:00.000000

This is a proof-of-concept migration demonstrating the UUID v7 pattern for the
Open Notes project. The Webhook table is used as the test case because:

1. It has no incoming foreign keys (low risk)
2. It's a relatively simple table with few dependencies
3. Audit shows it currently has minimal data in production

The migration performs the following steps:
1. Create a new UUID column with uuidv7() as the default
2. Generate UUIDs for any existing webhook records
3. Drop the old Integer ID column
4. Rename the UUID column to 'id'
5. Update any indexes on the ID column
6. Includes a full downgrade path for testing

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "task_poi_001"
down_revision: str | Sequence[str] | None = "e27213685b1c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Convert webhooks table from Integer ID to UUID v7."""

    # Step 1: Create new UUID column with uuidv7() server default
    op.add_column(
        "webhooks",
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
        UPDATE webhooks
        SET id_new = uuidv7()
        WHERE id_new IS NULL
    """)

    # Step 3: Drop the old Integer ID column
    op.drop_column("webhooks", "id")

    # Step 4: Rename the new UUID column to 'id'
    op.alter_column(
        "webhooks",
        column_name="id_new",
        new_column_name="id",
        existing_type=postgresql.UUID(as_uuid=True),
        existing_nullable=False,
        existing_server_default=sa.text("uuidv7()"),
    )

    # Step 5: Set the new 'id' column as primary key
    op.create_primary_key("pk_webhooks", "webhooks", ["id"])

    # Step 6: Recreate the index on the id column (was implicit with primary key)
    # The primary key constraint already provides indexing, but we can optionally
    # add an explicit index if needed for performance
    # op.create_index('ix_webhooks_id', 'webhooks', ['id'])


def downgrade() -> None:
    """Revert webhooks table from UUID v7 to Integer ID."""

    # Step 1: Drop the primary key constraint
    op.drop_constraint("pk_webhooks", "webhooks", type_="primary")

    # Step 2: Create new Integer column to hold the old IDs
    op.add_column("webhooks", sa.Column("id_old", sa.Integer(), nullable=False, autoincrement=True))

    # Step 3: For downgrade, we need to generate sequential integers
    # We'll use a ROW_NUMBER approach to assign sequential IDs
    op.execute("""
        WITH numbered_webhooks AS (
            SELECT id, ROW_NUMBER() OVER (ORDER BY id) as new_id
            FROM webhooks
        )
        UPDATE webhooks w
        SET id_old = nw.new_id
        FROM numbered_webhooks nw
        WHERE w.id = nw.id
    """)

    # Step 4: Drop the UUID column
    op.drop_column("webhooks", "id")

    # Step 5: Rename the old Integer column back to 'id'
    op.alter_column(
        "webhooks",
        column_name="id_old",
        new_column_name="id",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    # Step 6: Set the id column as primary key again
    op.create_primary_key("pk_webhooks", "webhooks", ["id"])

    # Step 7: Recreate any indexes
    op.create_index("ix_webhooks_id", "webhooks", ["id"])
