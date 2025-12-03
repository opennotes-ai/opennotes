"""Anthropic LLM provider implementation."""

from collections.abc import AsyncGenerator

from anthropic import AsyncAnthropic
from anthropic.types import TextBlock
from pydantic import BaseModel, ConfigDict, Field

from src.llm_config.providers.base import LLMMessage, LLMProvider, LLMResponse, ProviderSettings
from src.monitoring import get_logger

logger = get_logger(__name__)


class AnthropicProviderSettings(ProviderSettings):
    """Settings for Anthropic provider."""

    model_config = ConfigDict(extra="forbid")

    api_version: str | None = Field(None, description="API version (default: latest)")
    timeout: float = Field(30.0, description="Request timeout in seconds", gt=0)
    max_tokens: int = Field(4096, description="Default max tokens to generate", gt=0)
    temperature: float = Field(0.7, description="Default sampling temperature", ge=0.0, le=1.0)


class AnthropicCompletionParams(BaseModel):
    """Completion parameters for Anthropic provider."""

    model_config = ConfigDict(extra="forbid")

    model: str | None = None
    max_tokens: int | None = None
    temperature: float | None = None
    top_p: float | None = None
    top_k: int | None = None


class AnthropicProvider(LLMProvider[AnthropicProviderSettings, AnthropicCompletionParams]):
    """
    Anthropic API provider implementation.

    Supports Claude 3 models (Opus, Sonnet, Haiku).
    """

    def __init__(
        self, api_key: str, default_model: str, settings: AnthropicProviderSettings
    ) -> None:
        """
        Initialize Anthropic provider.

        Args:
            api_key: Anthropic API key
            default_model: Default model (e.g., 'claude-3-opus-20240229')
            settings: Provider settings
        """
        super().__init__(api_key, default_model, settings)
        self.client = AsyncAnthropic(
            api_key=api_key,
            timeout=settings.timeout,
        )

    async def complete(
        self, messages: list[LLMMessage], params: AnthropicCompletionParams | None = None
    ) -> LLMResponse:
        """
        Generate a completion using Anthropic's messages API.

        Anthropic requires system messages to be provided separately from
        the conversation messages.

        Args:
            messages: Conversation messages
            params: Completion parameters (uses defaults from settings if not provided)

        Returns:
            LLMResponse with generated content

        Raises:
            anthropic.APIError: If API call fails
        """
        params = params or AnthropicCompletionParams()

        system_msg = next((m.content for m in messages if m.role == "system"), None)
        user_messages = [m for m in messages if m.role != "system"]

        response = await self.client.messages.create(
            model=params.model or self.default_model,
            system=system_msg,  # type: ignore[arg-type]
            messages=[{"role": m.role, "content": m.content} for m in user_messages],  # type: ignore[typeddict-item]
            max_tokens=params.max_tokens or self.settings.max_tokens,
            temperature=params.temperature
            if params.temperature is not None
            else self.settings.temperature,
            top_p=params.top_p,  # type: ignore[arg-type]
            top_k=params.top_k,  # type: ignore[arg-type]
        )

        # Handle missing usage data
        if not response.usage:
            logger.warning(
                "Anthropic response missing usage data",
                extra={"model": response.model, "stop_reason": response.stop_reason},
            )
            total_tokens = 0
        else:
            total_tokens = response.usage.input_tokens + response.usage.output_tokens

        # Handle missing or empty content
        content = ""
        if response.content and len(response.content) > 0:
            first_block = response.content[0]
            if isinstance(first_block, TextBlock):
                content = first_block.text
        else:
            logger.warning(
                "Anthropic response missing content",
                extra={"model": response.model, "stop_reason": response.stop_reason},
            )

        return LLMResponse(
            content=content,
            model=response.model,
            tokens_used=total_tokens,
            finish_reason=response.stop_reason or "stop",
            provider="anthropic",
        )

    async def stream_complete(
        self, messages: list[LLMMessage], params: AnthropicCompletionParams | None = None
    ) -> AsyncGenerator[str, None]:
        """
        Generate a streaming completion using Anthropic's API.

        Args:
            messages: Conversation messages
            params: Completion parameters (uses defaults from settings if not provided)

        Yields:
            Content chunks as they are generated
        """
        params = params or AnthropicCompletionParams()

        system_msg = next((m.content for m in messages if m.role == "system"), None)
        user_messages = [m for m in messages if m.role != "system"]

        async with self.client.messages.stream(
            model=params.model or self.default_model,
            system=system_msg,  # type: ignore[arg-type]
            messages=[{"role": m.role, "content": m.content} for m in user_messages],  # type: ignore[typeddict-item]
            max_tokens=params.max_tokens or self.settings.max_tokens,
            temperature=params.temperature
            if params.temperature is not None
            else self.settings.temperature,
        ) as stream:
            async for text in stream.text_stream:
                yield text

    async def validate_api_key(self) -> bool:
        """
        Validate Anthropic API key by making a minimal request.

        Returns:
            True if API key is valid
        """
        try:
            await self.client.messages.create(
                model=self.default_model,
                messages=[{"role": "user", "content": "test"}],
                max_tokens=1,
            )
            return True
        except Exception:
            return False

    async def close(self) -> None:
        """Close the Anthropic client and clean up HTTP connections and API key."""
        await self.client.close()
        await super().close()
