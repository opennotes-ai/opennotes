from enum import Enum


class SafetyLevel(str, Enum):
    CAUTION = "caution"
    MILD = "mild"
    SAFE = "safe"
    UNSAFE = "unsafe"

    def __str__(self) -> str:
        return str(self.value)
