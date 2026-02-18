"""Pydantic schemas for Claim Relevance Check API endpoints."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.common.base_schemas import StrictInputSchema


class RelevanceOutcome(StrEnum):
    """Outcome of LLM relevance check for content filtering.

    Used to distinguish between different reasons why a relevance check
    may succeed, fail, or be indeterminate due to content filtering.
    """

    RELEVANT = "relevant"
    NOT_RELEVANT = "not_relevant"
    INDETERMINATE = "indeterminate"
    CONTENT_FILTERED = "content_filtered"


class RelevanceCheckResult(StrictInputSchema):
    """Result from LLM relevance check for hybrid search matches."""

    is_relevant: bool = Field(..., description="Whether the match is semantically relevant")
    reasoning: str = Field(..., description="LLM's reasoning for the relevance decision")
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Model's confidence in the relevance decision (0.0-1.0)",
    )


class ClaimRelevanceCheckAttributes(StrictInputSchema):
    """Attributes for performing a claim relevance check via JSON:API."""

    original_message: str = Field(
        ...,
        min_length=1,
        max_length=50000,
        description="The user's original message to check for claims",
    )
    matched_content: str = Field(
        ...,
        min_length=1,
        max_length=50000,
        description="The matched fact-check content",
    )
    matched_source: str = Field(
        ...,
        max_length=2048,
        description="URL to the fact-check source",
    )
    similarity_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Cosine similarity score of the match",
    )


class ClaimRelevanceCheckCreateData(BaseModel):
    """JSON:API data object for claim relevance check."""

    type: Literal["claim-relevance-checks"] = Field(
        ..., description="Resource type must be 'claim-relevance-checks'"
    )
    attributes: ClaimRelevanceCheckAttributes


class ClaimRelevanceCheckRequest(BaseModel):
    """JSON:API request body for performing a claim relevance check."""

    data: ClaimRelevanceCheckCreateData


class ClaimRelevanceCheckResultAttributes(BaseModel):
    """Attributes for claim relevance check result."""

    model_config = ConfigDict(from_attributes=True)

    outcome: str = Field(
        ...,
        description="Relevance check outcome: relevant, not_relevant, indeterminate, or content_filtered",
    )
    reasoning: str = Field(..., description="Explanation of the relevance decision")
    should_flag: bool = Field(
        ...,
        description="Whether the message should be flagged (true for relevant or indeterminate outcomes)",
    )


class ClaimRelevanceCheckResultResource(BaseModel):
    """JSON:API resource object for claim relevance check results."""

    type: str = "claim-relevance-checks"
    id: str
    attributes: ClaimRelevanceCheckResultAttributes


class ClaimRelevanceCheckResponse(BaseModel):
    """JSON:API response for claim relevance check results."""

    model_config = ConfigDict(from_attributes=True)

    data: ClaimRelevanceCheckResultResource
    jsonapi: dict[str, str] = {"version": "1.1"}
