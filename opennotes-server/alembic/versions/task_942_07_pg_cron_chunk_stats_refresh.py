"""task-942.07: Add pg_cron job for nightly chunk_stats refresh

Schedule nightly refresh of chunk_stats materialized view for BM25/TF-IDF
scoring accuracy using pg_cron.

The chunk_stats view provides:
- total_chunks: Total number of chunks with word_count > 0
- avg_chunk_length: Average word count across all chunks

These statistics are used for document length normalization in BM25 scoring.
Daily refresh is sufficient as BM25 is robust to minor statistical drift.

IMPORTANT: pg_cron has a database restriction - it can only be installed in
the database specified by `cron.database_name` in postgresql.conf. This means:
- Production (Supabase): pg_cron is pre-installed, we just schedule the job
- CI/Tests: pg_cron cannot be installed on template databases, so we skip

Revision ID: 94207a1b2c3d
Revises: 94201a1b2c3d
Create Date: 2026-01-03 02:00:00.000000

"""

from collections.abc import Sequence

from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from alembic import op

revision: str = "94207a1b2c3d"
down_revision: str | Sequence[str] | None = "94201a1b2c3d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _pg_cron_available(connection) -> bool:
    """Check if pg_cron extension is available and can be used."""
    result = connection.execute(
        text(
            """
            SELECT EXISTS (
                SELECT 1 FROM pg_extension WHERE extname = 'pg_cron'
            )
            """
        )
    )
    return result.scalar()


def upgrade() -> None:
    connection = op.get_bind()

    try:
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_cron")
    except ProgrammingError as e:
        error_msg = str(e).lower()
        if "can only create extension in database" in error_msg:
            print(
                "pg_cron: Skipping extension creation (not allowed on this database). "
                "This is expected in test/CI environments."
            )
            return
        if "cron.database_name" in error_msg or "unrecognized configuration parameter" in error_msg:
            print(
                "pg_cron: Skipping - pg_cron not configured on this PostgreSQL server. "
                "This is expected in test/CI environments."
            )
            return
        raise

    if _pg_cron_available(connection):
        connection.execute(
            text(
                """
                SELECT cron.schedule(
                    'refresh-chunk-stats',
                    '0 3 * * *',
                    'REFRESH MATERIALIZED VIEW CONCURRENTLY chunk_stats'
                )
                """
            )
        )
    else:
        print("pg_cron: Extension not available, skipping job scheduling.")


def downgrade() -> None:
    connection = op.get_bind()

    if _pg_cron_available(connection):
        connection.execute(text("SELECT cron.unschedule('refresh-chunk-stats')"))
        op.execute("DROP EXTENSION IF EXISTS pg_cron")
