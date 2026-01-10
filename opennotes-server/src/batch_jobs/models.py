"""
SQLAlchemy models for batch job tracking.

Provides persistent storage for batch job status, progress, and error information.
Used for long-running operations like fact-check imports.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID

from sqlalchemy import DateTime, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base
from src.notes.models import TimestampMixin


class BatchJobStatus(str, Enum):
    """Status states for a batch job."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BatchJob(Base, TimestampMixin):
    """
    Database model for tracking batch job progress and status.

    This model provides persistent storage for long-running batch operations,
    enabling progress tracking, error reporting, and job management.
    """

    __tablename__ = "batch_jobs"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("uuidv7()"),
    )

    job_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        server_default=text("'pending'"),
        nullable=False,
        index=True,
    )

    total_tasks: Mapped[int] = mapped_column(
        Integer,
        server_default=text("0"),
        nullable=False,
    )

    completed_tasks: Mapped[int] = mapped_column(
        Integer,
        server_default=text("0"),
        nullable=False,
    )

    failed_tasks: Mapped[int] = mapped_column(
        Integer,
        server_default=text("0"),
        nullable=False,
    )

    metadata_: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        server_default=text("'{}'::jsonb"),
        nullable=False,
    )

    error_summary: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    @property
    def progress_percentage(self) -> float:
        """Calculate progress as a percentage (0.0 to 100.0)."""
        if self.total_tasks == 0:
            return 0.0
        return (self.completed_tasks / self.total_tasks) * 100.0

    @property
    def is_terminal(self) -> bool:
        """Check if the job is in a terminal state."""
        return self.status in (
            BatchJobStatus.COMPLETED.value,
            BatchJobStatus.FAILED.value,
            BatchJobStatus.CANCELLED.value,
        )
