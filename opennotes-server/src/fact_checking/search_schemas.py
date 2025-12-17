"""Pydantic schemas for hybrid search endpoint."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.common.base_schemas import StrictInputSchema


class HybridSearchRequest(StrictInputSchema):
    """Request body for hybrid search endpoint."""

    query: str = Field(
        ...,
        min_length=1,
        max_length=50000,
        description="Search query text for hybrid search",
    )
    limit: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Maximum number of results to return",
    )


class FactCheckSearchResult(BaseModel):
    """Individual search result from hybrid search."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Unique identifier for the fact-check item")
    title: str = Field(..., description="Fact-check article title")
    content: str = Field(..., description="Main content of the fact-check")
    summary: str | None = Field(None, description="Brief summary of the fact-check")
    source_url: str | None = Field(None, description="URL to original fact-check article")
    rating: str | None = Field(None, description="Fact-check verdict/rating")
    dataset_name: str = Field(..., description="Source dataset name")
    dataset_tags: list[str] = Field(..., description="Dataset tags for filtering")
    published_date: datetime | None = Field(None, description="Publication date")
    author: str | None = Field(None, description="Author name")


class HybridSearchResponse(BaseModel):
    """Response for hybrid search endpoint."""

    model_config = ConfigDict(from_attributes=True)

    results: list[FactCheckSearchResult] = Field(
        ..., description="List of matching fact-check items ranked by relevance"
    )
    query: str = Field(..., description="Original query text")
    total: int = Field(..., description="Number of results returned")
