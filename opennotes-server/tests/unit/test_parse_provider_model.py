"""Unit tests for parse_provider_model() in config.py."""

import pytest

from src.config import parse_provider_model


class TestParseProviderModel:
    """Tests for parse_provider_model splitting provider/model strings."""

    def test_vertex_ai_gemini_flash(self) -> None:
        provider, model = parse_provider_model("vertex_ai/gemini-2.5-flash")
        assert provider == "vertex_ai"
        assert model == "gemini-2.5-flash"

    def test_openai_gpt(self) -> None:
        provider, model = parse_provider_model("openai/gpt-5.1")
        assert provider == "openai"
        assert model == "gpt-5.1"

    def test_bare_model_defaults_to_openai(self) -> None:
        provider, model = parse_provider_model("gpt-5.1")
        assert provider == "openai"
        assert model == "gpt-5.1"

    def test_anthropic_claude(self) -> None:
        provider, model = parse_provider_model("anthropic/claude-3-opus")
        assert provider == "anthropic"
        assert model == "claude-3-opus"

    def test_empty_string_defaults_to_openai(self) -> None:
        provider, model = parse_provider_model("")
        assert provider == "openai"
        assert model == ""

    def test_vertex_ai_gemini_pro(self) -> None:
        provider, model = parse_provider_model("vertex_ai/gemini-2.5-pro")
        assert provider == "vertex_ai"
        assert model == "gemini-2.5-pro"

    def test_gemini_provider(self) -> None:
        provider, model = parse_provider_model("gemini/gemini-2.5-flash")
        assert provider == "gemini"
        assert model == "gemini-2.5-flash"

    def test_model_with_multiple_slashes(self) -> None:
        provider, model = parse_provider_model("org/model/version")
        assert provider == "org"
        assert model == "model/version"

    def test_openai_mini_model(self) -> None:
        provider, model = parse_provider_model("openai/gpt-5-mini")
        assert provider == "openai"
        assert model == "gpt-5-mini"

    @pytest.mark.parametrize(
        ("input_str", "expected_provider", "expected_model"),
        [
            ("vertex_ai/gemini-2.5-flash", "vertex_ai", "gemini-2.5-flash"),
            ("openai/gpt-5.1", "openai", "gpt-5.1"),
            ("gpt-5.1", "openai", "gpt-5.1"),
            ("anthropic/claude-3-opus", "anthropic", "claude-3-opus"),
            ("", "openai", ""),
        ],
    )
    def test_parametrized(
        self, input_str: str, expected_provider: str, expected_model: str
    ) -> None:
        provider, model = parse_provider_model(input_str)
        assert provider == expected_provider
        assert model == expected_model
