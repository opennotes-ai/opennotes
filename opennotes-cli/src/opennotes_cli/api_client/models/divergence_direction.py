from enum import Enum


class DivergenceDirection(str, Enum):
    DISCOUNTED = "discounted"
    ESCALATED = "escalated"

    def __str__(self) -> str:
        return str(self.value)
