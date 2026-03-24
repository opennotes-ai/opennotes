"""repoint_copied_requests_to_original_archives

Data-only migration: re-point copied requests to share the original
message archives instead of their stripped duplicates, then delete
orphaned archive rows.

Revision ID: 1dceabf5c87e
Revises: 63983efd8f6c
Create Date: 2026-03-23 11:57:41.960482

"""

from collections.abc import Sequence

from alembic import op

revision: str = "1dceabf5c87e"
down_revision: str | Sequence[str] | None = "63983efd8f6c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TEMP TABLE _orphaned_archives AS
        SELECT DISTINCT copied.message_archive_id AS id
        FROM requests AS copied
        JOIN requests AS source
          ON copied.request_metadata->>'copied_from' = source.id::text
        WHERE copied.message_archive_id IS NOT NULL
          AND copied.message_archive_id IS DISTINCT FROM source.message_archive_id
    """)

    op.execute("""
        UPDATE requests AS copied
        SET message_archive_id = source.message_archive_id
        FROM requests AS source
        WHERE copied.request_metadata->>'copied_from' = source.id::text
          AND copied.message_archive_id IS DISTINCT FROM source.message_archive_id
    """)

    op.execute("""
        DELETE FROM message_archive
        WHERE id IN (
            SELECT oa.id FROM _orphaned_archives oa
            LEFT JOIN requests r ON r.message_archive_id = oa.id
            WHERE r.id IS NULL
        )
    """)

    op.execute("DROP TABLE IF EXISTS _orphaned_archives")


def downgrade() -> None:
    pass
