from enum import Enum


class ContentModerationClassificationResultRecommendedActionType0(str, Enum):
    HIDE = "hide"
    PASS = "pass"
    REVIEW = "review"

    def __str__(self) -> str:
        return str(self.value)
