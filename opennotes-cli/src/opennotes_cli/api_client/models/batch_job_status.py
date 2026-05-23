from enum import Enum


class BatchJobStatus(str, Enum):
    ANALYZING = "analyzing"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    EXTRACTING = "extracting"
    FAILED = "failed"
    IN_PROGRESS = "in_progress"
    PARTIAL = "partial"
    PENDING = "pending"

    def __str__(self) -> str:
        return str(self.value)
