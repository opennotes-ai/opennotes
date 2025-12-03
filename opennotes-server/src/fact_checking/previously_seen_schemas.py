"""Pydantic schemas for previously seen message tracking."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.common.base_schemas import SQLAlchemySchema, StrictInputSchema


class PreviouslySeenMessageBase(BaseModel):
    """Base schema for previously seen message."""

    community_server_id: UUID = Field(..., description="Community server UUID")
    original_message_id: str = Field(..., description="Platform-specific message ID", max_length=64)
    published_note_id: UUID = Field(..., description="Note ID that was published for this message")
    embedding: list[float] | None = Field(
        None, description="Vector embedding for semantic similarity search (1536 dimensions)"
    )
    embedding_provider: str | None = Field(
        None, description="LLM provider used for embedding generation", max_length=50
    )
    embedding_model: str | None = Field(
        None, description="Model name used for embedding generation", max_length=100
    )
    extra_metadata: dict[str, str | int | float | bool | None] = Field(
        default_factory=dict, description="Additional context metadata"
    )


class PreviouslySeenMessageCreate(PreviouslySeenMessageBase, StrictInputSchema):
    """Schema for creating a previously seen message record."""


class PreviouslySeenMessageUpdate(StrictInputSchema):
    """Schema for updating a previously seen message record."""

    extra_metadata: dict[str, str | int | float | bool | None] | None = Field(
        None, description="Additional context metadata"
    )


class PreviouslySeenMessageResponse(PreviouslySeenMessageBase, SQLAlchemySchema):
    """Schema for previously seen message responses."""

    id: UUID = Field(..., description="Unique identifier")
    created_at: datetime = Field(..., description="When record was created")


class PreviouslySeenMessageMatch(SQLAlchemySchema):
    """Previously seen message with similarity score (used in search results)."""

    id: UUID = Field(..., description="Unique identifier")
    community_server_id: UUID = Field(..., description="Community server UUID")
    original_message_id: str = Field(..., description="Platform-specific message ID")
    published_note_id: UUID = Field(..., description="Note ID that was published")
    embedding_provider: str | None = Field(None, description="LLM provider used")
    embedding_model: str | None = Field(None, description="Model name used")
    extra_metadata: dict[str, str | int | float | bool | None] = Field(
        default_factory=dict, description="Additional context metadata"
    )
    created_at: datetime = Field(..., description="When record was created")
    similarity_score: float = Field(
        ..., description="Cosine similarity score (0.0-1.0)", ge=0.0, le=1.0
    )


class PreviouslySeenSearchResponse(BaseModel):
    """Response schema for previously seen message search."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    matches: list[PreviouslySeenMessageMatch] = Field(
        ..., description="Matching previously seen messages"
    )
    query_text: str = Field(..., description="Original query text")
    similarity_threshold: float = Field(..., description="Similarity threshold applied")
    total_matches: int = Field(..., description="Number of matches found")
