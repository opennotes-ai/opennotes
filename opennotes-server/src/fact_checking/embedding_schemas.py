"""Pydantic schemas for embedding generation and similarity search."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.common.base_schemas import SQLAlchemySchema, StrictInputSchema
from src.config import settings


class EmbeddingRequest(StrictInputSchema):
    """Request schema for generating embeddings."""

    text: str = Field(
        ..., description="Text to generate embedding for", min_length=1, max_length=50000
    )
    community_server_id: str = Field(..., description="Community server (guild) ID", max_length=64)


class SimilaritySearchRequest(StrictInputSchema):
    """Request schema for similarity search against fact-check items."""

    text: str = Field(
        ...,
        description="Message text to search for similar fact-checks",
        min_length=1,
        max_length=50000,
    )
    community_server_id: str = Field(..., description="Community server (guild) ID", max_length=64)
    dataset_tags: list[str] = Field(
        default_factory=lambda: ["snopes"],
        description="Dataset tags to filter by (e.g., ['snopes', 'politifact'])",
    )
    similarity_threshold: float = Field(
        default_factory=lambda: settings.SIMILARITY_SEARCH_DEFAULT_THRESHOLD,
        description="Minimum cosine similarity (0.0-1.0) for semantic search pre-filtering",
        ge=0.0,
        le=1.0,
    )
    score_threshold: float = Field(
        0.1,
        description="Minimum CC score (0.0-1.0) for post-fusion filtering",
        ge=0.0,
        le=1.0,
    )
    limit: int = Field(5, description="Maximum number of results to return", ge=1, le=20)


class FactCheckMatch(SQLAlchemySchema):
    """Single fact-check similarity match result."""

    id: UUID = Field(..., description="Fact-check item UUID")
    dataset_name: str = Field(..., description="Source dataset (e.g., 'snopes')")
    dataset_tags: list[str] = Field(..., description="Dataset tags")
    title: str = Field(..., description="Fact-check article title")
    content: str = Field(..., description="Fact-check content")
    summary: str | None = Field(None, description="Brief summary")
    rating: str | None = Field(None, description="Fact-check verdict")
    source_url: str | None = Field(None, description="URL to original article")
    published_date: datetime | None = Field(None, description="Publication date")
    author: str | None = Field(None, description="Author name")
    embedding_provider: str | None = Field(
        None, description="LLM provider used for embedding (e.g., 'openai')"
    )
    embedding_model: str | None = Field(
        None, description="Model name used for embedding (e.g., 'text-embedding-3-small')"
    )
    similarity_score: float = Field(..., description="CC fusion score (0.0-1.0)", ge=0.0, le=1.0)
    cosine_similarity: float = Field(
        0.0, description="Raw cosine similarity score (0.0-1.0)", ge=0.0, le=1.0
    )


class SimilaritySearchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    """Response schema for similarity search."""

    matches: list[FactCheckMatch] = Field(..., description="Matching fact-check items")
    query_text: str = Field(..., description="Original query text")
    dataset_tags: list[str] = Field(..., description="Dataset tags used for filtering")
    similarity_threshold: float = Field(..., description="Cosine similarity threshold applied")
    score_threshold: float = Field(..., description="CC score threshold applied")
    total_matches: int = Field(..., description="Number of matches found")
