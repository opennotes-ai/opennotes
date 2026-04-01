from enum import Enum


class ActionState(str, Enum):
    APPLIED = "applied"
    CONFIRMED = "confirmed"
    DISMISSED = "dismissed"
    OVERTURNED = "overturned"
    PROPOSED = "proposed"
    RETRO_REVIEW = "retro_review"
    SCAN_EXEMPT = "scan_exempt"
    UNDER_REVIEW = "under_review"

    def __str__(self) -> str:
        return str(self.value)
