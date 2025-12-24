"""Unit tests for OpenAI provider."""

import pytest

from src.llm_config.providers.openai_provider import OpenAIProvider


class TestReasoningModelDetection:
    """Tests for reasoning model detection logic."""

    @pytest.mark.parametrize(
        ("model", "expected"),
        [
            ("o1", True),
            ("o1-mini", True),
            ("o1-preview", True),
            ("o3", True),
            ("o3-mini", True),
            ("gpt-5.1", True),
            ("gpt-5", True),
            ("gpt-5-turbo", True),
            ("gpt-4", False),
            ("gpt-4o", False),
            ("gpt-4o-mini", False),
            ("gpt-4-turbo", False),
            ("gpt-3.5-turbo", False),
            ("claude-3-opus", False),
        ],
    )
    def test_is_reasoning_model(self, model: str, expected: bool) -> None:
        """Test reasoning model detection for various model names."""
        assert OpenAIProvider._is_reasoning_model(model) == expected
