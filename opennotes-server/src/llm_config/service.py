"""
Unified LLM service interface.

Provides high-level methods for all LLM operations with automatic
credential fallback and provider abstraction.
"""

from collections.abc import AsyncGenerator
from typing import Any, Literal
from uuid import UUID

import litellm
from litellm.exceptions import (
    APIConnectionError,
    APIError,
    RateLimitError,
    ServiceUnavailableError,
    Timeout,
)
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.config import settings
from src.llm_config.manager import LLMClientManager
from src.llm_config.model_id import ModelId
from src.llm_config.providers import LiteLLMCompletionParams
from src.llm_config.providers.base import LLMMessage, LLMResponse
from src.monitoring import get_logger

TRANSIENT_EXCEPTIONS = (
    APIConnectionError,
    Timeout,
    RateLimitError,
    ServiceUnavailableError,
    APIError,
    ConnectionError,
    TimeoutError,
)

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
        community_server_id: UUID | None = None,
        provider: str = "openai",
        model: ModelId | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """
        Generate a completion using the specified LLM provider.

        Args:
            db: Database session
            messages: Conversation messages
            community_server_id: Community server UUID, or None for global fallback
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
        if model:
            litellm_provider = model.litellm_provider
            if provider not in ("openai", model.provider, litellm_provider):
                logger.warning(
                    "Model prefix provider differs from explicit provider param, "
                    "using model prefix",
                    extra={
                        "explicit_provider": provider,
                        "model_prefix_provider": model.provider,
                        "model": model.to_litellm(),
                    },
                )
            provider = litellm_provider

        llm_provider = await self.client_manager.get_client(db, community_server_id, provider)

        if not llm_provider:
            context = f"community server {community_server_id}" if community_server_id else "global"
            raise ValueError(f"No {provider} configuration found for {context}")

        params = LiteLLMCompletionParams(
            model=model, max_tokens=max_tokens, temperature=temperature, **kwargs
        )

        logger.debug(
            f"Generating completion with {provider}",
            extra={
                "community_server_id": str(community_server_id) if community_server_id else None,
                "provider": provider,
                "model": model.to_litellm() if model else "default",
                "message_count": len(messages),
            },
        )

        return await llm_provider.complete(messages, params)

    async def stream_complete(
        self,
        db: AsyncSession,
        messages: list[LLMMessage],
        community_server_id: UUID | None = None,
        provider: str = "openai",
        model: ModelId | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[str, None]:
        """
        Generate a streaming completion using the specified LLM provider.

        Args:
            db: Database session
            messages: Conversation messages
            community_server_id: Community server UUID, or None for global fallback
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
        if model:
            litellm_provider = model.litellm_provider
            if provider not in ("openai", model.provider, litellm_provider):
                logger.warning(
                    "Model prefix provider differs from explicit provider param, "
                    "using model prefix",
                    extra={
                        "explicit_provider": provider,
                        "model_prefix_provider": model.provider,
                        "model": model.to_litellm(),
                    },
                )
            provider = litellm_provider

        llm_provider = await self.client_manager.get_client(db, community_server_id, provider)

        if not llm_provider:
            context = f"community server {community_server_id}" if community_server_id else "global"
            raise ValueError(f"No {provider} configuration found for {context}")

        params = LiteLLMCompletionParams(
            model=model, max_tokens=max_tokens, temperature=temperature, **kwargs
        )

        logger.debug(
            f"Starting streaming completion with {provider}",
            extra={
                "community_server_id": str(community_server_id) if community_server_id else None,
                "provider": provider,
                "model": model.to_litellm() if model else "default",
                "message_count": len(messages),
            },
        )

        async for chunk in llm_provider.stream_complete(messages, params):
            yield chunk

    @retry(
        retry=retry_if_exception_type(TRANSIENT_EXCEPTIONS),
        wait=wait_exponential(multiplier=1, min=1, max=60),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    async def generate_embedding(
        self,
        db: AsyncSession,
        text: str,
        community_server_id: UUID | None = None,
        model: ModelId | None = None,
    ) -> tuple[list[float], str, str]:
        """
        Generate embedding for text using LiteLLM.

        Automatically retries on errors with exponential backoff.
        Uses OpenAI provider credentials but can work with any LiteLLM-supported
        embedding model.

        Args:
            db: Database session
            text: Text to embed
            community_server_id: Community server UUID, or None for global fallback
            model: Embedding model (uses settings.EMBEDDING_MODEL if None)

        Returns:
            Tuple of (embedding vector, provider name, model name)

        Raises:
            ValueError: If no OpenAI configuration found
            Exception: If API call fails after retries
        """
        llm_provider = await self.client_manager.get_client(db, community_server_id, "openai")

        if not llm_provider:
            context = f"community server {community_server_id}" if community_server_id else "global"
            raise ValueError(f"No OpenAI configuration found for {context}")

        embedding_model = model or settings.EMBEDDING_MODEL
        embedding_model_str = embedding_model.to_litellm()

        logger.debug(
            "Generating embedding",
            extra={
                "text_length": len(text),
                "community_server_id": str(community_server_id) if community_server_id else None,
                "model": embedding_model_str,
            },
        )

        response = await litellm.aembedding(
            model=embedding_model_str,
            input=[text],
            api_key=llm_provider.api_key,
            encoding_format="float",
        )

        embedding = response.data[0]["embedding"]

        logger.info(
            "Embedding generated successfully",
            extra={
                "text_length": len(text),
                "community_server_id": str(community_server_id) if community_server_id else None,
                "tokens_used": response.usage.total_tokens if response.usage else 0,
                "embedding_dimensions": len(embedding),
            },
        )

        return embedding, "litellm", embedding_model_str

    @retry(
        retry=retry_if_exception_type(TRANSIENT_EXCEPTIONS),
        wait=wait_exponential(multiplier=1, min=1, max=60),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    async def generate_embeddings_batch(
        self,
        db: AsyncSession,
        texts: list[str],
        community_server_id: UUID | None = None,
        model: ModelId | None = None,
    ) -> list[tuple[list[float], str, str]]:
        """
        Generate embeddings for multiple texts in a single API call.

        This batch method reduces API calls from N to 1 for N texts, improving
        performance when embedding multiple chunks.

        Automatically retries on errors with exponential backoff.
        Uses OpenAI provider credentials but can work with any LiteLLM-supported
        embedding model.

        Args:
            db: Database session
            texts: List of texts to embed
            community_server_id: Community server UUID, or None for global fallback
            model: Embedding model (uses settings.EMBEDDING_MODEL if None)

        Returns:
            List of tuples (embedding vector, provider name, model name),
            in the same order as input texts

        Raises:
            ValueError: If no OpenAI configuration found or if texts is empty
            Exception: If API call fails after retries
        """
        if not texts:
            return []

        llm_provider = await self.client_manager.get_client(db, community_server_id, "openai")

        if not llm_provider:
            context = f"community server {community_server_id}" if community_server_id else "global"
            raise ValueError(f"No OpenAI configuration found for {context}")

        embedding_model = model or settings.EMBEDDING_MODEL
        embedding_model_str = embedding_model.to_litellm()

        logger.debug(
            "Generating batch embeddings",
            extra={
                "text_count": len(texts),
                "total_text_length": sum(len(t) for t in texts),
                "community_server_id": str(community_server_id) if community_server_id else None,
                "model": embedding_model_str,
            },
        )

        response = await litellm.aembedding(
            model=embedding_model_str,
            input=texts,
            api_key=llm_provider.api_key,
            encoding_format="float",
        )

        if len(response.data) != len(texts):
            raise ValueError(
                f"API returned {len(response.data)} embeddings but expected {len(texts)}"
            )

        embeddings_by_index = {item["index"]: item["embedding"] for item in response.data}
        results = [
            (embeddings_by_index[i], "litellm", embedding_model_str) for i in range(len(texts))
        ]

        logger.info(
            "Batch embeddings generated successfully",
            extra={
                "text_count": len(texts),
                "community_server_id": str(community_server_id) if community_server_id else None,
                "tokens_used": response.usage.total_tokens if response.usage else 0,
                "embedding_dimensions": len(results[0][0]) if results else 0,
            },
        )

        return results

    @retry(
        retry=retry_if_exception_type(TRANSIENT_EXCEPTIONS),
        wait=wait_exponential(multiplier=1, min=1, max=60),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    async def describe_image(
        self,
        db: AsyncSession,
        image_url: str,
        community_server_id: UUID | None = None,
        detail: Literal["low", "high", "auto"] = "auto",
        max_tokens: int = 300,
        model: ModelId | None = None,
    ) -> str:
        """
        Generate image description using LiteLLM vision capabilities.

        Automatically retries on errors with exponential backoff.
        Routes through the appropriate provider based on model prefix
        (e.g., "openai/gpt-5.1", "vertex_ai/gemini-2.5-flash").

        Args:
            db: Database session
            image_url: URL of image to describe
            community_server_id: Community server UUID, or None for global fallback
            detail: Image detail level ('low', 'high', 'auto')
            max_tokens: Maximum tokens in description
            model: Vision model (uses settings.VISION_MODEL if None)

        Returns:
            Generated description text

        Raises:
            ValueError: If no provider configuration found
            Exception: If API call fails after retries
        """
        vision_model = model or settings.VISION_MODEL
        provider = vision_model.litellm_provider

        llm_provider = await self.client_manager.get_client(db, community_server_id, provider)

        if not llm_provider:
            context = f"community server {community_server_id}" if community_server_id else "global"
            raise ValueError(f"No {provider} configuration found for {context}")

        logger.debug(
            "Generating image description",
            extra={
                "image_url": image_url[:100],
                "community_server_id": str(community_server_id) if community_server_id else None,
                "model": vision_model.to_litellm(),
                "detail": detail,
                "provider": provider,
            },
        )

        messages = [
            LLMMessage(
                role="user",
                content=[
                    {"type": "text", "text": settings.VISION_PROMPT},
                    {"type": "image_url", "image_url": {"url": image_url, "detail": detail}},
                ],
            )
        ]

        params = LiteLLMCompletionParams(model=vision_model, max_tokens=max_tokens)
        response = await llm_provider.complete(messages, params)

        logger.info(
            "Image description generated successfully",
            extra={
                "image_url": image_url[:100],
                "community_server_id": str(community_server_id) if community_server_id else None,
                "tokens_used": response.tokens_used,
                "description_length": len(response.content),
            },
        )

        return response.content

    def invalidate_cache(self, community_server_id: UUID, provider: str | None = None) -> None:
        """
        Invalidate cached LLM clients for a community server.

        Args:
            community_server_id: Community server UUID
            provider: Specific provider to invalidate, or None for all providers
        """
        self.client_manager.invalidate_cache(community_server_id, provider)
