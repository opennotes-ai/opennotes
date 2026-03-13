"""resolve stuck scans 2026-03-13

Mark two production scans stuck due to DBOS queue stall and zero-message gap:
- 019ce8ca-33e4-7240-9c37-5adbea1e123b: PENDING with 0 messages (zero-message gap)
- 019ce8fc-f10a-7c50-88f2-4f41965aee86: IN_PROGRESS with 1 message (DBOS stall)

Revision ID: c2bb19d8c78c
Revises: 82909ed55243
Create Date: 2026-03-13 14:33:44.022764

"""

from collections.abc import Sequence

from alembic import op

revision: str = "c2bb19d8c78c"
down_revision: str | Sequence[str] | None = "82909ed55243"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        UPDATE bulk_content_scan_logs
        SET status = 'completed',
            completed_at = initiated_at,
            messages_scanned = 0,
            messages_flagged = 0,
            updated_at = NOW()
        WHERE id = '019ce8ca-33e4-7240-9c37-5adbea1e123b'
          AND status = 'pending'
    """)

    op.execute("""
        UPDATE bulk_content_scan_logs
        SET status = 'failed',
            completed_at = NOW(),
            updated_at = NOW()
        WHERE id = '019ce8fc-f10a-7c50-88f2-4f41965aee86'
          AND status = 'in_progress'
    """)


def downgrade() -> None:
    op.execute("""
        UPDATE bulk_content_scan_logs
        SET status = 'pending',
            completed_at = NULL,
            messages_scanned = NULL,
            messages_flagged = NULL,
            updated_at = NOW()
        WHERE id = '019ce8ca-33e4-7240-9c37-5adbea1e123b'
          AND status = 'completed'
    """)

    op.execute("""
        UPDATE bulk_content_scan_logs
        SET status = 'in_progress',
            completed_at = NULL,
            updated_at = NOW()
        WHERE id = '019ce8fc-f10a-7c50-88f2-4f41965aee86'
          AND status = 'failed'
    """)
