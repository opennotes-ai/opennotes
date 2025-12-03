"""
Base provider interface for LLM integrations.

Defines the abstract interface that all LLM providers must implement,
enabling consistent interaction with different LLM services.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict


class LLMMessage(BaseModel):
    """
    A message in an LLM conversation.

    Attributes:
        role: Message role ('system', 'user', 'assistant')
        content: Message content
    """

    role: str
    content: str


class LLMResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    """
    Response from an LLM completion request.

    Attributes:
        content: Generated response content
        model: Model that generated the response
        tokens_used: Total tokens consumed (input + output)
        finish_reason: Why the model stopped generating ('stop', 'length', etc.)
        provider: Provider name that generated this response
    """

    content: str
    model: str
    tokens_used: int
    finish_reason: str
    provider: str


class ProviderSettings(BaseModel):
    """Base settings for LLM providers."""

    model_config = ConfigDict(extra="forbid")


SettingsT = TypeVar("SettingsT", bound=ProviderSettings)
CompletionParamsT = TypeVar("CompletionParamsT", bound=BaseModel)


class LLMProvider(ABC, Generic[SettingsT, CompletionParamsT]):
    """
    Abstract base class for LLM provider implementations.

    All LLM providers (OpenAI, Anthropic, etc.) must implement this interface
    to ensure consistent behavior across different services.

    Type Parameters:
        SettingsT: Provider-specific settings type
        CompletionParamsT: Provider-specific completion parameters type
    """

    def __init__(self, api_key: str, default_model: str, settings: SettingsT) -> None:
        """
        Initialize LLM provider.

        Args:
            api_key: API key for authentication
            default_model: Default model to use for completions
            settings: Provider-specific settings
        """
        self.api_key = api_key
        self.default_model = default_model
        self.settings = settings

    @abstractmethod
    async def complete(
        self, messages: list[LLMMessage], params: CompletionParamsT | None = None
    ) -> LLMResponse:
        """
        Generate a completion for the given messages.

        Args:
            messages: List of conversation messages
            params: Provider-specific completion parameters

        Returns:
            LLMResponse with generated content and metadata

        Raises:
            Exception: If API call fails
        """

    @abstractmethod
    def stream_complete(
        self, messages: list[LLMMessage], params: CompletionParamsT | None = None
    ) -> AsyncGenerator[str, None]:
        """
        Generate a streaming completion for the given messages.

        Args:
            messages: List of conversation messages
            params: Provider-specific completion parameters

        Yields:
            Content chunks as they are generated

        Raises:
            Exception: If API call fails
        """
        ...

    @abstractmethod
    async def validate_api_key(self) -> bool:
        """
        Validate that the API key is valid and functional.

        Returns:
            True if API key is valid, False otherwise
        """

    async def close(self) -> None:
        """
        Close the provider and clean up any resources.

        Providers should override this to close HTTP clients and connections.
        This method also clears the API key from memory to prevent leakage.

        Note: Subclasses that override this method MUST call super().close()
        to ensure proper cleanup of sensitive data.
        """
        self._clear_api_key()

    def _clear_api_key(self) -> None:
        """
        Clear the API key from memory.

        Python strings are immutable, so we cannot truly zero the original string.
        However, we can:
        1. Remove the reference from this object
        2. Set it to an empty string to make the object unusable

        The original string will be garbage collected when no other references exist.
        For truly secure handling, use SecureString from the secure_string module.
        """
        self.api_key = ""
