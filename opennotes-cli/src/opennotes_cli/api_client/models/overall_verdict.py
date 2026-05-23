from enum import Enum


class OverallVerdict(str, Enum):
    FLAG = "flag"
    PASS = "pass"

    def __str__(self) -> str:
        return str(self.value)
