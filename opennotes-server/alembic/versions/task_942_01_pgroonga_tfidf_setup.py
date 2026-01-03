"""task-942.01: Add PGroonga TF-IDF scoring infrastructure

Enable PGroonga extension and set up infrastructure for TF-IDF scoring:
- Enable PGroonga extension for full-text search with Japanese/CJK support
- Create PGroonga index on chunk_embeddings.chunk_text for efficient FTS
- Add word_count column to chunk_embeddings for TF-IDF calculations
- Create trigger to auto-compute word_count on INSERT/UPDATE
- Create chunk_stats materialized view for global corpus statistics

The chunk_stats materialized view should be refreshed nightly via scheduled job.
See docs/chunk-stats-refresh.md for refresh strategy.

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


def upgrade() -> None:
    """Add PGroonga TF-IDF infrastructure to chunk_embeddings."""
    op.execute("CREATE EXTENSION IF NOT EXISTS pgroonga")

    op.add_column(
        "chunk_embeddings",
        sa.Column(
            "word_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Word count of chunk_text for TF-IDF calculations",
        ),
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION chunk_embeddings_word_count_trigger()
        RETURNS trigger AS $$
        BEGIN
            NEW.word_count := COALESCE(
                array_length(
                    regexp_split_to_array(NULLIF(TRIM(NEW.chunk_text), ''), E'\\s+'),
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

    op.execute(
        """
        UPDATE chunk_embeddings
        SET word_count = COALESCE(
            array_length(
                regexp_split_to_array(NULLIF(TRIM(chunk_text), ''), E'\\s+'),
                1
            ),
            0
        )
        WHERE word_count = 0
        """
    )

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
