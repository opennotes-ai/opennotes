"""Unit tests for LLM provider factory."""

import pytest

from src.llm_config.providers.factory import LLMProviderFactory
from src.llm_config.providers.litellm_provider import LiteLLMProvider


class TestLLMProviderFactoryCreate:
    """Tests for factory.create() method."""

    def test_create_openai_returns_litellm_provider(self) -> None:
        """Creating an openai provider should return LiteLLMProvider with prefixed model."""
        provider = LLMProviderFactory.create(
            provider_name="openai",
            api_key="test-key",
            default_model="gpt-4o",
            settings={"timeout": 30.0},
        )
        assert isinstance(provider, LiteLLMProvider)
        assert provider.default_model == "openai/gpt-4o"

    def test_create_anthropic_returns_litellm_provider(self) -> None:
        """Creating an anthropic provider should return LiteLLMProvider with prefixed model."""
        provider = LLMProviderFactory.create(
            provider_name="anthropic",
            api_key="test-key",
            default_model="claude-3-opus-20240229",
            settings={"timeout": 30.0},
        )
        assert isinstance(provider, LiteLLMProvider)
        assert provider.default_model == "anthropic/claude-3-opus-20240229"

    def test_create_vertex_ai_returns_litellm_provider(self) -> None:
        """Creating a vertex_ai provider should return LiteLLMProvider with prefixed model."""
        provider = LLMProviderFactory.create(
            provider_name="vertex_ai",
            api_key="test-key",
            default_model="gemini-2.5-pro",
            settings={"timeout": 30.0},
        )
        assert isinstance(provider, LiteLLMProvider)
        assert provider.default_model == "vertex_ai/gemini-2.5-pro"

    def test_create_gemini_returns_litellm_provider(self) -> None:
        """Creating a gemini provider should return LiteLLMProvider with prefixed model."""
        provider = LLMProviderFactory.create(
            provider_name="gemini",
            api_key="test-key",
            default_model="gemini-1.5-pro",
            settings={"timeout": 30.0},
        )
        assert isinstance(provider, LiteLLMProvider)
        assert provider.default_model == "gemini/gemini-1.5-pro"

    def test_create_litellm_provider_no_prefix(self) -> None:
        """Creating a litellm provider should not add any prefix."""
        provider = LLMProviderFactory.create(
            provider_name="litellm",
            api_key="test-key",
            default_model="openai/gpt-4o",
            settings={"timeout": 30.0},
        )
        assert isinstance(provider, LiteLLMProvider)
        assert provider.default_model == "openai/gpt-4o"

    def test_unknown_provider_raises_valueerror(self) -> None:
        """Unknown provider should raise ValueError."""
        with pytest.raises(ValueError, match=r"Unknown provider.*unknown_provider"):
            LLMProviderFactory.create(
                provider_name="unknown_provider",
                api_key="test-key",
                default_model="some-model",
                settings={},
            )


class TestToLiteLLMModel:
    """Tests for _to_litellm_model() helper method."""

    def test_adds_openai_prefix(self) -> None:
        """Should add openai/ prefix for openai provider."""
        result = LLMProviderFactory._to_litellm_model("openai", "gpt-4o")
        assert result == "openai/gpt-4o"

    def test_adds_anthropic_prefix(self) -> None:
        """Should add anthropic/ prefix for anthropic provider."""
        result = LLMProviderFactory._to_litellm_model("anthropic", "claude-3-opus")
        assert result == "anthropic/claude-3-opus"

    def test_adds_vertex_ai_prefix(self) -> None:
        """Should add vertex_ai/ prefix for vertex_ai provider."""
        result = LLMProviderFactory._to_litellm_model("vertex_ai", "gemini-2.5-pro")
        assert result == "vertex_ai/gemini-2.5-pro"

    def test_adds_gemini_prefix(self) -> None:
        """Should add gemini/ prefix for gemini provider."""
        result = LLMProviderFactory._to_litellm_model("gemini", "gemini-1.5-flash")
        assert result == "gemini/gemini-1.5-flash"

    def test_no_prefix_for_litellm_provider(self) -> None:
        """Should not add prefix for litellm provider (model already in litellm format)."""
        result = LLMProviderFactory._to_litellm_model("litellm", "openai/gpt-4o")
        assert result == "openai/gpt-4o"

    def test_no_double_prefix_openai(self) -> None:
        """Should not double prefix if model already has openai/ prefix."""
        result = LLMProviderFactory._to_litellm_model("openai", "openai/gpt-4o")
        assert result == "openai/gpt-4o"

    def test_no_double_prefix_anthropic(self) -> None:
        """Should not double prefix if model already has anthropic/ prefix."""
        result = LLMProviderFactory._to_litellm_model("anthropic", "anthropic/claude-3-opus")
        assert result == "anthropic/claude-3-opus"

    def test_unknown_provider_returns_model_unchanged(self) -> None:
        """Unknown provider should return model unchanged (no prefix)."""
        result = LLMProviderFactory._to_litellm_model("custom", "some-model")
        assert result == "some-model"


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
