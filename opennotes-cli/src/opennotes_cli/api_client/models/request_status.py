from enum import Enum


class RequestStatus(str, Enum):
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    IN_PROGRESS = "IN_PROGRESS"
    PENDING = "PENDING"

    def __str__(self) -> str:
        return str(self.value)
