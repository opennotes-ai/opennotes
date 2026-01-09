"""
Pydantic schemas for batch job tracking.

Follows the 4-tier pattern: Base, Create, Update, Response.
"""

from datetime import UTC, datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_serializer


class BatchJobStatus(str, Enum):
    """Status states for a batch job."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BatchJobBase(BaseModel):
    """Base schema for batch jobs - shared fields."""

    model_config = ConfigDict(use_enum_values=True)

    job_type: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Type of batch job (e.g., 'fact_check_import')",
    )


class BatchJobCreate(BatchJobBase):
    """Schema for creating a new batch job."""

    total_tasks: int = Field(
        default=0,
        ge=0,
        description="Total number of tasks to process",
    )
    metadata_: dict = Field(
        default_factory=dict,
        alias="metadata",
        description="Job-specific metadata (e.g., source file, options)",
    )


class BatchJobUpdate(BaseModel):
    """Schema for updating batch job progress."""

    model_config = ConfigDict(use_enum_values=True)

    status: BatchJobStatus | None = Field(
        default=None,
        description="New status for the job",
    )
    completed_tasks: int | None = Field(
        default=None,
        ge=0,
        description="Number of successfully completed tasks",
    )
    failed_tasks: int | None = Field(
        default=None,
        ge=0,
        description="Number of failed tasks",
    )
    error_summary: dict | None = Field(
        default=None,
        description="Summary of errors encountered",
    )


class BatchJobResponse(BatchJobBase):
    """Response schema for batch job with full details."""

    model_config = ConfigDict(use_enum_values=True, from_attributes=True)

    id: UUID = Field(..., description="Unique job identifier")
    status: BatchJobStatus = Field(..., description="Current job status")
    total_tasks: int = Field(default=0, ge=0, description="Total tasks to process")
    completed_tasks: int = Field(default=0, ge=0, description="Tasks completed successfully")
    failed_tasks: int = Field(default=0, ge=0, description="Tasks that failed")
    metadata_: dict = Field(
        default_factory=dict,
        alias="metadata",
        description="Job-specific metadata",
    )
    error_summary: dict | None = Field(
        default=None,
        description="Summary of errors if any",
    )
    started_at: datetime | None = Field(
        default=None,
        description="When the job started processing",
    )
    completed_at: datetime | None = Field(
        default=None,
        description="When the job finished",
    )
    created_at: datetime = Field(..., description="When the job was created")
    updated_at: datetime | None = Field(
        default=None,
        description="When the job was last updated",
    )

    @field_serializer("created_at", "updated_at", "started_at", "completed_at", when_used="json")
    def serialize_datetime(self, value: datetime | None) -> str | None:
        """Serialize datetime to ISO 8601 format with timezone."""
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.isoformat()

    @computed_field
    @property
    def progress_percentage(self) -> float:
        """Calculate progress as a percentage (0.0 to 100.0)."""
        if self.total_tasks == 0:
            return 0.0
        return (self.completed_tasks / self.total_tasks) * 100.0


class BatchJobProgress(BaseModel):
    """Real-time progress information from Redis cache."""

    model_config = ConfigDict(use_enum_values=True)

    job_id: UUID = Field(..., description="Job identifier")
    processed_count: int = Field(default=0, ge=0, description="Items processed so far")
    error_count: int = Field(default=0, ge=0, description="Errors encountered")
    current_item: str | None = Field(default=None, description="Currently processing item")
    rate: float = Field(default=0.0, ge=0.0, description="Processing rate (items/second)")
    eta_seconds: float | None = Field(default=None, description="Estimated time to completion")
