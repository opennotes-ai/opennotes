from enum import Enum


class ActionType(str, Enum):
    DELETE = "delete"
    HIDE = "hide"
    SILENCE = "silence"
    UNHIDE = "unhide"
    WARN = "warn"

    def __str__(self) -> str:
        return str(self.value)
