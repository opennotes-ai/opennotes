"""Data carriers for submit-path helpers (TASK-1498.02)."""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from src.analyses.schemas import JobStatus


@dataclass(frozen=True)
class SubmitResult:
    """Minimal submit-path outcome used by the POST /api/analyze handler."""

    job_id: UUID
    status: JobStatus
    cached: bool
