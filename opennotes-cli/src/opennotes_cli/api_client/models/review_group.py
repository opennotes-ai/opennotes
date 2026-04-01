from enum import Enum


class ReviewGroup(str, Enum):
    COMMUNITY = "community"
    STAFF = "staff"
    TRUSTED = "trusted"

    def __str__(self) -> str:
        return str(self.value)
