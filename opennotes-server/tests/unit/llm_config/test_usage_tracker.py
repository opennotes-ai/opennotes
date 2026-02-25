import logging

from src.llm_config.model_id import ModelFlavor
from src.llm_config.usage_tracker import _make_model_id


class TestMakeModelId:
    def test_model_without_slash_prepends_provider(self):
        result = _make_model_id("openai", "gpt-5")
        assert result.provider == "openai"
        assert result.model == "gpt-5"
        assert result.flavor == ModelFlavor.LITELLM

    def test_model_with_slash_uses_model_prefix(self):
        result = _make_model_id("anthropic", "openai/gpt-5")
        assert result.provider == "openai"
        assert result.model == "gpt-5"

    def test_consistent_provider_no_warning(self, caplog: logging.Handler):
        with caplog.at_level(logging.WARNING, logger="src.llm_config.usage_tracker"):  # type: ignore[union-attr]
            result = _make_model_id("openai", "openai/gpt-5")
        assert result.provider == "openai"
        assert result.model == "gpt-5"
        assert len(caplog.records) == 0  # type: ignore[union-attr]

    def test_mismatched_provider_logs_warning(self, caplog: logging.Handler):
        with caplog.at_level(logging.WARNING, logger="src.llm_config.usage_tracker"):  # type: ignore[union-attr]
            result = _make_model_id("anthropic", "openai/gpt-5")
        assert result.provider == "openai"
        assert len(caplog.records) == 1  # type: ignore[union-attr]
        record = caplog.records[0]  # type: ignore[union-attr]
        assert record.levelno == logging.WARNING
        assert "disagrees" in record.message
        assert "anthropic" in record.message
        assert "openai" in record.message
