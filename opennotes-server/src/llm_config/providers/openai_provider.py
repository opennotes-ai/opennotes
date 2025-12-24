"""OpenAI LLM provider implementation."""

from collections.abc import AsyncGenerator

from openai import AsyncOpenAI
from pydantic import BaseModel, ConfigDict, Field

from src.llm_config.providers.base import LLMMessage, LLMProvider, LLMResponse, ProviderSettings
from src.monitoring import get_logger

logger = get_logger(__name__)


class OpenAIProviderSettings(ProviderSettings):
    """Settings for OpenAI provider."""

    model_config = ConfigDict(extra="forbid")

    organization_id: str | None = Field(None, description="OpenAI organization ID")
    base_url: str | None = Field(None, description="Custom API base URL")
    timeout: float = Field(30.0, description="Request timeout in seconds", gt=0)
    max_tokens: int = Field(4096, description="Default max tokens to generate", gt=0)
    temperature: float = Field(0.7, description="Default sampling temperature", ge=0.0, le=2.0)


class OpenAICompletionParams(BaseModel):
    """Completion parameters for OpenAI provider."""

    model_config = ConfigDict(extra="forbid")

    model: str | None = None
    max_tokens: int | None = None
    temperature: float | None = None
    top_p: float | None = None
    frequency_penalty: float | None = None
    presence_penalty: float | None = None


# Prefixes for OpenAI reasoning models that require max_completion_tokens instead of max_tokens
REASONING_MODEL_PREFIXES = ("o1", "o3", "gpt-5")


class OpenAIProvider(LLMProvider[OpenAIProviderSettings, OpenAICompletionParams]):
    """
    OpenAI API provider implementation.

    Supports GPT-4, GPT-3.5-turbo, and other OpenAI models.
    Also supports reasoning models (o1, o3, gpt-5) which require max_completion_tokens.
    """

    @staticmethod
    def _is_reasoning_model(model: str) -> bool:
        """
        Check if a model is a reasoning model that uses max_completion_tokens.

        OpenAI reasoning models (o1, o3, gpt-5 families) require max_completion_tokens
        instead of the traditional max_tokens parameter.

        Args:
            model: Model identifier

        Returns:
            True if model is a reasoning model
        """
        return model.startswith(REASONING_MODEL_PREFIXES)

    def __init__(self, api_key: str, default_model: str, settings: OpenAIProviderSettings) -> None:
        """
        Initialize OpenAI provider.

        Args:
            api_key: OpenAI API key
            default_model: Default model (e.g., 'gpt-4-turbo-preview')
            settings: Provider settings
        """
        super().__init__(api_key, default_model, settings)
        self.client = AsyncOpenAI(
            api_key=api_key,
            organization=settings.organization_id,
            base_url=settings.base_url,
            timeout=settings.timeout,
        )

    async def complete(
        self, messages: list[LLMMessage], params: OpenAICompletionParams | None = None
    ) -> LLMResponse:
        """
        Generate a completion using OpenAI's chat completion API.

        Args:
            messages: Conversation messages
            params: Completion parameters (uses defaults from settings if not provided)

        Returns:
            LLMResponse with generated content

        Raises:
            openai.APIError: If API call fails
        """
        params = params or OpenAICompletionParams()
        model = params.model or self.default_model
        max_tokens_value = params.max_tokens or self.settings.max_tokens

        # Build request kwargs - reasoning models use max_completion_tokens
        request_kwargs: dict = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": params.temperature
            if params.temperature is not None
            else self.settings.temperature,
            "top_p": params.top_p,
            "frequency_penalty": params.frequency_penalty,
            "presence_penalty": params.presence_penalty,
        }

        if self._is_reasoning_model(model):
            request_kwargs["max_completion_tokens"] = max_tokens_value
        else:
            request_kwargs["max_tokens"] = max_tokens_value

        response = await self.client.chat.completions.create(**request_kwargs)  # type: ignore[arg-type]

        # Handle missing usage data
        if not response.usage:
            logger.warning(
                "OpenAI response missing usage data",
                extra={"model": response.model, "finish_reason": response.choices[0].finish_reason},
            )
            tokens_used = 0
        else:
            tokens_used = response.usage.total_tokens

        return LLMResponse(
            content=response.choices[0].message.content or "",
            model=response.model,
            tokens_used=tokens_used,
            finish_reason=response.choices[0].finish_reason,
            provider="openai",
        )

    async def stream_complete(
        self, messages: list[LLMMessage], params: OpenAICompletionParams | None = None
    ) -> AsyncGenerator[str, None]:
        """
        Generate a streaming completion using OpenAI's API.

        Args:
            messages: Conversation messages
            params: Completion parameters (uses defaults from settings if not provided)

        Yields:
            Content chunks as they are generated
        """
        params = params or OpenAICompletionParams()
        model = params.model or self.default_model
        max_tokens_value = params.max_tokens or self.settings.max_tokens

        # Build request kwargs - reasoning models use max_completion_tokens
        request_kwargs: dict = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": params.temperature
            if params.temperature is not None
            else self.settings.temperature,
            "stream": True,
        }

        if self._is_reasoning_model(model):
            request_kwargs["max_completion_tokens"] = max_tokens_value
        else:
            request_kwargs["max_tokens"] = max_tokens_value

        stream = await self.client.chat.completions.create(**request_kwargs)  # type: ignore[arg-type]

        async for chunk in stream:  # type: ignore[union-attr]
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    async def validate_api_key(self) -> bool:
        """
        Validate OpenAI API key by listing models.

        Returns:
            True if API key is valid
        """
        try:
            await self.client.models.list()
            return True
        except Exception:
            return False

    async def close(self) -> None:
        """Close the OpenAI client and clean up HTTP connections and API key."""
        await self.client.close()
        await super().close()
