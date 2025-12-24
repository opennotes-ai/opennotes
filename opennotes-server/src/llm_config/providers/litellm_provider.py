"""LiteLLM unified provider - supports all LLM backends via single interface."""

from collections.abc import AsyncGenerator
from typing import Any

import litellm
from pydantic import BaseModel, ConfigDict, Field

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

    model_config = ConfigDict(extra="forbid")

    model: str | None = None
    max_tokens: int | None = None
    temperature: float | None = None
    top_p: float | None = None
    frequency_penalty: float | None = None
    presence_penalty: float | None = None


class LiteLLMProvider(LLMProvider[LiteLLMProviderSettings, LiteLLMCompletionParams]):
    """
    Unified LLM provider using LiteLLM.

    Supports 100+ LLM providers through a single interface:
    - OpenAI: "openai/gpt-4o", "openai/gpt-4-turbo"
    - Anthropic: "anthropic/claude-3-opus", "anthropic/claude-3-sonnet"
    - Google: "gemini/gemini-1.5-pro"
    - And many more...

    Key advantage: Consistent API across all providers with automatic
    parameter filtering to avoid provider-specific compatibility issues.
    """

    def __init__(self, api_key: str, default_model: str, settings: LiteLLMProviderSettings) -> None:
        """
        Initialize LiteLLM provider.

        Args:
            api_key: API key for the underlying provider
            default_model: Default model in "provider/model" format (e.g., "openai/gpt-4o")
            settings: Provider settings
        """
        super().__init__(api_key, default_model, settings)
        self._provider_prefix = default_model.split("/")[0] if "/" in default_model else "openai"

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
            Exception: If API call fails
        """
        params = params or LiteLLMCompletionParams()
        model = params.model or self.default_model

        request_kwargs = self._filter_none_params(
            {
                "model": model,
                "messages": [{"role": m.role, "content": m.content} for m in messages],
                "max_tokens": params.max_tokens or self.settings.max_tokens,
                "temperature": params.temperature
                if params.temperature is not None
                else self.settings.temperature,
                "top_p": params.top_p,
                "frequency_penalty": params.frequency_penalty,
                "presence_penalty": params.presence_penalty,
                "api_key": self.api_key,
                "timeout": self.settings.timeout,
            }
        )

        response = await litellm.acompletion(**request_kwargs)

        tokens_used = response.usage.total_tokens if response.usage else 0  # type: ignore[union-attr]

        return LLMResponse(
            content=response.choices[0].message.content or "",  # type: ignore[union-attr]
            model=response.model or model,  # type: ignore[arg-type]
            tokens_used=tokens_used,
            finish_reason=response.choices[0].finish_reason or "stop",  # type: ignore[union-attr]
            provider="litellm",
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
        """
        params = params or LiteLLMCompletionParams()
        model = params.model or self.default_model

        request_kwargs = self._filter_none_params(
            {
                "model": model,
                "messages": [{"role": m.role, "content": m.content} for m in messages],
                "max_tokens": params.max_tokens or self.settings.max_tokens,
                "temperature": params.temperature
                if params.temperature is not None
                else self.settings.temperature,
                "stream": True,
                "api_key": self.api_key,
                "timeout": self.settings.timeout,
            }
        )

        response = await litellm.acompletion(**request_kwargs)

        async for chunk in response:  # type: ignore[union-attr]
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    async def validate_api_key(self) -> bool:
        """
        Validate the API key by making a minimal request.

        Returns:
            True if API key is valid, False otherwise
        """
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

    def get_completion_cost(self, response: LLMResponse, prompt: str) -> float:
        """
        Calculate the cost of a completion using LiteLLM's cost tracking.

        Args:
            response: The LLMResponse from a completion call
            prompt: The original prompt text

        Returns:
            Cost in USD as a float
        """
        return litellm.completion_cost(
            model=response.model,
            prompt=prompt,
            completion=response.content,
        )
