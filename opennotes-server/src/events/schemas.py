from datetime import UTC, datetime
from enum import Enum
from typing import Any, Literal, TypedDict
from uuid import UUID

from pydantic import Field, field_validator

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
    fact_check_item_id: str = Field(
        ..., min_length=1, max_length=36, description="Matched fact-check item ID (UUID)"
    )
    community_server_id: str = Field(
        ..., min_length=1, max_length=255, description="Community server ID"
    )
    content: str = Field(
        ..., min_length=1, max_length=10000, description="Message content from archive"
    )
    similarity_score: float = Field(..., ge=0.0, le=1.0, description="Match similarity score")
    dataset_name: str = Field(..., min_length=1, max_length=100, description="Dataset name")


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
)
