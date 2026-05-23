from enum import Enum


class JobStatus(str, Enum):
    ANALYZING = "analyzing"
    DONE = "done"
    EXTRACTING = "extracting"
    FAILED = "failed"
    PARTIAL = "partial"
    PENDING = "pending"

    def __str__(self) -> str:
        return str(self.value)
