"""task-942.01: Add PGroonga TF-IDF scoring infrastructure

Enable PGroonga extension and set up infrastructure for TF-IDF scoring:
- Enable PGroonga extension for full-text search with Japanese/CJK support
- Create PGroonga index on chunk_embeddings.chunk_text for efficient FTS
- Add word_count column to chunk_embeddings for TF-IDF calculations
- Create trigger to auto-compute word_count on INSERT/UPDATE
- Create chunk_stats materialized view for global corpus statistics

The chunk_stats materialized view is refreshed nightly via pg_cron.
See task_942_07_pg_cron_chunk_stats_refresh.py for the scheduled job setup.

Revision ID: 94201a1b2c3d
Revises: 87146a1b2c3d
Create Date: 2026-01-02 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "94201a1b2c3d"
down_revision: str | Sequence[str] | None = "87146a1b2c3d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _batch_update_word_count(batch_size: int = 50) -> None:
    """Update word_count in batches to avoid statement timeout.

    Uses ID-based pagination with explicit LIMIT to process rows incrementally.
    Each batch is a separate statement, avoiding long-running transactions.
    """
    conn = op.get_bind()

    conn.execute(sa.text("SET statement_timeout = '300s'"))

    # Get total count for progress logging
    result = conn.execute(sa.text("SELECT COUNT(*) FROM chunk_embeddings WHERE word_count = 0"))
    total_rows = result.scalar() or 0

    if total_rows == 0:
        print("word_count: No rows to update")
        return

    print(f"word_count: Starting update of {total_rows} rows in batches of {batch_size}")

    batch_num = 0
    total_updated = 0

    while True:
        # Update a batch using subquery with LIMIT
        result = conn.execute(
            sa.text("""
                UPDATE chunk_embeddings
                SET word_count = COALESCE(
                    array_length(
                        array_remove(
                            regexp_split_to_array(chunk_text, '[[:space:]]+'),
                            ''
                        ),
                        1
                    ),
                    0
                )
                WHERE id IN (
                    SELECT id FROM chunk_embeddings
                    WHERE word_count = 0
                    LIMIT :batch_size
                )
            """),
            {"batch_size": batch_size},
        )
        rows_updated = result.rowcount

        if rows_updated == 0:
            break

        batch_num += 1
        total_updated += rows_updated
        print(
            f"word_count: Batch {batch_num} complete ({rows_updated} rows, {total_updated}/{total_rows} total)"
        )

    print(f"word_count: Migration complete ({batch_num} batches, {total_updated} rows)")

    conn.execute(sa.text("RESET statement_timeout"))


def upgrade() -> None:
    """Add PGroonga TF-IDF infrastructure to chunk_embeddings.

    Word Count Tokenization Strategy:
    ---------------------------------
    The word_count column uses simple whitespace splitting (regexp_split_to_array)
    rather than language-aware tokenization (like PostgreSQL's tsvector/english).

    This is intentional for BM25 length normalization:
    - BM25 needs a rough measure of document length, not linguistic precision
    - Whitespace splitting counts all tokens including stop words
    - tsvector applies stemming and removes stop words (e.g., "the quick brown fox"
      becomes 3 lexemes: 'quick', 'brown', 'fox')
    - PGroonga uses its own ICU-based tokenization for scoring, separate from word_count

    The simple approach is sufficient because:
    1. Length normalization is relative (doc_len / avgdl ratio matters, not absolute count)
    2. Consistent tokenization across all chunks maintains relative proportions
    3. Performance is better without language processing overhead
    """
    op.execute("CREATE EXTENSION IF NOT EXISTS pgroonga")

    op.add_column(
        "chunk_embeddings",
        sa.Column(
            "word_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Word count of chunk_text for TF-IDF length normalization",
        ),
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION chunk_embeddings_word_count_trigger()
        RETURNS trigger AS $$
        BEGIN
            -- Split on whitespace, remove empty strings, count remaining words
            -- array_remove handles edge cases like whitespace-only text
            NEW.word_count := COALESCE(
                array_length(
                    array_remove(
                        regexp_split_to_array(NEW.chunk_text, '[[:space:]]+'),
                        ''
                    ),
                    1
                ),
                0
            );
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    op.execute(
        """
        CREATE TRIGGER chunk_embeddings_word_count_update
        BEFORE INSERT OR UPDATE OF chunk_text ON chunk_embeddings
        FOR EACH ROW
        EXECUTE FUNCTION chunk_embeddings_word_count_trigger();
        """
    )

    # Batch UPDATE to avoid statement timeout on large tables
    _batch_update_word_count(batch_size=50)

    op.execute(
        """
        CREATE INDEX idx_chunk_embeddings_pgroonga
        ON chunk_embeddings USING pgroonga (chunk_text pgroonga_text_full_text_search_ops_v2)
        """
    )

    op.execute(
        """
        CREATE MATERIALIZED VIEW chunk_stats AS
        SELECT
            COUNT(*)::integer AS total_chunks,
            AVG(word_count)::float AS avg_chunk_length
        FROM chunk_embeddings
        WHERE word_count > 0
        """
    )

    op.execute("CREATE UNIQUE INDEX idx_chunk_stats_unique ON chunk_stats ((1))")


def downgrade() -> None:
    """Remove PGroonga TF-IDF infrastructure from chunk_embeddings."""
    op.execute("DROP MATERIALIZED VIEW IF EXISTS chunk_stats")

    op.execute("DROP INDEX IF EXISTS idx_chunk_embeddings_pgroonga")

    op.execute("DROP TRIGGER IF EXISTS chunk_embeddings_word_count_update ON chunk_embeddings")
    op.execute("DROP FUNCTION IF EXISTS chunk_embeddings_word_count_trigger()")

    op.drop_column("chunk_embeddings", "word_count")

    op.execute("DROP EXTENSION IF EXISTS pgroonga CASCADE")
