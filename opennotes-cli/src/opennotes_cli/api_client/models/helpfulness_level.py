from enum import Enum


class HelpfulnessLevel(str, Enum):
    HELPFUL = "HELPFUL"
    NOT_HELPFUL = "NOT_HELPFUL"
    SOMEWHAT_HELPFUL = "SOMEWHAT_HELPFUL"

    def __str__(self) -> str:
        return str(self.value)
