"""task-942.01: Add PGroonga TF-IDF scoring infrastructure

Enable PGroonga extension and set up infrastructure for TF-IDF scoring:
- Enable PGroonga extension for full-text search with Japanese/CJK support
- Create PGroonga index on chunk_embeddings.chunk_text for efficient FTS
- Add word_count column to chunk_embeddings for TF-IDF calculations
- Create chunk_stats materialized view for global corpus statistics

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
        UPDATE chunk_embeddings
        SET word_count = array_length(regexp_split_to_array(chunk_text, E'\\s+'), 1)
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

    op.execute("CREATE UNIQUE INDEX ON chunk_stats ((1))")


def downgrade() -> None:
    """Remove PGroonga TF-IDF infrastructure from chunk_embeddings."""
    op.execute("DROP MATERIALIZED VIEW IF EXISTS chunk_stats")

    op.execute("DROP INDEX IF EXISTS idx_chunk_embeddings_pgroonga")

    op.drop_column("chunk_embeddings", "word_count")

    op.execute("DROP EXTENSION IF EXISTS pgroonga CASCADE")
