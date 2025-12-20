"""fix_stuck_zero_message_scans

Fix existing bulk content scans that are stuck in pending/in_progress status
with 0 messages scanned. These represent scans that were initiated but never
received any messages to process (e.g., all messages were filtered out as
bot messages or empty content).

Revision ID: 41e171275262
Revises: a37eb031fffa
Create Date: 2025-12-19 14:39:41.500509

"""

from collections.abc import Sequence

from alembic import op

revision: str = "41e171275262"
down_revision: str | Sequence[str] | None = "a37eb031fffa"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Mark stuck 0-message scans as completed.

    Scans with messages_scanned = 0 and status in ('pending', 'in_progress')
    represent scans that were initiated but never received messages to process.
    These should be marked as completed with 0 flagged messages.

    Uses initiated_at for completed_at since we don't know exactly when the
    scan "finished" (it never truly started processing).
    """
    op.execute("""
        UPDATE bulk_content_scan_logs
        SET status = 'completed',
            completed_at = initiated_at,
            messages_flagged = 0,
            updated_at = NOW()
        WHERE messages_scanned = 0
          AND status IN ('pending', 'in_progress')
    """)


def downgrade() -> None:
    """Revert stuck scans back to in_progress status.

    Note: This cannot perfectly restore the original state since we don't know
    if the scan was originally 'pending' or 'in_progress'. We default to
    'in_progress' since that's the more common initial state after a scan
    is initiated and starts waiting for messages.
    """
    op.execute("""
        UPDATE bulk_content_scan_logs
        SET status = 'in_progress',
            completed_at = NULL,
            updated_at = NOW()
        WHERE messages_scanned = 0
          AND status = 'completed'
          AND completed_at = initiated_at
    """)
