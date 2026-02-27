from enum import Enum


class CommunityServerCreateRequestPlatform(str, Enum):
    DISCORD = "discord"
    DISCOURSE = "discourse"
    MATRIX = "matrix"
    OTHER = "other"
    PLAYGROUND = "playground"
    REDDIT = "reddit"
    SLACK = "slack"

    def __str__(self) -> str:
        return str(self.value)
