"""task-942.07: Add pg_cron job for nightly chunk_stats refresh

Set up pg_cron extension and schedule nightly refresh of chunk_stats
materialized view for BM25/TF-IDF scoring accuracy.

The chunk_stats view provides:
- total_chunks: Total number of chunks with word_count > 0
- avg_chunk_length: Average word count across all chunks

These statistics are used for document length normalization in BM25 scoring.
Daily refresh is sufficient as BM25 is robust to minor statistical drift.

Revision ID: 94207a1b2c3d
Revises: 94201a1b2c3d
Create Date: 2026-01-03 02:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "94207a1b2c3d"
down_revision: str | Sequence[str] | None = "94201a1b2c3d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_cron")

    op.execute(
        """
        SELECT cron.schedule(
            'refresh-chunk-stats',
            '0 3 * * *',
            'REFRESH MATERIALIZED VIEW CONCURRENTLY chunk_stats'
        )
        """
    )


def downgrade() -> None:
    op.execute("SELECT cron.unschedule('refresh-chunk-stats')")

    op.execute("DROP EXTENSION IF EXISTS pg_cron")
