"""Add foreign key constraint to notes.request_id

This migration adds a foreign key constraint from notes.request_id to requests.request_id.
The request_id column is nullable with ondelete="SET NULL" behavior.

This ensures referential integrity between notes and requests tables. When a request
is deleted, the corresponding note's request_id will be set to NULL instead of
leaving orphaned references.

Revision ID: 9369136951b7
Revises: aaf74ceb1dd5
Create Date: 2025-10-31 13:30:00.000000

"""

from collections.abc import Sequence

from sqlalchemy import text

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9369136951b7"
down_revision: str | Sequence[str] | None = "aaf74ceb1dd5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add foreign key constraint from notes.request_id to requests.request_id."""
    # Check if the constraint already exists to make this migration idempotent
    connection = op.get_bind()

    # Query to check if the constraint exists
    result = connection.execute(
        text("""
        SELECT constraint_name FROM information_schema.table_constraints
        WHERE table_name = 'notes' AND constraint_name = 'fk_notes_request_id'
    """)
    )

    constraint_exists = result.fetchone() is not None

    if not constraint_exists:
        op.create_foreign_key(
            "fk_notes_request_id",
            "notes",
            "requests",
            ["request_id"],
            ["request_id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    """Remove foreign key constraint from notes.request_id."""
    # Check if constraint exists before trying to drop it
    connection = op.get_bind()

    result = connection.execute(
        text("""
        SELECT constraint_name FROM information_schema.table_constraints
        WHERE table_name = 'notes' AND constraint_name = 'fk_notes_request_id'
    """)
    )

    constraint_exists = result.fetchone() is not None

    if constraint_exists:
        op.drop_constraint("fk_notes_request_id", "notes", type_="foreignkey")
