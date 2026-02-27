from enum import Enum


class NoteStatus(str, Enum):
    CURRENTLY_RATED_HELPFUL = "CURRENTLY_RATED_HELPFUL"
    CURRENTLY_RATED_NOT_HELPFUL = "CURRENTLY_RATED_NOT_HELPFUL"
    NEEDS_MORE_RATINGS = "NEEDS_MORE_RATINGS"

    def __str__(self) -> str:
        return str(self.value)
