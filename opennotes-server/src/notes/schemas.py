from datetime import datetime
from enum import Enum as PyEnum
from typing import Any, Literal
from uuid import UUID

import pendulum
from pydantic import BaseModel, ConfigDict, Field, computed_field, field_serializer

from src.common.base_schemas import (
    ResponseSchema,
    SQLAlchemySchema,
    StrictInputSchema,
    TimestampSchema,
)
from src.common.jsonapi import JSONAPILinks, JSONAPIMeta


class NoteClassification(str, PyEnum):
    NOT_MISLEADING = "NOT_MISLEADING"
    MISINFORMED_OR_POTENTIALLY_MISLEADING = "MISINFORMED_OR_POTENTIALLY_MISLEADING"


class NoteStatus(str, PyEnum):
    NEEDS_MORE_RATINGS = "NEEDS_MORE_RATINGS"
    CURRENTLY_RATED_HELPFUL = "CURRENTLY_RATED_HELPFUL"
    CURRENTLY_RATED_NOT_HELPFUL = "CURRENTLY_RATED_NOT_HELPFUL"


class HelpfulnessLevel(str, PyEnum):
    HELPFUL = "HELPFUL"
    SOMEWHAT_HELPFUL = "SOMEWHAT_HELPFUL"
    NOT_HELPFUL = "NOT_HELPFUL"

    def to_score_value(self) -> float:
        """
        Convert helpfulness level to scoring value (0.0-1.0 scale).

        Used for: Community notes scoring algorithms, Bayesian averaging
        Range: 0.0 (not helpful) to 1.0 (helpful)

        Returns:
            float: Scoring value for algorithm calculations
                - HELPFUL: 1.0 (fully helpful)
                - SOMEWHAT_HELPFUL: 0.5 (moderately helpful)
                - NOT_HELPFUL: 0.0 (not helpful at all)
        """
        mapping = {
            HelpfulnessLevel.HELPFUL: 1.0,
            HelpfulnessLevel.SOMEWHAT_HELPFUL: 0.5,
            HelpfulnessLevel.NOT_HELPFUL: 0.0,
        }
        return mapping[self]

    def to_display_value(self) -> int:
        """
        Convert helpfulness level to display value (1-3 scale).

        Used for: Statistics display, average rating calculations in UI
        Range: 1 (not helpful) to 3 (helpful)

        Returns:
            int: Display value for user-facing statistics
                - HELPFUL: 3 (highest rating)
                - SOMEWHAT_HELPFUL: 2 (middle rating)
                - NOT_HELPFUL: 1 (lowest rating)
        """
        mapping = {
            HelpfulnessLevel.HELPFUL: 3,
            HelpfulnessLevel.SOMEWHAT_HELPFUL: 2,
            HelpfulnessLevel.NOT_HELPFUL: 1,
        }
        return mapping[self]


class RequestStatus(str, PyEnum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


# Note schemas
class NoteBase(BaseModel):
    author_id: UUID = Field(..., description="Author's user profile ID")
    channel_id: str | None = Field(
        None, description="Discord channel ID where the message is located"
    )
    request_id: str | None = Field(None, description="Request ID this note responds to")
    summary: str = Field(..., description="Note summary text")
    classification: NoteClassification = Field(..., description="Note classification")


class NoteCreate(NoteBase, StrictInputSchema):
    community_server_id: UUID = Field(..., description="Community server ID (required)")


class NoteUpdate(StrictInputSchema):
    summary: str | None = None
    classification: NoteClassification | None = None


class NoteInDB(NoteBase, TimestampSchema):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    community_server_id: UUID
    helpfulness_score: int
    status: NoteStatus
    force_published: bool = False
    force_published_by: UUID | None = None
    force_published_at: datetime | None = None


class RequestInfo(SQLAlchemySchema):
    """Simplified request info for embedding in note responses"""

    request_id: str
    content: str | None = None  # Content from message_archive
    requested_by: str
    requested_at: datetime


class NoteResponse(NoteInDB):
    ratings: list["RatingResponse"] = []
    request: RequestInfo | None = None

    @field_serializer("force_published_at")
    def serialize_force_published_at(self, value: datetime | None) -> str | None:
        """Serialize force_published_at to ISO 8601 format with timezone for JavaScript compatibility."""
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=pendulum.UTC)
        return value.isoformat()

    @computed_field  # type: ignore[prop-decorator]
    @property
    def ratings_count(self) -> int:
        """Compute ratings count from loaded ratings relationship."""
        return len(self.ratings)


# JSON:API Response schemas for notes
class NoteJSONAPIAttributes(SQLAlchemySchema):
    """Note attributes for JSON:API resource."""

    author_id: str
    channel_id: str | None = None
    summary: str
    classification: str
    helpfulness_score: int = 0
    status: str = "NEEDS_MORE_RATINGS"
    ai_generated: bool = False
    ai_provider: str | None = None
    force_published: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None
    request_id: str | None = None
    platform_message_id: str | None = None
    force_published_at: datetime | None = None
    ratings_count: int = 0
    community_server_id: str | None = None


class NoteResource(BaseModel):
    """JSON:API resource object for a note."""

    type: str = "notes"
    id: str
    attributes: NoteJSONAPIAttributes


class NoteListResponse(SQLAlchemySchema):
    """JSON:API response for a list of note resources."""

    data: list[NoteResource]
    jsonapi: dict[str, str] = {"version": "1.1"}
    links: JSONAPILinks | None = None
    meta: JSONAPIMeta | None = None


class NoteSingleResponse(SQLAlchemySchema):
    """JSON:API response for a single note resource."""

    data: NoteResource
    jsonapi: dict[str, str] = {"version": "1.1"}
    links: JSONAPILinks | None = None


# Rating schemas
class RatingBase(BaseModel):
    note_id: UUID = Field(..., description="Note ID to rate")
    helpfulness_level: HelpfulnessLevel = Field(..., description="Rating level")


class RatingCreate(RatingBase, StrictInputSchema):
    rater_id: UUID = Field(..., description="Rater's user profile ID")


class RatingUpdate(StrictInputSchema):
    helpfulness_level: HelpfulnessLevel


class RatingInDB(RatingBase, TimestampSchema):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    rater_id: UUID


class RatingResponse(RatingInDB):
    pass


class RatingStats(BaseModel):
    total: int
    helpful: int
    somewhat_helpful: int
    not_helpful: int
    average_score: float


# Request schemas
class RequestBase(BaseModel):
    request_id: str = Field(..., description="Unique request identifier")
    requested_by: str = Field(..., description="Requester's participant ID")


class RequestCreate(RequestBase, StrictInputSchema):
    community_server_id: str = Field(
        ..., description="Community server ID (Discord guild ID, subreddit, etc.)"
    )
    original_message_content: str | None = Field(None, description="Original message content")
    platform_message_id: str | None = Field(None, description="Platform message ID")
    platform_channel_id: str | None = Field(None, description="Platform channel ID")
    platform_author_id: str | None = Field(None, description="Platform author ID")
    platform_timestamp: datetime | None = Field(None, description="Platform message timestamp")
    metadata: dict[str, Any] | None = Field(
        None, description="Request metadata (e.g., fact-check match info)"
    )
    attachment_url: str | None = Field(
        None, description="URL of the first attachment (image, video, or file)"
    )
    attachment_type: Literal["image", "video", "file"] | None = Field(
        None, description="Type of attachment"
    )
    attachment_metadata: dict[str, Any] | None = Field(
        None, description="Attachment metadata (width, height, size, filename)"
    )
    embedded_image_url: str | None = Field(
        None, description="URL of embedded image (from Discord embeds or text links)"
    )


class RequestUpdate(StrictInputSchema):
    status: RequestStatus | None = None
    note_id: UUID | None = None


class RequestInDB(RequestBase, TimestampSchema):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    community_server_id: UUID = Field(..., description="Community server ID")
    requested_at: datetime
    status: RequestStatus
    note_id: UUID | None = None


class RequestResponse(RequestInDB):
    content: str | None = Field(None, description="Message content from archive or legacy field")
    platform_message_id: str | None = Field(
        None, description="Platform message ID from message archive"
    )
    request_metadata: dict[str, Any] | None = Field(
        None,
        serialization_alias="metadata",
        description="Request metadata (e.g., fact-check match info)",
    )

    @field_serializer("requested_at")
    def serialize_requested_at(self, value: datetime) -> str:
        """Serialize requested_at to ISO 8601 format with timezone for JavaScript compatibility."""
        # Ensure datetime is timezone-aware (assume UTC if naive)
        if value.tzinfo is None:
            value = value.replace(tzinfo=pendulum.UTC)
        return value.isoformat()


class RequestListResponse(ResponseSchema):
    model_config = ConfigDict(extra="forbid")

    requests: list[RequestResponse]
    total: int
    page: int
    size: int


# Aggregation schemas
class NoteSummaryStats(BaseModel):
    total_notes: int
    helpful_notes: int
    not_helpful_notes: int
    pending_notes: int
    average_helpfulness_score: float


class ParticipantStats(BaseModel):
    participant_id: str
    notes_created: int
    ratings_given: int
    average_helpfulness_received: float
    top_classification: NoteClassification | None = None
