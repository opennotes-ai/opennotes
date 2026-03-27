from typing import Any, ClassVar

from src.llm_config.providers.base import LLMProvider
from src.llm_config.providers.direct_provider import (
    DirectProvider,
    DirectProviderSettings,
)


class LLMProviderFactory:
    _providers: ClassVar[dict[str, type[LLMProvider[Any, Any]]]] = {
        "openai": DirectProvider,
        "anthropic": DirectProvider,
        "vertex_ai": DirectProvider,
        "gemini": DirectProvider,
    }

    @classmethod
    def create(
        cls, provider_name: str, api_key: str, default_model: str, settings: dict[str, Any]
    ) -> LLMProvider[Any, Any]:
        provider_class = cls._providers.get(provider_name)
        if not provider_class:
            raise ValueError(
                f"Unknown provider: {provider_name}. "
                f"Available providers: {', '.join(cls._providers.keys())}"
            )

        typed_settings = cls._create_typed_settings(provider_name, settings)
        if provider_class is DirectProvider:
            return DirectProvider(
                api_key, default_model, typed_settings, provider_name=provider_name
            )
        return provider_class(api_key, default_model, typed_settings)

    @classmethod
    def _create_typed_settings(
        cls,
        provider_name: str,  # noqa: ARG003
        settings: dict[str, Any],
    ) -> DirectProviderSettings:
        return DirectProviderSettings(**settings)

    @classmethod
    def register_provider(cls, name: str, provider_class: type[LLMProvider[Any, Any]]) -> None:
        cls._providers[name] = provider_class

    @classmethod
    def list_providers(cls) -> list[str]:
        return list(cls._providers.keys())
