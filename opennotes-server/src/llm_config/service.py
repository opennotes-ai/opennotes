"""
Unified LLM service interface.

Provides high-level methods for all LLM operations with automatic
credential fallback and provider abstraction.
"""

from collections.abc import AsyncGenerator
from typing import Any, Literal
from uuid import UUID

import litellm
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.config import settings
from src.llm_config.manager import LLMClientManager
from src.llm_config.providers import LiteLLMCompletionParams
from src.llm_config.providers.base import LLMMessage, LLMResponse
from src.monitoring import get_logger

logger = get_logger(__name__)


class LLMService:
    """
    Unified service for all LLM operations.

    Provides high-level methods that automatically handle:
    - Server-specific → global credential fallback
    - Provider abstraction (OpenAI/Anthropic/LiteLLM)
    - Caching and resource management
    - Error handling and retries
    """

    def __init__(self, client_manager: LLMClientManager) -> None:
        """
        Initialize LLM service.

        Args:
            client_manager: LLM client manager for provider access
        """
        self.client_manager = client_manager

    async def complete(
        self,
        db: AsyncSession,
        messages: list[LLMMessage],
        community_server_id: UUID,
        provider: str = "openai",
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """
        Generate a completion using the specified LLM provider.

        Args:
            db: Database session
            messages: Conversation messages
            community_server_id: Community server UUID
            provider: Provider name ('openai', 'anthropic')
            model: Model to use (uses provider default if None)
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            **kwargs: Additional provider-specific parameters

        Returns:
            LLMResponse with generated content

        Raises:
            ValueError: If no LLM configuration found for provider
            Exception: If API call fails
        """
        llm_provider = await self.client_manager.get_client(db, community_server_id, provider)

        if not llm_provider:
            raise ValueError(
                f"No {provider} configuration found for community server {community_server_id}"
            )

        params = LiteLLMCompletionParams(
            model=model, max_tokens=max_tokens, temperature=temperature, **kwargs
        )

        logger.info(
            f"Generating completion with {provider}",
            extra={
                "community_server_id": str(community_server_id),
                "provider": provider,
                "model": model or "default",
                "message_count": len(messages),
            },
        )

        return await llm_provider.complete(messages, params)

    async def stream_complete(
        self,
        db: AsyncSession,
        messages: list[LLMMessage],
        community_server_id: UUID,
        provider: str = "openai",
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[str, None]:
        """
        Generate a streaming completion using the specified LLM provider.

        Args:
            db: Database session
            messages: Conversation messages
            community_server_id: Community server UUID
            provider: Provider name ('openai', 'anthropic')
            model: Model to use (uses provider default if None)
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            **kwargs: Additional provider-specific parameters

        Yields:
            Content chunks as they are generated

        Raises:
            ValueError: If no LLM configuration found for provider
            Exception: If API call fails
        """
        llm_provider = await self.client_manager.get_client(db, community_server_id, provider)

        if not llm_provider:
            raise ValueError(
                f"No {provider} configuration found for community server {community_server_id}"
            )

        params = LiteLLMCompletionParams(
            model=model, max_tokens=max_tokens, temperature=temperature, **kwargs
        )

        logger.info(
            f"Starting streaming completion with {provider}",
            extra={
                "community_server_id": str(community_server_id),
                "provider": provider,
                "model": model or "default",
                "message_count": len(messages),
            },
        )

        async for chunk in llm_provider.stream_complete(messages, params):
            yield chunk

    @retry(
        retry=retry_if_exception_type(Exception),
        wait=wait_exponential(multiplier=1, min=1, max=60),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    async def generate_embedding(
        self,
        db: AsyncSession,
        text: str,
        community_server_id: UUID,
        model: str | None = None,
    ) -> tuple[list[float], str, str]:
        """
        Generate embedding for text using LiteLLM.

        Automatically retries on errors with exponential backoff.
        Uses OpenAI provider credentials but can work with any LiteLLM-supported
        embedding model.

        Args:
            db: Database session
            text: Text to embed
            community_server_id: Community server UUID
            model: Embedding model (uses settings.EMBEDDING_MODEL if None)

        Returns:
            Tuple of (embedding vector, provider name, model name)

        Raises:
            ValueError: If no OpenAI configuration found
            Exception: If API call fails after retries
        """
        llm_provider = await self.client_manager.get_client(db, community_server_id, "openai")

        if not llm_provider:
            raise ValueError(
                f"No OpenAI configuration found for community server {community_server_id}"
            )

        embedding_model = model or settings.EMBEDDING_MODEL

        logger.debug(
            "Generating embedding",
            extra={
                "text_length": len(text),
                "community_server_id": str(community_server_id),
                "model": embedding_model,
            },
        )

        response = await litellm.aembedding(
            model=embedding_model,
            input=[text],
            api_key=llm_provider.api_key,
            encoding_format="float",
        )

        embedding = response.data[0]["embedding"]

        logger.info(
            "Embedding generated successfully",
            extra={
                "text_length": len(text),
                "community_server_id": str(community_server_id),
                "tokens_used": response.usage.total_tokens if response.usage else 0,
                "embedding_dimensions": len(embedding),
            },
        )

        return embedding, "litellm", embedding_model

    @retry(
        retry=retry_if_exception_type(Exception),
        wait=wait_exponential(multiplier=1, min=1, max=60),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    async def describe_image(
        self,
        db: AsyncSession,
        image_url: str,
        community_server_id: UUID,
        detail: Literal["low", "high", "auto"] = "auto",
        max_tokens: int = 300,
        model: str | None = None,
    ) -> str:
        """
        Generate image description using LiteLLM vision capabilities.

        Automatically retries on errors with exponential backoff.
        Uses OpenAI provider credentials but can work with any LiteLLM-supported
        vision model.

        Args:
            db: Database session
            image_url: URL of image to describe
            community_server_id: Community server UUID
            detail: Image detail level ('low', 'high', 'auto')
            max_tokens: Maximum tokens in description
            model: Vision model (uses settings.VISION_MODEL if None)

        Returns:
            Generated description text

        Raises:
            ValueError: If no OpenAI configuration found
            Exception: If API call fails after retries
        """
        llm_provider = await self.client_manager.get_client(db, community_server_id, "openai")

        if not llm_provider:
            raise ValueError(
                f"No OpenAI configuration found for community server {community_server_id}"
            )

        vision_model = model or settings.VISION_MODEL

        logger.debug(
            "Generating image description",
            extra={
                "image_url": image_url[:100],
                "community_server_id": str(community_server_id),
                "model": vision_model,
                "detail": detail,
            },
        )

        response = await litellm.acompletion(
            model=vision_model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": settings.VISION_PROMPT,
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": image_url, "detail": detail},
                        },
                    ],
                }
            ],
            max_tokens=max_tokens,
            api_key=llm_provider.api_key,
        )

        description = response.choices[0].message.content or ""  # type: ignore[union-attr]

        logger.info(
            "Image description generated successfully",
            extra={
                "image_url": image_url[:100],
                "community_server_id": str(community_server_id),
                "tokens_used": response.usage.total_tokens if response.usage else 0,  # type: ignore[union-attr]
                "description_length": len(description),
            },
        )

        return description

    def invalidate_cache(self, community_server_id: UUID, provider: str | None = None) -> None:
        """
        Invalidate cached LLM clients for a community server.

        Args:
            community_server_id: Community server UUID
            provider: Specific provider to invalidate, or None for all providers
        """
        self.client_manager.invalidate_cache(community_server_id, provider)
