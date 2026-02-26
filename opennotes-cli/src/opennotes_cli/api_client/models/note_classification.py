from enum import Enum


class NoteClassification(str, Enum):
    MISINFORMED_OR_POTENTIALLY_MISLEADING = "MISINFORMED_OR_POTENTIALLY_MISLEADING"
    NOT_MISLEADING = "NOT_MISLEADING"

    def __str__(self) -> str:
        return str(self.value)
