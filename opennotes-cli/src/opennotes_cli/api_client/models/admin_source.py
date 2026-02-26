from enum import Enum


class AdminSource(str, Enum):
    COMMUNITY_ROLE = "community_role"
    DISCORD_MANAGE_SERVER = "discord_manage_server"
    OPENNOTES_PLATFORM = "opennotes_platform"

    def __str__(self) -> str:
        return str(self.value)
