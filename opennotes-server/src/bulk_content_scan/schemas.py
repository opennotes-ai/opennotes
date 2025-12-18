"""Pydantic schemas for Bulk Content Scan API endpoints."""

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import ConfigDict, Field, field_validator

from src.bulk_content_scan.scan_types import ScanType
from src.common.base_schemas import SQLAlchemySchema, StrictInputSchema


class BulkScanStatus(str, Enum):
    """Status values for a bulk content scan."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


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

    model_config = ConfigDict(from_attributes=True)

    scan_id: UUID = Field(..., description="Unique scan identifier")
    status: str = Field(..., description="Current scan status")
    initiated_at: datetime = Field(..., description="When the scan was initiated")
    completed_at: datetime | None = Field(
        None, description="When the scan completed (null if in progress)"
    )
    messages_scanned: int = Field(default=0, description="Total messages scanned")
    messages_flagged: int = Field(default=0, description="Number of messages flagged")


class FlaggedMessage(SQLAlchemySchema):
    """Schema for a single flagged message in scan results."""

    model_config = ConfigDict(from_attributes=True)

    message_id: str = Field(..., description="Discord message ID")
    channel_id: str = Field(..., description="Discord channel ID")
    content: str = Field(..., description="Original message content")
    author_id: str = Field(..., description="Discord author ID")
    timestamp: datetime = Field(..., description="When the message was posted")
    match_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Similarity score (0.0-1.0)",
    )
    matched_claim: str = Field(..., description="Fact-check claim that matched")
    matched_source: str = Field(..., description="URL to the fact-check source")
    scan_type: ScanType = Field(
        default=ScanType.SIMILARITY,
        description="Type of scan that flagged this message",
    )


class BulkScanResultsResponse(SQLAlchemySchema):
    """Response schema for scan results including flagged messages with pagination."""

    model_config = ConfigDict(from_attributes=True)

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

    model_config = ConfigDict(from_attributes=True)

    created_count: int = Field(..., description="Number of note requests created")
    request_ids: list[str] = Field(
        default_factory=list,
        description="IDs of created note requests",
    )
