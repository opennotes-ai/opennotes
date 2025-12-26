from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base

if TYPE_CHECKING:
    from src.llm_config.models import CommunityServer


class PreviouslySeenMessage(Base):
    """
    Tracks embeddings of previously seen messages for duplicate detection.

    When a note is published, the original message embedding is stored here
    to enable duplicate detection and auto-publishing of existing notes for
    similar future messages.

    Attributes:
        id: Unique identifier (UUID v7)
        community_server_id: Foreign key to community_servers table
        original_message_id: Platform-specific message ID (e.g., Discord message ID)
        published_note_id: Reference to the note that was published for this message
        embedding: Vector embedding for semantic similarity search (1536 dimensions)
        embedding_provider: LLM provider used for embedding generation
        embedding_model: Model name used for embedding generation
        extra_metadata: Flexible JSONB for additional context (database column: 'metadata')
        created_at: Timestamp when record was created
    """

    __tablename__ = "previously_seen_messages"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()"), index=True
    )

    # Community server relationship
    community_server_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("community_servers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Message identification
    original_message_id: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True, comment="Platform-specific message ID"
    )

    # Published note reference
    published_note_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("notes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Note that was published for this message",
    )

    # DEPRECATED: Use chunk_embeddings table instead. Will be removed in future version.
    # Vector embedding for semantic search
    # Using 1536 dimensions for OpenAI text-embedding-3-small (matches FactCheckItem)
    embedding: Mapped[Any | None] = mapped_column(Vector(1536), nullable=True)

    # DEPRECATED: Use chunk_embeddings table instead. Will be removed in future version.
    # Embedding provider and model tracking
    embedding_provider: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="LLM provider used for embedding generation (e.g., 'openai', 'anthropic')",
    )
    # DEPRECATED: Use chunk_embeddings table instead. Will be removed in future version.
    embedding_model: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Model name used for embedding generation (e.g., 'text-embedding-3-small')",
    )

    # Flexible metadata for additional context
    extra_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, server_default="{}"
    )

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    # Relationships
    community_server: Mapped["CommunityServer"] = relationship("CommunityServer", lazy="joined")

    def __init__(self, **kwargs: Any) -> None:
        """Initialize PreviouslySeenMessage with automatic created_at timestamp."""
        # Set created_at default if not provided
        if "created_at" not in kwargs:
            kwargs["created_at"] = datetime.now(UTC)
        super().__init__(**kwargs)

    # Indexes and constraints
    __table_args__ = (
        # B-tree index for community_server_id filtering
        Index("idx_previously_seen_messages_community_server_id", "community_server_id"),
        # Index for message ID lookups
        Index("idx_previously_seen_messages_original_message_id", "original_message_id"),
        # Index for published note reference
        Index("idx_previously_seen_messages_published_note_id", "published_note_id"),
        # GIN index for JSONB metadata queries
        Index("idx_previously_seen_messages_metadata", "metadata", postgresql_using="gin"),
        # Index for filtering by embedding version
        Index(
            "idx_previously_seen_messages_embedding_version",
            "embedding_provider",
            "embedding_model",
        ),
        # IVFFlat vector index for embedding similarity searches
        # Using same configuration as fact_check_items for consistency
        Index(
            "idx_previously_seen_messages_embedding_ivfflat",
            "embedding",
            postgresql_using="ivfflat",
            postgresql_with={"lists": 100},
        ),
    )

    def __repr__(self) -> str:
        return f"<PreviouslySeenMessage(id={self.id}, message_id={self.original_message_id}, note_id={self.published_note_id})>"
