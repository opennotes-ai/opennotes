from datetime import UTC, datetime
from enum import Enum
from typing import Any, Literal, TypedDict
from uuid import UUID

from pydantic import Field, field_validator

from src.bulk_content_scan.schemas import BulkScanMessage, FlaggedMessage
from src.common.base_schemas import StrictEventSchema


class NoteMetadata(TypedDict, total=False):
    """Common metadata fields for note-related events.

    Attributes:
        source: Source platform (e.g., 'discord', 'web', 'api')
        language: Language code (e.g., 'en', 'es', 'fr')
        tags: List of tags associated with the note
        community_server_name: Name of the community server
        channel_name: Name of the channel
    """

    source: str
    language: str
    tags: list[str]
    community_server_name: str
    channel_name: str


class UserMetadata(TypedDict, total=False):
    """Common metadata fields for user-related events.

    Attributes:
        registration_ip: IP address at registration
        referral_code: Referral code used
        oauth_provider: OAuth provider (e.g., 'discord', 'google')
        timezone: User timezone
    """

    registration_ip: str
    referral_code: str
    oauth_provider: str
    timezone: str


class AuditMetadata(TypedDict, total=False):
    """Common metadata fields for audit log events.

    Attributes:
        request_id: Unique request identifier
        session_id: Session identifier
        api_version: API version used
        response_code: HTTP response code
    """

    request_id: str
    session_id: str
    api_version: str
    response_code: int


class EventType(str, Enum):
    NOTE_CREATED = "note.created"
    NOTE_RATED = "note.rated"
    NOTE_SCORE_UPDATED = "note.score.updated"
    NOTE_REQUEST_CREATED = "note.request.created"
    REQUEST_AUTO_CREATED = "request.auto_created"
    VISION_DESCRIPTION_REQUESTED = "vision.description.requested"
    USER_REGISTERED = "user.registered"
    WEBHOOK_RECEIVED = "webhook.received"
    AUDIT_LOG_CREATED = "audit.log.created"
    BULK_SCAN_INITIATED = "bulk_scan.initiated"
    BULK_SCAN_MESSAGE_BATCH = "bulk_scan.message_batch"
    BULK_SCAN_ALL_BATCHES_TRANSMITTED = "bulk_scan.all_batches_transmitted"
    BULK_SCAN_PROCESSING_FINISHED = "bulk_scan.processing_finished"
    BULK_SCAN_RESULTS = "bulk_scan.results"
    BULK_SCAN_PROGRESS = "bulk_scan.progress"
    BULK_SCAN_FAILED = "bulk_scan.failed"


class BaseEvent(StrictEventSchema):
    event_id: str = Field(..., description="Unique event identifier")
    event_type: EventType = Field(..., description="Type of event")
    version: str = Field(default="1.0", description="Event schema version")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Event timestamp"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata. See NoteMetadata, UserMetadata, or AuditMetadata for common fields.",
    )


class NoteCreatedEvent(BaseEvent):
    event_type: EventType = EventType.NOTE_CREATED
    note_id: UUID = Field(..., description="Unique note identifier")
    author_id: str = Field(
        ..., min_length=1, max_length=255, description="Note author participant ID"
    )
    platform_message_id: str | None = Field(
        None, max_length=255, description="Platform message ID from message archive"
    )
    summary: str = Field(..., min_length=1, max_length=5000, description="Note summary text")
    classification: Literal[
        "NOT_MISLEADING",
        "MISINFORMED_OR_POTENTIALLY_MISLEADING",
    ] = Field(..., description="Note classification")

    @field_validator("summary")
    @classmethod
    def validate_summary(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Summary cannot be empty or whitespace only")
        return v.strip()


class NoteRatedEvent(BaseEvent):
    event_type: EventType = EventType.NOTE_RATED
    note_id: UUID = Field(..., description="Note being rated")
    rater_id: str = Field(..., min_length=1, max_length=255, description="Rater participant ID")
    helpfulness_level: Literal["HELPFUL", "SOMEWHAT_HELPFUL", "NOT_HELPFUL"] = Field(
        ..., description="Helpfulness rating"
    )


class UserRegisteredEvent(BaseEvent):
    event_type: EventType = EventType.USER_REGISTERED
    user_id: UUID = Field(..., description="New user ID")
    username: str = Field(..., min_length=1, max_length=255, description="Username")
    email: str | None = Field(None, max_length=320, description="User email")
    registration_source: str = Field(
        ..., min_length=1, max_length=50, description="Registration source (e.g., 'discord', 'web')"
    )


class WebhookReceivedEvent(BaseEvent):
    event_type: EventType = EventType.WEBHOOK_RECEIVED
    webhook_id: str = Field(..., min_length=1, max_length=255, description="Webhook interaction ID")
    community_server_id: str | None = Field(
        None, max_length=255, description="Community server ID (Discord guild ID, subreddit, etc.)"
    )
    channel_id: str | None = Field(None, max_length=255, description="Channel ID")
    user_id: str = Field(..., min_length=1, max_length=255, description="User ID")
    interaction_type: int = Field(..., ge=0, description="Interaction type")
    command_name: str | None = Field(None, max_length=255, description="Command name if applicable")


class NoteScoreUpdatedEvent(BaseEvent):
    event_type: EventType = EventType.NOTE_SCORE_UPDATED
    note_id: UUID = Field(..., description="Note ID")
    score: float = Field(..., ge=0.0, le=1.0, description="Calculated score (0.0-1.0)")
    confidence: Literal["no_data", "provisional", "standard"] = Field(
        ..., description="Confidence level"
    )
    algorithm: str = Field(
        ..., min_length=1, max_length=100, description="Algorithm used for scoring"
    )
    rating_count: int = Field(..., ge=0, description="Number of ratings used")
    tier: int = Field(..., ge=1, description="Scoring tier level")
    tier_name: str = Field(..., min_length=1, max_length=100, description="Scoring tier name")
    original_message_id: str | None = Field(
        None, max_length=255, description="Message ID where note was created"
    )
    channel_id: str | None = Field(None, max_length=255, description="Channel ID")
    community_server_id: str | None = Field(
        None, max_length=255, description="Community server ID (Discord guild ID, subreddit, etc.)"
    )


class NoteRequestCreatedEvent(BaseEvent):
    event_type: EventType = EventType.NOTE_REQUEST_CREATED
    request_id: str = Field(..., min_length=1, max_length=255, description="Note request ID")
    platform_message_id: str | None = Field(
        None, max_length=255, description="Platform message ID from message archive"
    )
    requested_by: str = Field(
        ..., min_length=1, max_length=255, description="Requester participant ID"
    )
    status: str = Field(..., min_length=1, max_length=50, description="Request status")
    priority: str | None = Field(None, min_length=1, max_length=50, description="Request priority")
    similarity_score: float | None = Field(
        None, ge=0.0, le=1.0, description="Match similarity score if auto-generated"
    )
    dataset_name: str | None = Field(
        None, max_length=100, description="Matched dataset name if auto-generated"
    )
    dataset_item_id: str | None = Field(
        None,
        min_length=1,
        max_length=36,
        description="Matched dataset item ID (UUID) if auto-generated",
    )


class RequestAutoCreatedEvent(BaseEvent):
    event_type: EventType = EventType.REQUEST_AUTO_CREATED
    request_id: str = Field(..., min_length=1, max_length=255, description="Note request ID")
    platform_message_id: str | None = Field(
        None, max_length=255, description="Platform message ID from message archive"
    )
    scan_type: Literal["similarity", "openai_moderation"] = Field(
        ..., description="Type of scan that triggered this event"
    )
    fact_check_item_id: str | None = Field(
        None, min_length=1, max_length=36, description="Matched fact-check item ID (UUID)"
    )
    community_server_id: str = Field(
        ..., min_length=1, max_length=255, description="Community server ID"
    )
    content: str = Field(
        ..., min_length=1, max_length=10000, description="Message content from archive"
    )
    similarity_score: float | None = Field(
        None, ge=0.0, le=1.0, description="Match similarity score (for similarity scans)"
    )
    dataset_name: str | None = Field(
        None, min_length=1, max_length=100, description="Dataset name (for similarity scans)"
    )
    moderation_metadata: dict[str, Any] | None = Field(
        None, description="OpenAI moderation results (for moderation scans)"
    )


class VisionDescriptionRequestedEvent(BaseEvent):
    event_type: EventType = EventType.VISION_DESCRIPTION_REQUESTED
    message_archive_id: str = Field(
        ..., min_length=1, max_length=36, description="Message archive UUID"
    )
    image_url: str = Field(..., min_length=1, max_length=2048, description="Image URL to process")
    community_server_id: str = Field(
        ..., min_length=1, max_length=255, description="Community server ID for API key lookup"
    )
    request_id: str | None = Field(
        None, min_length=1, max_length=255, description="Associated note request ID if applicable"
    )


class AuditLogCreatedEvent(BaseEvent):
    event_type: EventType = EventType.AUDIT_LOG_CREATED
    user_id: UUID | None = Field(None, description="User ID who performed the action")
    action: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Action performed (e.g., 'POST /api/v1/notes')",
    )
    resource: str = Field(..., min_length=1, max_length=255, description="Resource affected")
    resource_id: str | None = Field(None, max_length=255, description="Resource ID if applicable")
    details: str | None = Field(
        None, max_length=5000, description="Additional details about the action"
    )
    ip_address: str | None = Field(None, max_length=45, description="IP address of the client")
    user_agent: str | None = Field(None, max_length=1000, description="User agent of the client")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="When the action occurred"
    )


class BulkScanInitiatedEvent(BaseEvent):
    """Event published when a bulk content scan is initiated by a user."""

    event_type: EventType = EventType.BULK_SCAN_INITIATED
    scan_id: UUID = Field(..., description="Unique scan identifier")
    community_server_id: UUID = Field(..., description="Community server being scanned")
    initiated_by_user_id: UUID = Field(..., description="User who initiated the scan")
    scan_window_days: int = Field(..., ge=1, le=30, description="Number of days to scan back")
    channel_ids: list[str] = Field(
        default_factory=list, description="Specific channel IDs to scan (empty = all channels)"
    )


class BulkScanMessageBatchEvent(BaseEvent):
    """Event published with a batch of messages for bulk scan processing."""

    event_type: EventType = EventType.BULK_SCAN_MESSAGE_BATCH
    scan_id: UUID = Field(..., description="Scan this batch belongs to")
    community_server_id: UUID = Field(
        ..., description="Community server UUID (needed for platform_id lookup)"
    )
    messages: list[BulkScanMessage] = Field(
        ...,
        description="Batch of messages to scan",
    )
    batch_number: int = Field(..., ge=1, description="Batch sequence number")
    is_final_batch: bool = Field(default=False, description="Whether this is the last batch")


class BulkScanAllBatchesTransmittedEvent(BaseEvent):
    """Event published when Discord bot has transmitted all message batches.

    This event signals that the bot has finished sending all batches to the server.
    It does NOT mean processing is complete - batches may still be processing.
    The server uses this to set a flag and potentially trigger completion
    if all batches have already been processed.
    """

    event_type: EventType = EventType.BULK_SCAN_ALL_BATCHES_TRANSMITTED
    scan_id: UUID = Field(..., description="Scan identifier")
    community_server_id: UUID = Field(..., description="Community server that was scanned")
    messages_scanned: int = Field(..., ge=0, description="Total messages transmitted")


class BulkScanProcessingFinishedEvent(BaseEvent):
    """Event published when server has finished processing all batches.

    This event is published by the server after scan completion is finalized.
    The Discord bot subscribes to this to know when results are ready.
    """

    event_type: EventType = EventType.BULK_SCAN_PROCESSING_FINISHED
    scan_id: UUID = Field(..., description="Completed scan identifier")
    community_server_id: UUID = Field(..., description="Community server that was scanned")
    messages_scanned: int = Field(..., ge=0, description="Total messages processed")
    messages_flagged: int = Field(..., ge=0, description="Number of flagged messages")


class ScanErrorInfo(StrictEventSchema):
    """Error information from a failed message scan."""

    error_type: str = Field(..., description="Type of error (e.g., 'TypeError', 'ValueError')")
    message_id: str | None = Field(None, description="Message ID that caused the error")
    batch_number: int | None = Field(None, description="Batch number where error occurred")
    error_message: str = Field(..., description="Error message details")


class ScanErrorSummary(StrictEventSchema):
    """Summary of errors encountered during a bulk scan."""

    total_errors: int = Field(default=0, ge=0, description="Total number of errors")
    error_types: dict[str, int] = Field(
        default_factory=dict,
        description="Count of errors by type (e.g., {'TypeError': 5, 'ValueError': 2})",
    )
    sample_errors: list[ScanErrorInfo] = Field(
        default_factory=list,
        description="Sample of error messages (up to 5)",
    )


class BulkScanResultsEvent(BaseEvent):
    """Event published with scan results after processing is complete."""

    event_type: EventType = EventType.BULK_SCAN_RESULTS
    scan_id: UUID = Field(..., description="Scan results belong to")
    messages_scanned: int = Field(..., ge=0, description="Total messages processed")
    messages_flagged: int = Field(..., ge=0, description="Number of messages flagged")
    flagged_messages: list[FlaggedMessage] = Field(
        default_factory=list,
        description="Flagged messages with match info",
    )
    error_summary: ScanErrorSummary | None = Field(
        default=None,
        description="Summary of errors encountered during scan (if any)",
    )


class MessageScoreInfo(StrictEventSchema):
    """Score information for a single message during vibecheck debug mode."""

    message_id: str = Field(..., description="Discord message ID")
    channel_id: str = Field(..., description="Discord channel ID")
    similarity_score: float = Field(
        ..., ge=0.0, le=1.0, description="Similarity score from embedding search"
    )
    threshold: float = Field(..., ge=0.0, le=1.0, description="Threshold used for flagging")
    is_flagged: bool = Field(..., description="Whether message exceeded threshold")
    matched_claim: str | None = Field(None, description="Matched claim text if flagged")
    moderation_flagged: bool | None = Field(
        None, description="Whether OpenAI moderation flagged the message"
    )
    moderation_categories: dict[str, bool] | None = Field(
        None, description="OpenAI moderation category flags (e.g., {'violence': true})"
    )
    moderation_scores: dict[str, float] | None = Field(
        None, description="OpenAI moderation category scores (0.0-1.0)"
    )


class BulkScanProgressEvent(BaseEvent):
    """Event published with progress during bulk scan processing.

    This event is published after each batch of messages is processed.
    In debug mode, it includes detailed similarity scores for ALL messages.
    In normal mode, it includes summary progress information.
    """

    event_type: EventType = EventType.BULK_SCAN_PROGRESS
    scan_id: UUID = Field(..., description="Scan this progress belongs to")
    community_server_id: UUID = Field(..., description="Community server being scanned")
    platform_community_server_id: str = Field(
        ..., description="Platform ID (e.g., Discord guild ID)"
    )
    batch_number: int = Field(..., ge=1, description="Batch sequence number")
    messages_in_batch: int = Field(..., ge=0, description="Number of messages in this batch")
    messages_processed: int = Field(
        default=0, ge=0, description="Total messages processed so far in this scan"
    )
    channel_ids: list[str] = Field(
        default_factory=list, description="Channel IDs being processed in this batch"
    )
    message_scores: list[MessageScoreInfo] = Field(
        default_factory=list,
        description="Score info for each message in the batch (debug mode only)",
    )
    threshold_used: float = Field(..., ge=0.0, le=1.0, description="Threshold used for flagging")


class BulkScanFailedEvent(BaseEvent):
    """Event published when a bulk scan fails due to critical errors.

    This event is published by the server when a scan encounters unrecoverable
    errors that prevent completion. The Discord bot subscribes to this to
    immediately notify users of failures.
    """

    event_type: EventType = EventType.BULK_SCAN_FAILED
    scan_id: UUID = Field(..., description="Failed scan identifier")
    community_server_id: UUID = Field(..., description="Community server that was being scanned")
    error_message: str = Field(
        ..., min_length=1, max_length=5000, description="Error message describing the failure"
    )


EventUnion = (
    NoteCreatedEvent
    | NoteRatedEvent
    | NoteScoreUpdatedEvent
    | NoteRequestCreatedEvent
    | RequestAutoCreatedEvent
    | VisionDescriptionRequestedEvent
    | UserRegisteredEvent
    | WebhookReceivedEvent
    | AuditLogCreatedEvent
    | BulkScanInitiatedEvent
    | BulkScanMessageBatchEvent
    | BulkScanAllBatchesTransmittedEvent
    | BulkScanProcessingFinishedEvent
    | BulkScanResultsEvent
    | BulkScanProgressEvent
    | BulkScanFailedEvent
)
