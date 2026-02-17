"""Pydantic schemas for fact-check candidate JSONAPI endpoints.

Implements JSON:API 1.1 compliant request and response schemas for
candidate review and rating management.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from src.common.base_schemas import SQLAlchemySchema, StrictInputSchema
from src.common.jsonapi import JSONAPILinks, JSONAPIMeta
from src.fact_checking.candidate_models import CandidateStatus


class CandidateAttributes(SQLAlchemySchema):
    """JSON:API attributes for a fact-check candidate."""

    source_url: str = Field(..., description="URL to the original article")
    title: str = Field(..., description="Article title from source")
    content: str | None = Field(None, description="Scraped article body")
    summary: str | None = Field(None, description="Optional summary")
    rating: str | None = Field(None, description="Human-approved fact-check verdict")
    rating_details: str | None = Field(None, description="Original rating before normalization")
    predicted_ratings: dict[str, float] | None = Field(
        None, description="ML/AI predicted ratings as {rating: probability}"
    )
    published_date: datetime | None = Field(None, description="Publication date")
    dataset_name: str = Field(..., description="Source dataset identifier")
    dataset_tags: list[str] = Field(default_factory=list, description="Tags for filtering")
    original_id: str | None = Field(None, description="ID from source dataset")
    status: str = Field(..., description="Processing status")
    error_message: str | None = Field(None, description="Error details if failed")
    created_at: datetime = Field(..., description="Record creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")


class CandidateResource(SQLAlchemySchema):
    """JSON:API resource object for a fact-check candidate."""

    type: Literal["fact-check-candidates"] = "fact-check-candidates"
    id: str
    attributes: CandidateAttributes


class CandidateListResponse(SQLAlchemySchema):
    """JSON:API response for a list of candidates with pagination."""

    data: list[CandidateResource]
    jsonapi: dict[str, str] = {"version": "1.1"}
    links: JSONAPILinks | None = None
    meta: JSONAPIMeta | None = None


class CandidateSingleResponse(SQLAlchemySchema):
    """JSON:API response for a single candidate."""

    data: CandidateResource
    jsonapi: dict[str, str] = {"version": "1.1"}
    links: JSONAPILinks | None = None


class SetRatingAttributes(StrictInputSchema):
    """Attributes for setting rating on a candidate via JSON:API."""

    rating: str = Field(..., min_length=1, description="The rating to set")
    rating_details: str | None = Field(None, description="Original rating value if normalized")
    auto_promote: bool = Field(
        default=False,
        description="Whether to trigger promotion if candidate is ready",
    )


class SetRatingData(BaseModel):
    """JSON:API data object for setting rating."""

    type: Literal["fact-check-candidates"] = Field(
        ..., description="Resource type must be 'fact-check-candidates'"
    )
    attributes: SetRatingAttributes


class SetRatingRequest(BaseModel):
    """JSON:API request body for setting rating on a candidate."""

    data: SetRatingData


class BulkApproveRequest(StrictInputSchema):
    """Request body for bulk approval from predicted_ratings.

    Note: This is not wrapped in JSON:API data envelope since it's an action
    endpoint that accepts filter parameters, not a resource creation.
    """

    threshold: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Predictions >= threshold get approved",
    )
    auto_promote: bool = Field(
        default=False,
        description="Whether to promote approved candidates that are ready",
    )
    status: CandidateStatus | None = Field(
        None,
        description="Filter by candidate status",
    )
    dataset_name: str | None = Field(
        None,
        description="Filter by dataset name (exact match)",
    )
    dataset_tags: list[str] | None = Field(
        None,
        description="Filter by dataset tags (array overlap)",
    )
    has_content: bool | None = Field(
        None,
        description="Filter by whether candidate has content",
    )
    published_date_from: datetime | None = Field(
        None,
        description="Filter by published_date >= this value",
    )
    published_date_to: datetime | None = Field(
        None,
        description="Filter by published_date <= this value",
    )
    limit: int = Field(
        default=200,
        ge=1,
        le=10000,
        description="Maximum number of candidates to approve (default 200)",
    )


class BulkApproveResponseMeta(BaseModel):
    """Meta object for bulk approve response."""

    updated_count: int = Field(..., description="Number of candidates updated")
    promoted_count: int | None = Field(
        None, description="Number of candidates promoted (if auto_promote=True)"
    )


class BulkApproveResponse(SQLAlchemySchema):
    """JSON:API response for bulk approval action."""

    jsonapi: dict[str, str] = {"version": "1.1"}
    meta: BulkApproveResponseMeta
    links: JSONAPILinks | None = None
