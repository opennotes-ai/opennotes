"""Unit tests for LLM provider factory."""

import pytest

from src.llm_config.providers.direct_provider import DirectProvider
from src.llm_config.providers.factory import LLMProviderFactory
from tests._model_fixtures import GOOGLE_VERTEX_PRO_TEST_MODEL


class TestLLMProviderFactoryCreate:
    def test_create_openai_returns_direct_provider(self) -> None:
        provider = LLMProviderFactory.create(
            provider_name="openai",
            api_key="test-key",
            default_model="openai:gpt-5.1",
            settings={"timeout": 30.0},
        )
        assert isinstance(provider, DirectProvider)
        assert provider.default_model == "openai:gpt-5.1"
        assert provider._provider_name == "openai"

    def test_create_anthropic_returns_direct_provider(self) -> None:
        provider = LLMProviderFactory.create(
            provider_name="anthropic",
            api_key="test-key",
            default_model="anthropic:claude-3-opus-20240229",
            settings={"timeout": 30.0},
        )
        assert isinstance(provider, DirectProvider)
        assert provider.default_model == "anthropic:claude-3-opus-20240229"
        assert provider._provider_name == "anthropic"

    def test_create_vertex_ai_returns_direct_provider(self, prod_default_google_model: str) -> None:
        provider = LLMProviderFactory.create(
            provider_name="vertex_ai",
            api_key="test-key",
            default_model=prod_default_google_model,
            settings={"timeout": 30.0},
        )
        assert isinstance(provider, DirectProvider)
        assert provider.default_model == prod_default_google_model
        assert provider._provider_name == "vertex_ai"

    def test_factory_no_longer_registers_gemini(self) -> None:
        assert "gemini" not in LLMProviderFactory._providers
        with pytest.raises(ValueError, match=r"Unknown provider.*gemini"):
            LLMProviderFactory.create(
                provider_name="gemini",
                api_key="test-key",
                default_model=GOOGLE_VERTEX_PRO_TEST_MODEL,
                settings={"timeout": 30.0},
            )

    def test_unknown_provider_raises_valueerror(self) -> None:
        with pytest.raises(ValueError, match=r"Unknown provider.*unknown_provider"):
            LLMProviderFactory.create(
                provider_name="unknown_provider",
                api_key="test-key",
                default_model="some-model",
                settings={},
            )

    def test_settings_are_applied(self) -> None:
        provider = LLMProviderFactory.create(
            provider_name="openai",
            api_key="test-key",
            default_model="openai:gpt-5.1",
            settings={"timeout": 60.0, "max_tokens": 2048, "temperature": 0.5},
        )
        assert provider.settings.timeout == 60.0
        assert provider.settings.max_tokens == 2048
        assert provider.settings.temperature == 0.5

    def test_litellm_key_no_longer_registered(self) -> None:
        with pytest.raises(ValueError, match=r"Unknown provider.*litellm"):
            LLMProviderFactory.create(
                provider_name="litellm",
                api_key="test-key",
                default_model="openai:gpt-5.1",
                settings={"timeout": 30.0},
            )


class TestListProviders:
    def test_lists_all_registered_providers(self) -> None:
        providers = LLMProviderFactory.list_providers()
        assert "openai" in providers
        assert "anthropic" in providers
        assert "vertex_ai" in providers

    def test_gemini_not_in_providers(self) -> None:
        providers = LLMProviderFactory.list_providers()
        assert "gemini" not in providers

    def test_litellm_not_in_providers(self) -> None:
        providers = LLMProviderFactory.list_providers()
        assert "litellm" not in providers


class TestRegisterProvider:
    def test_register_custom_provider(self) -> None:
        original_providers = LLMProviderFactory._providers.copy()
        try:
            LLMProviderFactory.register_provider("custom", DirectProvider)
            assert "custom" in LLMProviderFactory.list_providers()
        finally:
            LLMProviderFactory._providers = original_providers
