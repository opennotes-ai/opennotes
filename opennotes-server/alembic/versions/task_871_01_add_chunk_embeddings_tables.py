"""task-871.01: Add chunk_embeddings tables with HNSW index and FTS

Create three tables for chunk-based embeddings:
- chunk_embeddings: Main table storing unique text chunks with embeddings, HNSW index, and FTS
- fact_check_chunks: Join table linking chunks to fact_check_items
- previously_seen_chunks: Join table linking chunks to previously_seen_messages

Includes:
- xxh3_64 hash column for efficient uniqueness checking (avoids B-tree index size limits on TEXT)
- HNSW index for vector similarity search
- GIN index on tsvector for full-text search
- Trigger to auto-populate search_vector on insert/update

Revision ID: 87101a1b2c3d
Revises: 865a1b2c3d4e
Create Date: 2025-12-25 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import TSVECTOR, UUID

from alembic import op

revision: str = "87101a1b2c3d"
down_revision: str | Sequence[str] | None = "865a1b2c3d4e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create chunk embedding tables with HNSW index for semantic search."""

    op.create_table(
        "chunk_embeddings",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuidv7()"),
            nullable=False,
        ),
        sa.Column(
            "chunk_text",
            sa.Text(),
            nullable=False,
            comment="Text content of the chunk",
        ),
        sa.Column(
            "chunk_text_hash",
            sa.String(16),
            nullable=False,
            unique=True,
            comment="xxh3_64 hash of chunk_text for efficient uniqueness checking",
        ),
        sa.Column(
            "embedding",
            Vector(1536),
            nullable=True,
            comment="Vector embedding for semantic search",
        ),
        sa.Column(
            "embedding_provider",
            sa.String(50),
            nullable=True,
            comment="LLM provider used for embedding generation (e.g., 'openai', 'anthropic')",
        ),
        sa.Column(
            "embedding_model",
            sa.String(100),
            nullable=True,
            comment="Model name used for embedding generation (e.g., 'text-embedding-3-small')",
        ),
        sa.Column(
            "is_common",
            sa.Boolean(),
            nullable=False,
            server_default="false",
            comment="Flag for common/boilerplate text that may be filtered in searches",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
            comment="Timestamp when record was created",
        ),
        sa.Column(
            "search_vector",
            TSVECTOR,
            nullable=True,
            comment="Full-text search vector for chunk text (auto-populated by trigger)",
        ),
    )

    op.create_index("idx_chunk_embeddings_is_common", "chunk_embeddings", ["is_common"])
    op.create_index(
        "idx_chunk_embeddings_embedding_version",
        "chunk_embeddings",
        ["embedding_provider", "embedding_model"],
    )

    op.create_index(
        "idx_chunk_embeddings_embedding_hnsw",
        "chunk_embeddings",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )

    op.create_index(
        "idx_chunk_embeddings_search_vector",
        "chunk_embeddings",
        ["search_vector"],
        postgresql_using="gin",
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION chunk_embeddings_search_vector_trigger()
        RETURNS trigger AS $$
        BEGIN
            NEW.search_vector := to_tsvector('english', COALESCE(NEW.chunk_text, ''));
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    op.execute(
        """
        CREATE TRIGGER chunk_embeddings_search_vector_update
        BEFORE INSERT OR UPDATE OF chunk_text ON chunk_embeddings
        FOR EACH ROW
        EXECUTE FUNCTION chunk_embeddings_search_vector_trigger();
        """
    )

    op.create_table(
        "fact_check_chunks",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuidv7()"),
            nullable=False,
        ),
        sa.Column(
            "chunk_id",
            UUID(as_uuid=True),
            sa.ForeignKey("chunk_embeddings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "fact_check_id",
            UUID(as_uuid=True),
            sa.ForeignKey("fact_check_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "chunk_index",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Position of this chunk in the fact-check document (0-indexed)",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint(
            "chunk_id", "fact_check_id", name="uq_fact_check_chunks_chunk_fact_check"
        ),
    )

    op.create_index("idx_fact_check_chunks_chunk_id", "fact_check_chunks", ["chunk_id"])
    op.create_index("idx_fact_check_chunks_fact_check_id", "fact_check_chunks", ["fact_check_id"])

    op.create_table(
        "previously_seen_chunks",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuidv7()"),
            nullable=False,
        ),
        sa.Column(
            "chunk_id",
            UUID(as_uuid=True),
            sa.ForeignKey("chunk_embeddings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "previously_seen_id",
            UUID(as_uuid=True),
            sa.ForeignKey("previously_seen_messages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "chunk_index",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Position of this chunk in the message (0-indexed)",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint(
            "chunk_id",
            "previously_seen_id",
            name="uq_previously_seen_chunks_chunk_previously_seen",
        ),
    )

    op.create_index("idx_previously_seen_chunks_chunk_id", "previously_seen_chunks", ["chunk_id"])
    op.create_index(
        "idx_previously_seen_chunks_previously_seen_id",
        "previously_seen_chunks",
        ["previously_seen_id"],
    )


def downgrade() -> None:
    """Drop chunk embedding tables, trigger, and function."""
    op.execute("DROP TRIGGER IF EXISTS chunk_embeddings_search_vector_update ON chunk_embeddings")
    op.execute("DROP FUNCTION IF EXISTS chunk_embeddings_search_vector_trigger()")
    op.drop_table("previously_seen_chunks")
    op.drop_table("fact_check_chunks")
    op.drop_table("chunk_embeddings")
