"""task-555: enforce NOT NULL on community_server_id for notes and requests

Revision ID: 7791f3eca498
Revises: 60659bf5f7fa
Create Date: 2025-11-11 13:35:58.804405

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7791f3eca498"
down_revision: str | Sequence[str] | None = "60659bf5f7fa"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Step 1: Fix orphaned notes by copying community_server_id from their linked request
    # This handles notes where community_server_id is NULL but request_id is not NULL
    op.execute("""
        UPDATE notes
        SET community_server_id = requests.community_server_id
        FROM requests
        WHERE notes.request_id = requests.request_id
          AND notes.community_server_id IS NULL
          AND requests.community_server_id IS NOT NULL
    """)

    # Step 2: Check for notes with NULL community_server_id that couldn't be fixed
    # This would indicate a data integrity issue that needs manual intervention
    conn = op.get_bind()
    result = conn.execute(
        sa.text("""
        SELECT COUNT(*) as count
        FROM notes
        WHERE community_server_id IS NULL
    """)
    )
    orphaned_count = result.scalar()

    if orphaned_count > 0:
        raise Exception(
            f"Cannot proceed: {orphaned_count} notes still have NULL community_server_id after attempting to copy from requests. "
            "Manual intervention required to fix data integrity issues."
        )

    # Step 3: Check for requests with NULL community_server_id
    result = conn.execute(
        sa.text("""
        SELECT COUNT(*) as count
        FROM requests
        WHERE community_server_id IS NULL
    """)
    )
    orphaned_requests_count = result.scalar()

    if orphaned_requests_count > 0:
        raise Exception(
            f"Cannot proceed: {orphaned_requests_count} requests have NULL community_server_id. "
            "Manual intervention required to fix data integrity issues."
        )

    # Step 4: Add NOT NULL constraints
    op.alter_column(
        "notes", "community_server_id", existing_type=sa.dialects.postgresql.UUID(), nullable=False
    )

    op.alter_column(
        "requests",
        "community_server_id",
        existing_type=sa.dialects.postgresql.UUID(),
        nullable=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Remove NOT NULL constraints
    op.alter_column(
        "requests",
        "community_server_id",
        existing_type=sa.dialects.postgresql.UUID(),
        nullable=True,
    )

    op.alter_column(
        "notes", "community_server_id", existing_type=sa.dialects.postgresql.UUID(), nullable=True
    )
