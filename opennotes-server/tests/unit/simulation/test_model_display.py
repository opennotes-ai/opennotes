from __future__ import annotations

import pytest

from src.simulation.model_display import humanize_model_name
from tests._model_fixtures import GOOGLE_VERTEX_FLASH_TEST_MODEL

pytestmark = pytest.mark.unit


class TestHumanizeModelName:
    def test_vertex_ai_gemini(self):
        assert humanize_model_name("vertex_ai/gemini-2.5-flash") == "Google Gemini 2.5 Flash"

    def test_azure_gpt(self):
        assert humanize_model_name("azure/gpt-4o") == "OpenAI GPT 4o"

    def test_bedrock_claude(self):
        assert (
            humanize_model_name("bedrock/anthropic.claude-3-5-sonnet")
            == "Anthropic Claude 3.5 Sonnet"
        )

    def test_bare_gpt(self):
        assert humanize_model_name("gpt-4o") == "OpenAI GPT 4o"

    def test_bare_gemini(self):
        assert humanize_model_name("gemini-2.5-flash") == "Google Gemini 2.5 Flash"

    def test_bare_anthropic_dot_claude(self):
        assert humanize_model_name("anthropic.claude-3-5-sonnet") == "Anthropic Claude 3.5 Sonnet"

    def test_unknown_model_fallback(self):
        assert humanize_model_name("some-unknown-model") == "some-unknown-model"

    def test_empty_string(self):
        assert humanize_model_name("") == ""

    def test_openrouter_prefix_stripped(self):
        assert humanize_model_name("openrouter/gpt-4o") == "OpenAI GPT 4o"

    def test_gemini_pro_variant(self):
        assert humanize_model_name("gemini-1.5-pro") == "Google Gemini 1.5 Pro"

    def test_claude_without_anthropic_dot(self):
        assert humanize_model_name("claude-3-5-sonnet") == "Anthropic Claude 3.5 Sonnet"

    def test_gpt_4_turbo(self):
        assert humanize_model_name("gpt-4-turbo") == "OpenAI GPT 4 Turbo"

    def test_version_number_dot_separator(self):
        result = humanize_model_name("vertex_ai/gemini-1.5-flash")
        assert result == "Google Gemini 1.5 Flash"

    def test_pydantic_ai_openai(self):
        assert humanize_model_name("openai:gpt-4o-mini") == "OpenAI GPT 4o Mini"

    def test_pydantic_ai_anthropic(self):
        assert humanize_model_name("anthropic:claude-3-5-sonnet") == "Anthropic Claude 3.5 Sonnet"

    def test_pydantic_ai_google_vertex(self):
        assert humanize_model_name(GOOGLE_VERTEX_FLASH_TEST_MODEL) == "Google Gemini 3 Flash"

    def test_pydantic_ai_mistral(self):
        assert humanize_model_name("mistral:mistral-large-latest") == "Mistral Large Latest"

    def test_pydantic_ai_unknown_provider(self):
        assert humanize_model_name("deepseek:deepseek-chat") == "Deepseek Deepseek Chat"

    def test_mistral_bare_no_vendor_duplication(self):
        assert humanize_model_name("mistral-large-latest") == "Mistral Large Latest"
