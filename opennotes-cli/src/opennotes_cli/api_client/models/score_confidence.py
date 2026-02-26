from enum import Enum


class ScoreConfidence(str, Enum):
    NO_DATA = "no_data"
    PROVISIONAL = "provisional"
    STANDARD = "standard"

    def __str__(self) -> str:
        return str(self.value)
