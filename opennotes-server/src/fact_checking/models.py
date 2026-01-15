from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import ARRAY, CheckConstraint, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import DateTime

from src.database import Base

if TYPE_CHECKING:
    from src.fact_checking.chunk_models import FactCheckChunk


class FactCheckItem(Base):
    """
    Generic fact-checking dataset item with vector embeddings.

    Supports multiple fact-checking sources (Snopes, PolitiFact, etc.) with
    provenance tracking and semantic search via pgvector embeddings.

    Attributes:
        id: Unique identifier (UUID)
        dataset_name: Source dataset name (e.g., 'snopes', 'politifact')
        dataset_tags: Array of tags for filtering (e.g., ['snopes', 'fact-check'])
        title: Fact-check article title
        content: Main text content (used for embedding generation)
        summary: Optional brief summary
        source_url: URL to original fact-check article
        original_id: ID from source dataset
        published_date: Publication date from source
        author: Author name from source
        rating: Fact-check verdict (e.g., 'false', 'mostly-true', 'mixture')
        embedding: pgvector embedding for semantic search (1536 dimensions)
        extra_metadata: Flexible JSONB for dataset-specific fields (database column: 'metadata')
        search_vector: PostgreSQL tsvector for full-text search (auto-populated by trigger)
        created_at: Timestamp when record was created
        updated_at: Timestamp of last update
    """

    __tablename__ = "fact_check_items"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("uuidv7()"),
        index=True,
    )

    # Dataset identification
    dataset_name: Mapped[str] = mapped_column(String(100), nullable=False)
    dataset_tags: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, index=True)

    # Core content
    title: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Provenance
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    original_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    published_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    author: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Rating/verdict
    rating: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # DEPRECATED: Use chunk_embeddings table instead. Will be removed in v2.0.
    # Vector embedding for semantic search
    # Using 1536 dimensions for OpenAI text-embedding-3-small
    embedding: Mapped[Any | None] = mapped_column(Vector(1536), nullable=True)

    # DEPRECATED: Use chunk_embeddings table instead. Will be removed in v2.0.
    # Embedding provider and model tracking
    embedding_provider: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="LLM provider used for embedding generation (e.g., 'openai', 'anthropic')",
    )
    # DEPRECATED: Use chunk_embeddings table instead. Will be removed in v2.0.
    embedding_model: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Model name used for embedding generation (e.g., 'text-embedding-3-small')",
    )

    # Flexible metadata for dataset-specific fields
    # Note: Using 'extra_metadata' instead of 'metadata' which is reserved by SQLAlchemy
    extra_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, server_default="{}"
    )

    # Full-text search vector (auto-populated by database trigger)
    # Weight 'A' for title, weight 'B' for content
    search_vector: Mapped[Any | None] = mapped_column(TSVECTOR(), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=lambda: datetime.now(UTC),
    )

    chunks: Mapped[list["FactCheckChunk"]] = relationship(
        "FactCheckChunk",
        back_populates="fact_check_item",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    # Indexes and constraints
    __table_args__ = (
        # Ensure at least one tag is present
        CheckConstraint("array_length(dataset_tags, 1) > 0", name="check_dataset_tags_not_empty"),
        # B-tree indexes for filtering
        Index("idx_fact_check_items_dataset_name", "dataset_name"),
        Index("idx_fact_check_items_created_at", "created_at"),
        Index("idx_fact_check_items_dataset_tags", "dataset_tags", postgresql_using="gin"),
        # GIN index for JSONB extra_metadata queries
        Index("idx_fact_check_items_metadata", "metadata", postgresql_using="gin"),
        # Index for published_date queries
        Index("idx_fact_check_items_published_date", "published_date"),
        # Composite index for common query pattern
        Index("idx_fact_check_items_dataset_name_tags", "dataset_name", "dataset_tags"),
        # Index for filtering by embedding version
        Index("idx_fact_check_items_embedding_version", "embedding_provider", "embedding_model"),
        # IVFFlat vector index for embedding similarity searches
        Index(
            "idx_fact_check_items_embedding_ivfflat",
            "embedding",
            postgresql_using="ivfflat",
            postgresql_with={"lists": 100},
        ),
        # GIN index for full-text search on search_vector
        Index("ix_fact_check_items_search_vector", "search_vector", postgresql_using="gin"),
    )

    def __repr__(self) -> str:
        return f"<FactCheckItem(id={self.id}, dataset={self.dataset_name}, title='{self.title[:50]}...')>"
