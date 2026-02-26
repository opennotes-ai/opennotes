from enum import Enum


class RiskLevel(str, Enum):
    DANGEROUS = "Dangerous"
    GUARDED = "Guarded"
    HEATED = "Heated"
    HOSTILE = "Hostile"
    LOW_RISK = "Low Risk"

    def __str__(self) -> str:
        return str(self.value)
