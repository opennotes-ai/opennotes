"""
Pydantic schemas for rechunk background task status tracking.

These schemas define the data structures for tracking the progress and status
of rechunk operations, enabling clients to poll for completion.
"""

from datetime import UTC, datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer


class RechunkTaskStatus(str, Enum):
    """Status states for a rechunk task."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class RechunkTaskType(str, Enum):
    """Type of rechunk operation."""

    FACT_CHECK = "fact_check"
    PREVIOUSLY_SEEN = "previously_seen"


class RechunkTaskBase(BaseModel):
    """Base schema for rechunk task status."""

    model_config = ConfigDict(use_enum_values=True)

    task_type: RechunkTaskType = Field(
        ..., description="Type of rechunk operation (fact_check or previously_seen)"
    )
    community_server_id: UUID = Field(..., description="Community server ID for the operation")
    batch_size: int = Field(..., ge=1, le=1000, description="Batch size for processing")


class RechunkTaskCreate(RechunkTaskBase):
    """Schema for creating a new rechunk task."""

    total_items: int = Field(..., ge=0, description="Total items to process")


class RechunkTaskProgress(BaseModel):
    """Schema for task progress metrics."""

    model_config = ConfigDict(use_enum_values=True)

    processed_count: int = Field(default=0, ge=0, description="Number of items processed")
    total_count: int = Field(default=0, ge=0, description="Total items to process")

    @property
    def progress_percentage(self) -> float:
        """Calculate progress as a percentage (0.0 to 100.0)."""
        if self.total_count == 0:
            return 0.0
        return (self.processed_count / self.total_count) * 100.0


class RechunkTaskResponse(RechunkTaskBase):
    """Response schema for rechunk task status with full details."""

    model_config = ConfigDict(use_enum_values=True, from_attributes=True)

    task_id: UUID = Field(..., description="Unique task identifier")
    status: RechunkTaskStatus = Field(..., description="Current task status")
    processed_count: int = Field(default=0, ge=0, description="Number of items processed")
    total_count: int = Field(default=0, ge=0, description="Total items to process")
    error: str | None = Field(default=None, description="Error message if task failed")
    created_at: datetime = Field(..., description="When the task was created")
    updated_at: datetime = Field(..., description="When the task was last updated")

    @field_serializer("created_at", "updated_at", when_used="json")
    def serialize_datetime(self, value: datetime) -> str:
        """Serialize datetime to ISO 8601 format with timezone."""
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.isoformat()

    @property
    def progress_percentage(self) -> float:
        """Calculate progress as a percentage (0.0 to 100.0)."""
        if self.total_count == 0:
            return 0.0
        return (self.processed_count / self.total_count) * 100.0


class RechunkTaskStartResponse(BaseModel):
    """Response schema for starting a rechunk task."""

    model_config = ConfigDict(use_enum_values=True, from_attributes=True)

    task_id: UUID = Field(..., description="Unique task identifier for status polling")
    status: RechunkTaskStatus = Field(..., description="Initial task status (pending)")
    total_items: int = Field(..., ge=0, description="Total items to process")
    batch_size: int = Field(..., ge=1, le=1000, description="Batch size for processing")
    message: str = Field(..., description="Human-readable status message")
