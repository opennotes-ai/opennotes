"""fix_premature_note_status_changes

Revision ID: 53ef90ea75aa
Revises: 99fd02d32ce2
Create Date: 2025-12-03 16:38:06.358629

This migration fixes notes that were incorrectly marked as CURRENTLY_RATED_HELPFUL
or CURRENTLY_RATED_NOT_HELPFUL before reaching the minimum rating threshold.

The bug occurred in ratings_router.py where status was changed after just ONE
rating instead of waiting for MIN_RATINGS_NEEDED (default: 5) ratings.

Affected notes are identified as:
- Status = 'CURRENTLY_RATED_HELPFUL' or 'CURRENTLY_RATED_NOT_HELPFUL'
- Has fewer than MIN_RATINGS_NEEDED (5) ratings

These notes are reset to NEEDS_MORE_RATINGS status.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "53ef90ea75aa"
down_revision: str | Sequence[str] | None = "99fd02d32ce2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MIN_RATINGS_NEEDED = 5


def upgrade() -> None:
    conn = op.get_bind()

    find_affected_sql = sa.text("""
        SELECT n.id, n.status,
               (SELECT COUNT(*) FROM ratings r WHERE r.note_id = n.id) as rating_count
        FROM notes n
        WHERE n.status IN ('CURRENTLY_RATED_HELPFUL', 'CURRENTLY_RATED_NOT_HELPFUL')
        AND (SELECT COUNT(*) FROM ratings r WHERE r.note_id = n.id) < :threshold
    """)

    affected_notes = conn.execute(find_affected_sql, {"threshold": MIN_RATINGS_NEEDED}).fetchall()

    if affected_notes:
        print(f"[MIGRATION] Found {len(affected_notes)} notes with premature status changes")
        for note in affected_notes:
            print(f"[MIGRATION]   Note {note[0]}: status={note[1]}, rating_count={note[2]}")

        update_sql = sa.text("""
            UPDATE notes
            SET status = 'NEEDS_MORE_RATINGS'
            WHERE status IN ('CURRENTLY_RATED_HELPFUL', 'CURRENTLY_RATED_NOT_HELPFUL')
            AND (SELECT COUNT(*) FROM ratings r WHERE r.note_id = notes.id) < :threshold
        """)

        result = conn.execute(update_sql, {"threshold": MIN_RATINGS_NEEDED})
        print(f"[MIGRATION] Updated {result.rowcount} notes to NEEDS_MORE_RATINGS")
    else:
        print("[MIGRATION] No notes with premature status changes found - nothing to fix")


def downgrade() -> None:
    print("[MIGRATION] Downgrade is a no-op for this data fix migration")
    print("[MIGRATION] Reason: We cannot reliably determine the original incorrect status")
