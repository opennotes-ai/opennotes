"""Pydantic schemas for Bulk Content Scan API endpoints."""

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import Discriminator, Field, field_validator

from src.claim_relevance_check.schemas import RelevanceCheckResult, RelevanceOutcome
from src.common.base_schemas import SQLAlchemySchema, StrictInputSchema

__all__ = ["RelevanceCheckResult", "RelevanceOutcome"]


class BulkScanStatus(StrEnum):
    """Status values for a bulk content scan."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class RiskLevel(StrEnum):
    """Categorical risk level for conversation flashpoint detection."""

    LOW_RISK = "Low Risk"
    GUARDED = "Guarded"
    HEATED = "Heated"
    HOSTILE = "Hostile"
    DANGEROUS = "Dangerous"


class BulkScanMessage(StrictInputSchema):
    """Schema for a message to be scanned in bulk content scanning."""

    message_id: str = Field(..., description="Discord message ID")
    channel_id: str = Field(..., description="Discord channel ID")
    community_server_id: str = Field(
        ..., description="Community server ID (platform-agnostic identifier)"
    )
    content: str = Field(..., description="Message text content")
    author_id: str = Field(..., description="Discord author ID")
    author_username: str | None = Field(None, description="Discord author username")
    timestamp: datetime = Field(..., description="When the message was posted")
    attachment_urls: list[str] | None = Field(None, description="URLs of message attachments")
    embed_content: str | None = Field(None, description="Extracted text from message embeds")


class ContentItem(StrictInputSchema):
    """Platform-agnostic content item for the content reviewer agent.

    Replaces BulkScanMessage at service boundaries. Each platform adapter
    maps its native event to this schema, with platform-specific metadata
    preserved in the platform_metadata bag.
    """

    content_id: str = Field(..., description="Platform-specific content identifier")
    platform: str = Field(..., description="Source platform (discord, discourse, etc.)")
    content_text: str = Field(..., description="Text content to be reviewed")
    author_id: str = Field(..., description="Platform-specific author identifier")
    author_username: str | None = Field(None, description="Author display name")
    timestamp: datetime = Field(..., description="When the content was posted")
    channel_id: str = Field(..., description="Platform-specific channel/topic identifier")
    community_server_id: str = Field(
        ..., description="Community server ID (platform-agnostic identifier)"
    )
    attachment_urls: list[str] | None = Field(None, description="URLs of content attachments")
    platform_metadata: dict[str, Any] = Field(
        default_factory=dict, description="Platform-specific metadata bag"
    )


def bulk_scan_message_to_content_item(msg: "BulkScanMessage") -> "ContentItem":
    """Convert a Discord BulkScanMessage to a platform-agnostic ContentItem.

    Discord-specific fields (embed_content) are preserved in platform_metadata.
    """
    return ContentItem(
        content_id=msg.message_id,
        platform="discord",
        content_text=msg.content,
        author_id=msg.author_id,
        author_username=msg.author_username,
        timestamp=msg.timestamp,
        channel_id=msg.channel_id,
        community_server_id=msg.community_server_id,
        attachment_urls=msg.attachment_urls,
        platform_metadata={
            "embed_content": msg.embed_content,
        },
    )


class BulkScanCreateRequest(StrictInputSchema):
    """Request schema for initiating a new bulk content scan."""

    community_server_id: UUID = Field(..., description="Community server UUID to scan")
    scan_window_days: int = Field(
        ...,
        ge=1,
        le=30,
        description="Number of days of message history to scan (1-30)",
    )
    channel_ids: list[str] = Field(
        default_factory=list,
        description="Specific channel IDs to scan (empty = all channels)",
    )


class BulkScanResponse(SQLAlchemySchema):
    """Response schema for scan status and metadata."""

    scan_id: UUID = Field(..., description="Unique scan identifier")
    status: str = Field(..., description="Current scan status")
    initiated_at: datetime = Field(..., description="When the scan was initiated")
    completed_at: datetime | None = Field(
        None, description="When the scan completed (null if in progress)"
    )
    messages_scanned: int = Field(default=0, description="Total messages scanned")
    messages_flagged: int = Field(default=0, description="Number of messages flagged")


class SimilarityMatch(StrictInputSchema):
    """Match result from similarity scan."""

    scan_type: Literal["similarity"] = "similarity"
    score: float = Field(..., ge=0.0, le=1.0, description="Similarity score")
    matched_claim: str = Field(..., description="Fact-check claim that matched")
    matched_source: str = Field(..., description="URL to the fact-check source")
    # TODO: Make required (remove None/default) once old scans without this field are flushed from Redis
    fact_check_item_id: UUID | None = Field(
        default=None, description="UUID of the matched FactCheckItem"
    )


class OpenAIModerationMatch(StrictInputSchema):
    """Match result from OpenAI moderation scan."""

    scan_type: Literal["openai_moderation"] = "openai_moderation"
    max_score: float = Field(..., ge=0.0, le=1.0, description="Max moderation score")
    categories: dict[str, bool] = Field(..., description="Moderation categories")
    scores: dict[str, float] = Field(..., description="Category scores")
    flagged_categories: list[str] = Field(
        default_factory=list, description="Flagged category names"
    )


class ConversationFlashpointMatch(StrictInputSchema):
    """Match result from conversation flashpoint detection scan."""

    scan_type: Literal["conversation_flashpoint"] = "conversation_flashpoint"
    derailment_score: int = Field(..., ge=0, le=100, description="Derailment risk score (0-100)")
    risk_level: RiskLevel = Field(..., description="Categorical risk assessment level")
    reasoning: str = Field(..., description="Explanation of detected escalation signals")
    context_messages: int = Field(..., ge=0, description="Number of context messages analyzed")


class ContentModerationClassificationResult(StrictInputSchema):
    """Structured output from the ContentReviewerAgent.

    Contains the agent's classification decision: confidence, category labels,
    recommended action, action tier, and explanation. Added to MatchResult
    union alongside existing match types.
    """

    scan_type: Literal["content_moderation_classification"] = "content_moderation_classification"
    confidence: float = Field(..., ge=0.0, le=1.0, description="Classification confidence score")
    category_labels: dict[str, bool] = Field(
        ..., description="Category labels with flagged/not-flagged status"
    )
    category_scores: dict[str, float] | None = Field(
        None, description="Per-category confidence scores"
    )
    recommended_action: Literal["hide", "review", "pass"] | None = Field(
        None, description="Recommended action (hide, review, pass)"
    )
    action_tier: Literal["tier_1_immediate", "tier_2_consensus"] | None = Field(
        None, description="Action tier (tier_1_immediate, tier_2_consensus)"
    )
    explanation: str = Field(..., description="Human-readable explanation of the classification")
    error_type: str | None = Field(
        default=None,
        description=(
            "None for normal classification; "
            "'timeout', 'transport_error', 'parse_error', or 'unexpected_error' for failures"
        ),
    )


MatchResult = Annotated[
    SimilarityMatch
    | OpenAIModerationMatch
    | ConversationFlashpointMatch
    | ContentModerationClassificationResult,
    Discriminator("scan_type"),
]


class ScanCandidate(StrictInputSchema):
    """Internal schema for a scan candidate before relevance filtering.

    This is an internal-only schema (not API-facing) used to collect candidates
    from all scan types before applying the unified LLM relevance check.

    Task-953: All scan paths produce candidates, then ALL candidates pass through
    the LLM relevance check as a unified final filter before being marked as flagged.
    """

    message: "BulkScanMessage" = Field(..., description="The original message being scanned")
    scan_type: str = Field(..., description="Type of scan that produced this candidate")
    match_data: MatchResult = Field(..., description="Match result from the scan")
    score: float = Field(..., ge=0.0, le=1.0, description="Match score")
    matched_content: str = Field(..., description="Content to use for relevance check")
    matched_source: str | None = Field(None, description="Source URL if available")


class FlaggedMessage(SQLAlchemySchema):
    """Schema for a single flagged message in scan results."""

    message_id: str = Field(..., description="Discord message ID")
    channel_id: str = Field(..., description="Discord channel ID")
    content: str = Field(..., description="Original message content")
    author_id: str = Field(..., description="Discord author ID")
    timestamp: datetime = Field(..., description="When the message was posted")
    matches: list[MatchResult] = Field(
        default_factory=list,
        description="List of match results from scans (each includes its scan_type)",
    )


class BulkScanResultsResponse(SQLAlchemySchema):
    """Response schema for scan results including flagged messages with pagination."""

    scan_id: UUID = Field(..., description="Scan identifier")
    status: str = Field(..., description="Current scan status")
    messages_scanned: int = Field(..., description="Total messages processed")
    flagged_messages: list[FlaggedMessage] = Field(
        default_factory=list,
        description="List of flagged messages with match info (paginated)",
    )
    total: int = Field(
        default=0,
        ge=0,
        description="Total number of flagged messages across all pages",
    )
    page: int = Field(
        default=1,
        ge=1,
        description="Current page number (1-indexed)",
    )
    page_size: int = Field(
        default=50,
        ge=1,
        le=100,
        description="Number of results per page",
    )


class CreateNoteRequestsRequest(StrictInputSchema):
    """Request schema for creating note requests from flagged messages."""

    message_ids: list[str] = Field(
        ...,
        min_length=1,
        description="Message IDs to create note requests for",
    )
    generate_ai_notes: bool = Field(
        default=False,
        description="Whether to generate AI-written draft notes",
    )

    @field_validator("message_ids")
    @classmethod
    def validate_message_ids(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("At least one message ID must be provided")
        return v


class NoteRequestsResponse(SQLAlchemySchema):
    """Response schema for note request creation results."""

    created_count: int = Field(..., description="Number of note requests created")
    request_ids: list[str] = Field(
        default_factory=list,
        description="IDs of created note requests",
    )


class LatestScanResponse(SQLAlchemySchema):
    """Response schema for the latest scan for a community server.

    Includes full scan details: status, counts, timestamps, and flagged messages
    if the scan is completed.
    """

    scan_id: UUID = Field(..., description="Unique scan identifier")
    status: str = Field(
        ..., description="Current scan status (pending, in_progress, completed, failed)"
    )
    initiated_at: datetime = Field(..., description="When the scan was initiated")
    completed_at: datetime | None = Field(
        None, description="When the scan completed (null if in progress or pending)"
    )
    messages_scanned: int = Field(default=0, description="Total messages scanned")
    messages_flagged: int = Field(default=0, description="Number of messages flagged")
    flagged_messages: list[FlaggedMessage] = Field(
        default_factory=list,
        description="List of flagged messages with match info (only populated for completed scans)",
    )
