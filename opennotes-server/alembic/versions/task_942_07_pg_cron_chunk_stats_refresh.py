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

from alembic import op

revision: str = "94207a1b2c3d"
down_revision: str | Sequence[str] | None = "94201a1b2c3d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _pg_cron_installed(connection) -> bool:
    """Check if pg_cron extension is already installed."""
    result = connection.execute(
        text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_cron')")
    )
    return result.scalar()


def _pg_cron_loadable(connection) -> bool:
    """Check if pg_cron extension can actually be created.

    pg_cron requires both:
    1. The extension package to be installed (in pg_available_extensions)
    2. pg_cron to be in shared_preload_libraries (required for background worker)

    If only the package is installed but pg_cron isn't in shared_preload_libraries,
    CREATE EXTENSION will fail with "unrecognized configuration parameter cron.database_name".
    """
    pkg_result = connection.execute(
        text("SELECT EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'pg_cron')")
    )
    if not pkg_result.scalar():
        return False

    lib_result = connection.execute(text("SHOW shared_preload_libraries"))
    shared_libs = lib_result.scalar() or ""
    return "pg_cron" in shared_libs


def upgrade() -> None:
    connection = op.get_bind()

    if _pg_cron_installed(connection):
        print("pg_cron: Extension already installed.")
    elif _pg_cron_loadable(connection):
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_cron")
        print("pg_cron: Extension created successfully.")
    else:
        print(
            "pg_cron: Extension not available (not in shared_preload_libraries). "
            "Skipping. This is expected in test/CI environments."
        )
        return

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


def downgrade() -> None:
    connection = op.get_bind()

    if _pg_cron_installed(connection):
        connection.execute(text("SELECT cron.unschedule('refresh-chunk-stats')"))
        op.execute("DROP EXTENSION IF EXISTS pg_cron")
