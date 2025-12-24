"""Unit tests for LLM provider factory."""

import pytest

from src.llm_config.providers.factory import LLMProviderFactory
from src.llm_config.providers.litellm_provider import LiteLLMProvider


class TestLLMProviderFactoryCreate:
    """Tests for factory.create() method."""

    def test_create_openai_returns_litellm_provider(self) -> None:
        """Creating an openai provider should return LiteLLMProvider."""
        provider = LLMProviderFactory.create(
            provider_name="openai",
            api_key="test-key",
            default_model="gpt-4o",
            settings={"timeout": 30.0},
        )
        assert isinstance(provider, LiteLLMProvider)
        assert provider.default_model == "gpt-4o"
        assert provider._provider_name == "openai"

    def test_create_anthropic_returns_litellm_provider(self) -> None:
        """Creating an anthropic provider should return LiteLLMProvider."""
        provider = LLMProviderFactory.create(
            provider_name="anthropic",
            api_key="test-key",
            default_model="claude-3-opus-20240229",
            settings={"timeout": 30.0},
        )
        assert isinstance(provider, LiteLLMProvider)
        assert provider.default_model == "claude-3-opus-20240229"
        assert provider._provider_name == "anthropic"

    def test_create_vertex_ai_returns_litellm_provider(self) -> None:
        """Creating a vertex_ai provider should return LiteLLMProvider."""
        provider = LLMProviderFactory.create(
            provider_name="vertex_ai",
            api_key="test-key",
            default_model="gemini-2.5-pro",
            settings={"timeout": 30.0},
        )
        assert isinstance(provider, LiteLLMProvider)
        assert provider.default_model == "gemini-2.5-pro"
        assert provider._provider_name == "vertex_ai"

    def test_create_gemini_returns_litellm_provider(self) -> None:
        """Creating a gemini provider should return LiteLLMProvider."""
        provider = LLMProviderFactory.create(
            provider_name="gemini",
            api_key="test-key",
            default_model="gemini-1.5-pro",
            settings={"timeout": 30.0},
        )
        assert isinstance(provider, LiteLLMProvider)
        assert provider.default_model == "gemini-1.5-pro"
        assert provider._provider_name == "gemini"

    def test_create_litellm_provider(self) -> None:
        """Creating a litellm provider should return LiteLLMProvider."""
        provider = LLMProviderFactory.create(
            provider_name="litellm",
            api_key="test-key",
            default_model="openai/gpt-4o",
            settings={"timeout": 30.0},
        )
        assert isinstance(provider, LiteLLMProvider)
        assert provider.default_model == "openai/gpt-4o"
        assert provider._provider_name == "litellm"

    def test_unknown_provider_raises_valueerror(self) -> None:
        """Unknown provider should raise ValueError."""
        with pytest.raises(ValueError, match=r"Unknown provider.*unknown_provider"):
            LLMProviderFactory.create(
                provider_name="unknown_provider",
                api_key="test-key",
                default_model="some-model",
                settings={},
            )

    def test_settings_are_applied(self) -> None:
        """Provider should have custom settings applied."""
        provider = LLMProviderFactory.create(
            provider_name="openai",
            api_key="test-key",
            default_model="gpt-4o",
            settings={"timeout": 60.0, "max_tokens": 2048, "temperature": 0.5},
        )
        assert provider.settings.timeout == 60.0
        assert provider.settings.max_tokens == 2048
        assert provider.settings.temperature == 0.5


class TestListProviders:
    """Tests for list_providers() method."""

    def test_lists_all_registered_providers(self) -> None:
        """Should list all registered providers."""
        providers = LLMProviderFactory.list_providers()
        assert "openai" in providers
        assert "anthropic" in providers
        assert "litellm" in providers
        assert "vertex_ai" in providers
        assert "gemini" in providers


class TestRegisterProvider:
    """Tests for register_provider() method."""

    def test_register_custom_provider(self) -> None:
        """Should be able to register a custom provider."""
        original_providers = LLMProviderFactory._providers.copy()
        try:
            LLMProviderFactory.register_provider("custom", LiteLLMProvider)
            assert "custom" in LLMProviderFactory.list_providers()
        finally:
            LLMProviderFactory._providers = original_providers
