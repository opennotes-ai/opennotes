from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.common.base_schemas import ResponseSchema, SQLAlchemySchema, StrictInputSchema
from src.config import settings


class MonitoredChannelBase(BaseModel):
    """Base schema for monitored channel configuration."""

    community_server_id: str = Field(..., description="Discord server/guild ID", max_length=64)
    channel_id: str = Field(..., description="Discord channel ID", max_length=64)
    name: str | None = Field(None, description="Human-readable channel name", max_length=255)
    enabled: bool = Field(True, description="Whether monitoring is active")
    similarity_threshold: float = Field(
        default_factory=lambda: settings.SIMILARITY_SEARCH_DEFAULT_THRESHOLD,
        description="Minimum similarity score (0.0-1.0) for fact-check matches",
        ge=0.0,
        le=1.0,
    )
    dataset_tags: list[str] = Field(
        default_factory=lambda: ["snopes"],
        description="Dataset tags to check against (e.g., ['snopes', 'politifact'])",
    )
    previously_seen_autopublish_threshold: float | None = Field(
        None,
        description="Per-channel override for auto-publish threshold (NULL = use global config default)",
        ge=0.0,
        le=1.0,
    )
    previously_seen_autorequest_threshold: float | None = Field(
        None,
        description="Per-channel override for auto-request threshold (NULL = use global config default)",
        ge=0.0,
        le=1.0,
    )


class MonitoredChannelCreate(MonitoredChannelBase, StrictInputSchema):
    """Schema for creating a monitored channel configuration."""

    updated_by: str | None = Field(None, description="Discord user ID of admin creating config")


class MonitoredChannelUpdate(StrictInputSchema):
    """Schema for updating a monitored channel configuration."""

    name: str | None = Field(None, description="Human-readable channel name", max_length=255)
    enabled: bool | None = Field(None, description="Whether monitoring is active")
    similarity_threshold: float | None = Field(
        None,
        description="Minimum similarity score (0.0-1.0) for fact-check matches",
        ge=0.0,
        le=1.0,
    )
    dataset_tags: list[str] | None = Field(
        None, description="Dataset tags to check against (e.g., ['snopes', 'politifact'])"
    )
    previously_seen_autopublish_threshold: float | None = Field(
        None,
        description="Per-channel override for auto-publish threshold (NULL = use global config default)",
        ge=0.0,
        le=1.0,
    )
    previously_seen_autorequest_threshold: float | None = Field(
        None,
        description="Per-channel override for auto-request threshold (NULL = use global config default)",
        ge=0.0,
        le=1.0,
    )
    updated_by: str | None = Field(None, description="Discord user ID of admin updating config")


class MonitoredChannelResponse(MonitoredChannelBase, SQLAlchemySchema):
    """Schema for monitored channel configuration responses."""

    id: UUID = Field(..., description="Unique identifier")
    created_at: datetime = Field(..., description="When monitoring was configured")
    updated_at: datetime = Field(..., description="Last configuration update")
    updated_by: str | None = Field(None, description="Discord user ID of last admin to update")


class MonitoredChannelListResponse(ResponseSchema):
    """Schema for paginated list of monitored channels."""

    model_config = ConfigDict(extra="forbid")

    channels: list[MonitoredChannelResponse] = Field(..., description="List of monitored channels")
    total: int = Field(..., description="Total count of channels")
    page: int = Field(1, description="Current page number", ge=1)
    size: int = Field(20, description="Items per page", ge=1, le=100)
