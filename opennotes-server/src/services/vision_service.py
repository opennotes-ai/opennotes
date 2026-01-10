"""Service for generating image descriptions using GPT-5.1 vision."""

import hashlib
from typing import Literal, cast

from cachetools import TTLCache
from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.llm_config.models import CommunityServer, CommunityServerLLMConfig
from src.llm_config.service import LLMService
from src.monitoring import get_logger

logger = get_logger(__name__)


class VisionService:
    """
    Service for generating image descriptions using GPT-5.1 vision API.

    Uses LLMService for credential management and provider abstraction.
    """

    def __init__(self, llm_service: LLMService) -> None:
        """
        Initialize vision service.

        Args:
            llm_service: LLM service for generating image descriptions
        """
        self.llm_service = llm_service
        self.description_cache: TTLCache[str, str] = TTLCache[str, str](
            maxsize=1000, ttl=settings.VISION_CACHE_TTL_SECONDS
        )
        self.api_key_source_cache: dict[str, str] = {}

    async def describe_image(
        self,
        db: AsyncSession,
        image_url: str,
        community_server_id: str,
        detail: Literal["low", "high", "auto"] = "auto",
        max_tokens: int = 300,
    ) -> str:
        """
        Generate description for an image using GPT-5.1 vision.

        Automatically retries on errors with exponential backoff.

        Args:
            db: Database session
            image_url: URL of image to describe
            community_server_id: Community server (guild) ID
            detail: Image detail level - 'low' for quick/cheap, 'high' for detailed
            max_tokens: Maximum tokens in description

        Returns:
            Generated description text

        Raises:
            ValueError: If no OpenAI configuration found for community server
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

    async def _get_openai_client(self, db: AsyncSession, community_server_id: str) -> AsyncOpenAI:
        """
        Get or create an OpenAI client for the community server.

        Attempts to use community-specific configuration first, then falls back
        to global API key. Tracks which source was used.

        Args:
            db: Database session
            community_server_id: Community server ID (string/platform ID)

        Returns:
            Initialized AsyncOpenAI client

        Raises:
            ValueError: If no OpenAI configuration found for community server
        """
        result = await db.execute(
            select(CommunityServerLLMConfig).where(
                CommunityServerLLMConfig.community_server_id == community_server_id,
                CommunityServerLLMConfig.provider == "openai",
                CommunityServerLLMConfig.enabled == True,
            )
        )
        config = result.scalar_one_or_none()

        if config:
            api_key = self.llm_service.client_manager.encryption_service.decrypt_api_key(
                config.api_key_encrypted, config.encryption_key_id
            )
            self.api_key_source_cache[community_server_id] = "community"
            logger.info(
                "Using community OpenAI API key",
                extra={
                    "community_server_id": community_server_id,
                    "api_key_source": "community",
                },
            )
            return AsyncOpenAI(api_key=api_key, timeout=30.0)

        if settings.OPENAI_API_KEY:
            self.api_key_source_cache[community_server_id] = "global"
            logger.info(
                "Using global OpenAI API key as fallback",
                extra={
                    "community_server_id": community_server_id,
                    "api_key_source": "global",
                },
            )
            return AsyncOpenAI(api_key=settings.OPENAI_API_KEY, timeout=30.0)

        raise ValueError(
            f"No OpenAI configuration found for community server {community_server_id}"
        )

    def invalidate_cache(self, community_server_id: str | None = None) -> None:
        """
        Invalidate cached image descriptions and API key source information.

        Args:
            community_server_id: Specific community server ID to invalidate,
                                or None to clear all caches
        """
        self.description_cache.clear()
        if community_server_id is None:
            self.api_key_source_cache.clear()
        else:
            self.api_key_source_cache.pop(community_server_id, None)
        logger.info(
            "Vision description cache invalidated",
            extra={"community_server_id": community_server_id},
        )
