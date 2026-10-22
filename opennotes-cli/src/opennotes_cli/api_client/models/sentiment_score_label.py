from enum import Enum


class SentimentScoreLabel(str, Enum):
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    POSITIVE = "positive"

    def __str__(self) -> str:
        return str(self.value)
