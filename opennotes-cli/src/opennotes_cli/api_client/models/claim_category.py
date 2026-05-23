from enum import Enum


class ClaimCategory(str, Enum):
    OTHER = "other"
    POTENTIALLY_FACTUAL = "potentially_factual"
    PREDICTIONS = "predictions"
    SELF_CLAIMS = "self_claims"
    SUBJECTIVE = "subjective"

    def __str__(self) -> str:
        return str(self.value)
