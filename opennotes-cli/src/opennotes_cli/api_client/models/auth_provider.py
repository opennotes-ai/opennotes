from enum import Enum


class AuthProvider(str, Enum):
    DISCORD = "discord"
    EMAIL = "email"
    GITHUB = "github"

    def __str__(self) -> str:
        return str(self.value)
