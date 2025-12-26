"""
Chunk-based embedding models for semantic search.

This module provides the data models for chunked content embeddings,
enabling more granular semantic search compared to full-document embeddings.
Content is split into smaller chunks, each with its own embedding, allowing
for better matching of specific claims within larger documents.

Models:
    ChunkEmbedding: Main table storing unique text chunks and their embeddings
    FactCheckChunk: Join table linking chunks to FactCheckItem entries
    PreviouslySeenChunk: Join table linking chunks to PreviouslySeenMessage entries
"""

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base

if TYPE_CHECKING:
    from src.fact_checking.models import FactCheckItem
    from src.fact_checking.previously_seen_models import PreviouslySeenMessage


class ChunkEmbedding(Base):
    """
    Stores unique text chunks with their vector embeddings.

    Each chunk represents a segment of text from either a fact-check item
    or a previously seen message. Chunks are deduplicated by text content,
    allowing the same chunk to be referenced by multiple source documents.

    Note: chunk_index (position in document) is stored in the join tables
    (FactCheckChunk, PreviouslySeenChunk) rather than here, because the same
    chunk text can appear at different positions in different documents.

    Attributes:
        id: Unique identifier (UUID v7)
        chunk_text: The text content of the chunk (unique across all chunks)
        embedding: Vector embedding for semantic search (1536 dimensions)
        embedding_provider: LLM provider used for embedding generation
        embedding_model: Model name used for embedding generation
        is_common: Flag indicating common/boilerplate text (may be filtered in searches)
        created_at: Timestamp when record was created
    """

    __tablename__ = "chunk_embeddings"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()"), index=True
    )

    chunk_text: Mapped[str] = mapped_column(
        Text, nullable=False, unique=True, comment="Unique text content of the chunk"
    )

    embedding: Mapped[Any | None] = mapped_column(
        Vector(1536), nullable=True, comment="Vector embedding for semantic search"
    )

    embedding_provider: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="LLM provider used for embedding generation (e.g., 'openai', 'anthropic')",
    )

    embedding_model: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Model name used for embedding generation (e.g., 'text-embedding-3-small')",
    )

    is_common: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment="Flag for common/boilerplate text that may be filtered in searches",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        comment="Timestamp when record was created",
    )

    def __init__(self, **kwargs: Any) -> None:
        """Initialize ChunkEmbedding with default values."""
        if "is_common" not in kwargs:
            kwargs["is_common"] = False
        if "created_at" not in kwargs:
            kwargs["created_at"] = datetime.now(UTC)
        super().__init__(**kwargs)

    fact_check_chunks: Mapped[list["FactCheckChunk"]] = relationship(
        "FactCheckChunk", back_populates="chunk", cascade="all, delete-orphan"
    )

    previously_seen_chunks: Mapped[list["PreviouslySeenChunk"]] = relationship(
        "PreviouslySeenChunk", back_populates="chunk", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index(
            "idx_chunk_embeddings_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("idx_chunk_embeddings_is_common", "is_common"),
        Index("idx_chunk_embeddings_embedding_version", "embedding_provider", "embedding_model"),
    )

    def __repr__(self) -> str:
        text_preview = self.chunk_text[:20] if self.chunk_text else ""
        return f"<ChunkEmbedding(id={self.id}, text='{text_preview}...')>"


class FactCheckChunk(Base):
    """
    Join table linking ChunkEmbedding to FactCheckItem.

    Enables many-to-many relationship where a fact-check item can have
    multiple chunks, and the same chunk text can appear in multiple
    fact-check items.

    Attributes:
        id: Unique identifier (UUID v7)
        chunk_id: Foreign key to chunk_embeddings table
        fact_check_id: Foreign key to fact_check_items table
        chunk_index: Position of this chunk in the fact-check document (0-indexed)
        created_at: Timestamp when relationship was created
    """

    __tablename__ = "fact_check_chunks"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()"), index=True
    )

    chunk_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("chunk_embeddings.id", ondelete="CASCADE"),
        nullable=False,
    )

    fact_check_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("fact_check_items.id", ondelete="CASCADE"),
        nullable=False,
    )

    chunk_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Position of this chunk in the fact-check document (0-indexed)",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    chunk: Mapped["ChunkEmbedding"] = relationship(
        "ChunkEmbedding", back_populates="fact_check_chunks"
    )
    fact_check_item: Mapped["FactCheckItem"] = relationship("FactCheckItem")

    __table_args__ = (
        UniqueConstraint("chunk_id", "fact_check_id", name="uq_fact_check_chunks_chunk_fact_check"),
        Index("idx_fact_check_chunks_chunk_id", "chunk_id"),
        Index("idx_fact_check_chunks_fact_check_id", "fact_check_id"),
    )

    def __repr__(self) -> str:
        return f"<FactCheckChunk(id={self.id}, chunk_id={self.chunk_id}, fact_check_id={self.fact_check_id})>"


class PreviouslySeenChunk(Base):
    """
    Join table linking ChunkEmbedding to PreviouslySeenMessage.

    Enables many-to-many relationship where a previously seen message
    can have multiple chunks, and the same chunk text can appear in
    multiple messages.

    Attributes:
        id: Unique identifier (UUID v7)
        chunk_id: Foreign key to chunk_embeddings table
        previously_seen_id: Foreign key to previously_seen_messages table
        chunk_index: Position of this chunk in the message (0-indexed)
        created_at: Timestamp when relationship was created
    """

    __tablename__ = "previously_seen_chunks"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()"), index=True
    )

    chunk_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("chunk_embeddings.id", ondelete="CASCADE"),
        nullable=False,
    )

    previously_seen_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("previously_seen_messages.id", ondelete="CASCADE"),
        nullable=False,
    )

    chunk_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Position of this chunk in the message (0-indexed)",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    chunk: Mapped["ChunkEmbedding"] = relationship(
        "ChunkEmbedding", back_populates="previously_seen_chunks"
    )
    previously_seen_message: Mapped["PreviouslySeenMessage"] = relationship("PreviouslySeenMessage")

    __table_args__ = (
        UniqueConstraint(
            "chunk_id", "previously_seen_id", name="uq_previously_seen_chunks_chunk_previously_seen"
        ),
        Index("idx_previously_seen_chunks_chunk_id", "chunk_id"),
        Index("idx_previously_seen_chunks_previously_seen_id", "previously_seen_id"),
    )

    def __repr__(self) -> str:
        return f"<PreviouslySeenChunk(id={self.id}, chunk_id={self.chunk_id}, previously_seen_id={self.previously_seen_id})>"
