"""
Unified LLM service interface.

Provides high-level methods for all LLM operations with automatic
credential fallback and provider abstraction.
"""

import re
from collections.abc import AsyncGenerator
from typing import Any, Literal
from uuid import UUID

from litellm.exceptions import (
    APIConnectionError,
    APIError,
    BadRequestError,
    RateLimitError,
    ServiceUnavailableError,
    Timeout,
)
from pydantic_ai import Embedder
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import (
    AsyncRetrying,
    retry,
    retry_if_exception_type,
    retry_if_not_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.config import settings
from src.llm_config.manager import LLMClientManager
from src.llm_config.model_id import ModelId
from src.llm_config.providers import LiteLLMCompletionParams
from src.llm_config.providers.base import LLMMessage, LLMResponse
from src.llm_config.providers.direct_provider import EmptyLLMResponseError
from src.monitoring import get_logger

TRANSIENT_EXCEPTIONS = (
    APIConnectionError,
    Timeout,
    RateLimitError,
    ServiceUnavailableError,
    APIError,
    ConnectionError,
    TimeoutError,
    EmptyLLMResponseError,
)

_RETRY_PREDICATE = retry_if_exception_type(TRANSIENT_EXCEPTIONS) & retry_if_not_exception_type(
    BadRequestError
)

logger = get_logger(__name__)


class LLMService:
    """
    Unified service for all LLM operations.

    Provides high-level methods that automatically handle:
    - Server-specific -> global credential fallback
    - Provider abstraction (OpenAI/Anthropic/LiteLLM)
    - Caching and resource management
    - Error handling and retries
    """

    def __init__(self, client_manager: LLMClientManager, embedder: Embedder | None = None) -> None:
        self.client_manager = client_manager
        self._embedder = embedder
        self._control_char_re = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")

    def _sanitize_embedding_text(self, text: str) -> str:
        cleaned = self._control_char_re.sub("", text)
        if len(cleaned) != len(text):
            logger.debug(
                "Stripped control characters from embedding input",
                extra={
                    "original_length": len(text),
                    "cleaned_length": len(cleaned),
                    "chars_removed": len(text) - len(cleaned),
                },
            )
        return cleaned

    @retry(
        retry=_RETRY_PREDICATE,
        wait=wait_exponential(multiplier=1, min=1, max=60),
        stop=stop_after_attempt(2),
        reraise=True,
    )
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

    def _require_embedder(self) -> Embedder:
        if self._embedder is None:
            raise RuntimeError(
                "LLMService was created without an Embedder; "
                "pass embedder= to use embedding methods"
            )
        return self._embedder

    async def generate_embedding(
        self,
        text: str,
        input_type: Literal["query", "document"] = "document",
        retry_attempts: int | None = None,
    ) -> tuple[list[float], str, str]:
        max_attempts = 3 if retry_attempts is None else retry_attempts
        if max_attempts < 1:
            raise ValueError(f"retry_attempts must be >= 1, got {max_attempts}")

        embedder = self._require_embedder()
        sanitized_text = self._sanitize_embedding_text(text)

        async for attempt in AsyncRetrying(
            retry=_RETRY_PREDICATE,
            wait=wait_exponential(multiplier=1, min=1, max=60),
            stop=stop_after_attempt(max_attempts),
            reraise=True,
        ):
            with attempt:
                if input_type == "query":
                    result = await embedder.embed_query(sanitized_text)
                else:
                    result = await embedder.embed_documents(sanitized_text)

                embedding = list(result.embeddings[0])
                return embedding, result.provider_name, result.model_name

        raise RuntimeError("Embedding generation failed unexpectedly after retries")

    async def generate_embeddings_batch(
        self,
        texts: list[str],
        input_type: Literal["query", "document"] = "document",  # noqa: ARG002
    ) -> list[tuple[list[float], str, str]]:
        if not texts:
            return []

        embedder = self._require_embedder()
        sanitized_texts = [self._sanitize_embedding_text(t) for t in texts]
        result = await embedder.embed_documents(sanitized_texts)
        return [(list(emb), result.provider_name, result.model_name) for emb in result.embeddings]

    @retry(
        retry=_RETRY_PREDICATE,
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
        self.client_manager.invalidate_cache(community_server_id, provider)
