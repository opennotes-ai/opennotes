from enum import Enum


class HeadlineSummaryKind(str, Enum):
    STOCK = "stock"
    SYNTHESIZED = "synthesized"

    def __str__(self) -> str:
        return str(self.value)
