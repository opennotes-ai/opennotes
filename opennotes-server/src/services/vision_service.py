"""Service for generating image descriptions using LLM vision capabilities."""

import hashlib
from typing import Literal, cast

from cachetools import TTLCache
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.llm_config.models import CommunityServer
from src.llm_config.service import LLMService
from src.monitoring import get_logger

logger = get_logger(__name__)


class VisionService:
    """
    Service for generating image descriptions using LLM vision capabilities.

    Uses LLMService for credential management and provider abstraction.
    """

    def __init__(self, llm_service: LLMService) -> None:
        self.llm_service = llm_service
        self.description_cache: TTLCache[str, str] = TTLCache[str, str](
            maxsize=1000, ttl=settings.VISION_CACHE_TTL_SECONDS
        )

    async def describe_image(
        self,
        db: AsyncSession,
        image_url: str,
        community_server_id: str,
        detail: Literal["low", "high", "auto"] = "auto",
        max_tokens: int = 300,
    ) -> str:
        """
        Generate description for an image using LLM vision capabilities.

        Automatically retries on errors with exponential backoff.
        Routes through the appropriate provider based on the configured VISION_MODEL.

        Args:
            db: Database session
            image_url: URL of image to describe
            community_server_id: Community server (guild) ID
            detail: Image detail level - 'low' for quick/cheap, 'high' for detailed
            max_tokens: Maximum tokens in description

        Returns:
            Generated description text

        Raises:
            ValueError: If no LLM configuration found for community server
            Exception: If API call fails after retries
        """
        cache_key = self._get_cache_key(image_url, detail, max_tokens)
        if cache_key in self.description_cache:
            logger.debug(
                "Vision cache hit",
                extra={"image_url": image_url[:100], "cache_key": cache_key[:16]},
            )
            return cast(str, self.description_cache[cache_key])

        # Convert guild ID string to UUID for LLMService
        # Get CommunityServer UUID from platform_community_server_id (Discord guild ID)
        result = await db.execute(
            select(CommunityServer.id).where(
                CommunityServer.platform_community_server_id == community_server_id
            )
        )
        community_server_uuid = result.scalar_one_or_none()

        if not community_server_uuid:
            raise ValueError(
                f"Community server not found for platform_community_server_id: {community_server_id}"
            )

        # Generate description via LLMService (handles retries internally)
        description = await self.llm_service.describe_image(
            db, image_url, community_server_uuid, detail, max_tokens
        )

        self.description_cache[cache_key] = description

        return description

    def _get_cache_key(self, image_url: str, detail: str, max_tokens: int) -> str:
        """
        Generate cache key from image URL and parameters.

        Args:
            image_url: Image URL
            detail: Detail level
            max_tokens: Max tokens

        Returns:
            SHA256 hash of parameters
        """
        key_data = f"{image_url}|{detail}|{max_tokens}"
        return hashlib.sha256(key_data.encode("utf-8")).hexdigest()

    def invalidate_cache(self, community_server_id: str | None = None) -> None:
        self.description_cache.clear()
        logger.info(
            "Vision description cache invalidated",
            extra={"community_server_id": community_server_id},
        )
