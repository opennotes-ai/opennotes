"""fix_erroneously_completed_requests

Revision ID: 99fd02d32ce2
Revises: task_678_tweet_id_str
Create Date: 2025-12-03 15:07:52.984963

This migration fixes requests that were incorrectly marked as COMPLETED.
The bug occurred when a note was rated (score >= 0.5) but the note was never
actually published. The correct behavior is that a request should only be
marked COMPLETED when the associated note has been successfully published.

Affected requests are identified as:
- Status = 'COMPLETED'
- Has an associated note (via notes.request_id)
- That note has NO successful publication record in note_publisher_posts

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "99fd02d32ce2"
down_revision: str | Sequence[str] | None = "task_678_tweet_id_str"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()

    find_affected_sql = sa.text("""
        SELECT r.request_id
        FROM requests r
        WHERE r.status = 'COMPLETED'
        AND EXISTS (
            SELECT 1 FROM notes n WHERE n.request_id = r.request_id
        )
        AND NOT EXISTS (
            SELECT 1
            FROM notes n
            JOIN note_publisher_posts npp ON npp.note_id = n.id
            WHERE n.request_id = r.request_id
            AND npp.success = true
        )
    """)

    affected_requests = conn.execute(find_affected_sql).fetchall()
    affected_ids = [row[0] for row in affected_requests]

    if affected_ids:
        print(f"[MIGRATION] Found {len(affected_ids)} requests erroneously marked as COMPLETED")
        print(f"[MIGRATION] Affected request IDs: {affected_ids}")

        update_sql = sa.text("""
            UPDATE requests
            SET status = 'IN_PROGRESS'
            WHERE request_id IN (
                SELECT r.request_id
                FROM requests r
                WHERE r.status = 'COMPLETED'
                AND EXISTS (
                    SELECT 1 FROM notes n WHERE n.request_id = r.request_id
                )
                AND NOT EXISTS (
                    SELECT 1
                    FROM notes n
                    JOIN note_publisher_posts npp ON npp.note_id = n.id
                    WHERE n.request_id = r.request_id
                    AND npp.success = true
                )
            )
        """)

        result = conn.execute(update_sql)
        print(f"[MIGRATION] Updated {result.rowcount} requests from COMPLETED to IN_PROGRESS")
    else:
        print("[MIGRATION] No erroneously completed requests found - nothing to fix")


def downgrade() -> None:
    print("[MIGRATION] Downgrade is a no-op for this data fix migration")
    print("[MIGRATION] Reason: We cannot reliably determine which requests were")
    print("[MIGRATION] incorrectly marked as COMPLETED vs legitimately completed")
