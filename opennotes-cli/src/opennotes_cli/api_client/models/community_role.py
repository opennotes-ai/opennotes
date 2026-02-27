from enum import Enum


class CommunityRole(str, Enum):
    ADMIN = "admin"
    MEMBER = "member"
    MODERATOR = "moderator"

    def __str__(self) -> str:
        return str(self.value)
