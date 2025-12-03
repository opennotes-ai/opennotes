"""Factory for creating LLM provider instances."""

from typing import Any, ClassVar

from src.llm_config.providers.anthropic_provider import (
    AnthropicProvider,
    AnthropicProviderSettings,
)
from src.llm_config.providers.base import LLMProvider
from src.llm_config.providers.openai_provider import (
    OpenAIProvider,
    OpenAIProviderSettings,
)


class LLMProviderFactory:
    """
    Factory for creating LLM provider instances.

    Supports dynamic registration of custom providers.
    """

    _providers: ClassVar[dict[str, type[LLMProvider[Any, Any]]]] = {
        "openai": OpenAIProvider,
        "anthropic": AnthropicProvider,
    }

    @classmethod
    def create(
        cls, provider_name: str, api_key: str, default_model: str, settings: dict[str, Any]
    ) -> LLMProvider[Any, Any]:
        """
        Create an LLM provider instance.

        Args:
            provider_name: Provider identifier ('openai', 'anthropic', etc.)
            api_key: API key for the provider
            default_model: Default model to use
            settings: Provider-specific settings as a dictionary

        Returns:
            Initialized LLM provider instance

        Raises:
            ValueError: If provider is not registered or settings are invalid
        """
        provider_class = cls._providers.get(provider_name)
        if not provider_class:
            raise ValueError(
                f"Unknown provider: {provider_name}. "
                f"Available providers: {', '.join(cls._providers.keys())}"
            )

        typed_settings = cls._create_typed_settings(provider_name, settings)
        return provider_class(api_key, default_model, typed_settings)

    @classmethod
    def _create_typed_settings(cls, provider_name: str, settings: dict[str, Any]) -> Any:
        """
        Convert dictionary settings to typed provider settings.

        Args:
            provider_name: Provider identifier
            settings: Settings dictionary

        Returns:
            Typed settings instance for the provider

        Raises:
            ValueError: If settings are invalid for the provider
        """
        if provider_name == "openai":
            return OpenAIProviderSettings(**settings)
        if provider_name == "anthropic":
            return AnthropicProviderSettings(**settings)
        raise ValueError(f"No settings class defined for provider: {provider_name}")

    @classmethod
    def register_provider(cls, name: str, provider_class: type[LLMProvider[Any, Any]]) -> None:
        """
        Register a custom LLM provider.

        Args:
            name: Provider identifier
            provider_class: Provider class implementing LLMProvider interface
        """
        cls._providers[name] = provider_class

    @classmethod
    def list_providers(cls) -> list[str]:
        """
        List all registered provider names.

        Returns:
            List of provider identifiers
        """
        return list(cls._providers.keys())
