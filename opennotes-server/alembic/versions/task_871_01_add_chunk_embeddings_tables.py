"""task-871.01: Add chunk_embeddings tables with HNSW index

Create three tables for chunk-based embeddings:
- chunk_embeddings: Main table storing unique text chunks with embeddings and HNSW index
- fact_check_chunks: Join table linking chunks to fact_check_items
- previously_seen_chunks: Join table linking chunks to previously_seen_messages

Revision ID: 87101a1b2c3d
Revises: 865a1b2c3d4e
Create Date: 2025-12-25 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import UUID

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
            unique=True,
            comment="Unique text content of the chunk",
        ),
        sa.Column(
            "chunk_index",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Position of this chunk in the original document (0-indexed)",
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
    )

    op.create_index("idx_chunk_embeddings_id", "chunk_embeddings", ["id"])
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
            index=True,
        ),
        sa.Column(
            "fact_check_id",
            UUID(as_uuid=True),
            sa.ForeignKey("fact_check_items.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
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

    op.create_index("idx_fact_check_chunks_id", "fact_check_chunks", ["id"])
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
            index=True,
        ),
        sa.Column(
            "previously_seen_id",
            UUID(as_uuid=True),
            sa.ForeignKey("previously_seen_messages.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
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

    op.create_index("idx_previously_seen_chunks_id", "previously_seen_chunks", ["id"])
    op.create_index("idx_previously_seen_chunks_chunk_id", "previously_seen_chunks", ["chunk_id"])
    op.create_index(
        "idx_previously_seen_chunks_previously_seen_id",
        "previously_seen_chunks",
        ["previously_seen_id"],
    )


def downgrade() -> None:
    """Drop chunk embedding tables."""
    op.drop_table("previously_seen_chunks")
    op.drop_table("fact_check_chunks")
    op.drop_table("chunk_embeddings")
