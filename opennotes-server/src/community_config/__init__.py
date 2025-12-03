from typing import TYPE_CHECKING

from src.community_config.models import CommunityConfig

if TYPE_CHECKING:
    from src.community_config.router import router


__all__ = ["CommunityConfig", "router"]
