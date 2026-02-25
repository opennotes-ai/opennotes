"""LiteLLM unified provider - supports all LLM backends via single interface."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

import litellm
from litellm.exceptions import JSONSchemaValidationError
from pydantic import BaseModel, ConfigDict, Field

from src.llm_config.model_id import ModelId
from src.llm_config.providers.base import LLMMessage, LLMProvider, LLMResponse, ProviderSettings
from src.monitoring import get_logger

logger = get_logger(__name__)


class LiteLLMProviderSettings(ProviderSettings):
    """Settings for LiteLLM unified provider."""

    model_config = ConfigDict(extra="forbid")

    timeout: float = Field(30.0, description="Request timeout in seconds", gt=0)
    max_tokens: int = Field(4096, description="Default max tokens to generate", gt=0)
    temperature: float = Field(0.7, description="Default sampling temperature", ge=0.0, le=2.0)


class LiteLLMCompletionParams(BaseModel):
    """Completion parameters for LiteLLM provider."""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    model: ModelId | None = None
    max_tokens: int | None = None
    temperature: float | None = None
    top_p: float | None = None
    frequency_penalty: float | None = None
    presence_penalty: float | None = None
    response_format: type[BaseModel] | dict[str, Any] | None = None


class LiteLLMProvider(LLMProvider[LiteLLMProviderSettings, LiteLLMCompletionParams]):
    """
    Unified LLM provider using LiteLLM.

    LiteLLM handles model prefixes, parameter translation, and provider-specific
    quirks internally. Models can be specified with or without provider prefixes
    (e.g., "gpt-5.1" or "openai/gpt-5.1").
    """

    def __init__(
        self,
        api_key: str | None,
        default_model: str,
        settings: LiteLLMProviderSettings,
        provider_name: str = "litellm",
    ) -> None:
        """
        Initialize LiteLLM provider.

        Args:
            api_key: API key for the underlying provider (None for ADC-based providers like Vertex AI)
            default_model: Default model (e.g., "gpt-5.1", "claude-3-opus-20240229")
            settings: Provider settings
            provider_name: Name of the underlying provider for tracking (e.g., "openai", "anthropic")
        """
        super().__init__(api_key, default_model, settings)
        self._provider_name = provider_name
        litellm.drop_params = True
        litellm.enable_json_schema_validation = True

    def _filter_none_params(self, params: dict[str, Any]) -> dict[str, Any]:
        """
        Filter out None values from parameters.

        This is critical for cross-provider compatibility. Some providers
        (e.g., Anthropic) reject parameters with None values even if they're
        optional. By filtering None values, we avoid the presence_penalty bug
        where passing None to Anthropic causes API errors.

        Args:
            params: Dictionary of parameters that may contain None values

        Returns:
            Dictionary with only non-None values
        """
        return {k: v for k, v in params.items() if v is not None}

    async def complete(
        self, messages: list[LLMMessage], params: LiteLLMCompletionParams | None = None
    ) -> LLMResponse:
        """
        Generate a completion using LiteLLM's unified API.

        Args:
            messages: Conversation messages
            params: Completion parameters (uses defaults from settings if not provided)

        Returns:
            LLMResponse with generated content

        Raises:
            ValueError: If model name is empty after fallback resolution
            Exception: If API call fails
        """
        params = params or LiteLLMCompletionParams()
        model_str = params.model.to_litellm() if params.model else self.default_model

        if not model_str:
            raise ValueError(
                "Model name cannot be empty. Check that RELEVANCE_CHECK_MODEL, "
                "DEFAULT_FULL_MODEL, or other model configuration is set correctly."
            )

        request_kwargs = self._filter_none_params(
            {
                "model": model_str,
                "messages": [{"role": m.role, "content": m.content} for m in messages],
                "max_tokens": params.max_tokens or self.settings.max_tokens,
                "temperature": params.temperature
                if params.temperature is not None
                else self.settings.temperature,
                "top_p": params.top_p,
                "frequency_penalty": params.frequency_penalty,
                "presence_penalty": params.presence_penalty,
                "response_format": params.response_format,
                "timeout": self.settings.timeout,
            }
        )
        if self.api_key and self._provider_name not in ("vertex_ai", "gemini"):
            request_kwargs["api_key"] = self.api_key

        logger.debug(
            "LiteLLM completion request",
            extra={
                "model": model_str,
                "has_response_format": params.response_format is not None,
                "max_tokens": request_kwargs.get("max_tokens"),
                "message_count": len(messages),
            },
        )

        try:
            response = await litellm.acompletion(**request_kwargs)
        except JSONSchemaValidationError as e:
            logger.exception(
                "LiteLLM JSON schema validation failed",
                extra={
                    "model": model_str,
                    "response_format": str(params.response_format)
                    if params.response_format
                    else None,
                    "raw_response": getattr(e, "raw_response", None),
                    "error": str(e),
                },
            )
            raise

        tokens_used = response.usage.total_tokens if response.usage else 0  # pyright: ignore[reportAttributeAccessIssue]
        finish_reason = response.choices[0].finish_reason or "stop"  # pyright: ignore[reportAttributeAccessIssue]
        content = response.choices[0].message.content or ""  # pyright: ignore[reportAttributeAccessIssue]
        content_length = len(content)

        logger.info(
            "LLM completion finished",
            extra={
                "model": model_str,
                "finish_reason": finish_reason,
                "content_length": content_length,
                "tokens_used": tokens_used,
            },
        )

        if not content:
            logger.warning(
                "LLM returned empty content",
                extra={"finish_reason": finish_reason, "model": model_str},
            )

        return LLMResponse(
            content=content,
            model=response.model or model_str,  # type: ignore
            tokens_used=tokens_used,
            finish_reason=finish_reason,
            provider=self._provider_name,
        )

    async def stream_complete(
        self, messages: list[LLMMessage], params: LiteLLMCompletionParams | None = None
    ) -> AsyncGenerator[str, None]:
        """
        Generate a streaming completion using LiteLLM.

        Args:
            messages: Conversation messages
            params: Completion parameters (uses defaults from settings if not provided)

        Yields:
            Content chunks as they are generated

        Raises:
            ValueError: If model name is empty after fallback resolution
        """
        params = params or LiteLLMCompletionParams()
        model_str = params.model.to_litellm() if params.model else self.default_model

        if not model_str:
            raise ValueError(
                "Model name cannot be empty. Check that model configuration is set correctly."
            )

        request_kwargs = self._filter_none_params(
            {
                "model": model_str,
                "messages": [{"role": m.role, "content": m.content} for m in messages],
                "max_tokens": params.max_tokens or self.settings.max_tokens,
                "temperature": params.temperature
                if params.temperature is not None
                else self.settings.temperature,
                "top_p": params.top_p,
                "frequency_penalty": params.frequency_penalty,
                "presence_penalty": params.presence_penalty,
                "stream": True,
                "timeout": self.settings.timeout,
            }
        )
        if self.api_key and self._provider_name not in ("vertex_ai", "gemini"):
            request_kwargs["api_key"] = self.api_key

        try:
            response = await litellm.acompletion(**request_kwargs)
        except JSONSchemaValidationError as e:
            logger.exception(
                "LiteLLM JSON schema validation failed in stream_complete",
                extra={
                    "model": model_str,
                    "raw_response": getattr(e, "raw_response", None),
                    "error": str(e),
                },
            )
            raise

        async for chunk in response:  # pyright: ignore[reportGeneralTypeIssues]
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    async def validate_api_key(self) -> bool:
        """
        Validate the API key by making a minimal request.

        For vertex_ai/gemini providers, returns True since ADC validation
        is handled by the Google auth SDK, not by API key testing.

        Returns:
            True if API key is valid, False otherwise
        """
        if self._provider_name in ("vertex_ai", "gemini"):
            return True
        try:
            await litellm.acompletion(
                model=self.default_model,
                messages=[{"role": "user", "content": "test"}],
                max_tokens=1,
                api_key=self.api_key,
            )
            return True
        except Exception:
            return False

    async def close(self) -> None:
        """Close the provider and clean up API key."""
        await super().close()
