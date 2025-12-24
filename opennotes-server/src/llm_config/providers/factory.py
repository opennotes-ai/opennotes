"""Factory for creating LLM provider instances."""

from typing import Any, ClassVar

from src.llm_config.providers.base import LLMProvider
from src.llm_config.providers.litellm_provider import (
    LiteLLMProvider,
    LiteLLMProviderSettings,
)

MODEL_PREFIXES: dict[str, str] = {
    "openai": "openai/",
    "anthropic": "anthropic/",
    "vertex_ai": "vertex_ai/",
    "gemini": "gemini/",
    "litellm": "",
}


class LLMProviderFactory:
    """
    Factory for creating LLM provider instances.

    Supports dynamic registration of custom providers.
    """

    _providers: ClassVar[dict[str, type[LLMProvider[Any, Any]]]] = {
        "openai": LiteLLMProvider,
        "anthropic": LiteLLMProvider,
        "vertex_ai": LiteLLMProvider,
        "gemini": LiteLLMProvider,
        "litellm": LiteLLMProvider,
    }

    @classmethod
    def _to_litellm_model(cls, provider_name: str, model: str) -> str:
        """
        Convert model name to litellm format with provider prefix.

        Args:
            provider_name: Provider identifier
            model: Model name (may or may not have prefix)

        Returns:
            Model name with appropriate prefix for litellm
        """
        prefix = MODEL_PREFIXES.get(provider_name, "")
        if prefix and not model.startswith(prefix):
            return f"{prefix}{model}"
        return model

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
        litellm_model = cls._to_litellm_model(provider_name, default_model)
        return provider_class(api_key, litellm_model, typed_settings)

    @classmethod
    def _create_typed_settings(
        cls,
        provider_name: str,  # noqa: ARG003
        settings: dict[str, Any],
    ) -> LiteLLMProviderSettings:
        """
        Convert dictionary settings to LiteLLMProviderSettings.

        All providers now use LiteLLMProvider, so settings are unified.

        Args:
            provider_name: Provider identifier (unused, kept for API compatibility)
            settings: Settings dictionary

        Returns:
            LiteLLMProviderSettings instance
        """
        return LiteLLMProviderSettings(**settings)

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
