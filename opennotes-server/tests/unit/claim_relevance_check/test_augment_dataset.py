"""Tests for augment_dataset module migration from litellm to pydantic-ai."""

from unittest.mock import MagicMock, patch

from src.claim_relevance_check.prompt_optimization.augment_dataset import (
    generate_example_with_llm,
)


class TestGenerateExampleWithLLM:
    """Tests that generate_example_with_llm uses pydantic-ai model_request_sync."""

    @patch("src.claim_relevance_check.prompt_optimization.augment_dataset.model_request_sync")
    def test_calls_model_request_sync(self, mock_request_sync) -> None:
        mock_response = MagicMock()
        mock_response.text = '{"example_id": "fp-001", "message": "test", "fact_check_title": "title", "fact_check_content": "content", "is_relevant": false, "reasoning": "not relevant"}'
        mock_request_sync.return_value = mock_response

        result = generate_example_with_llm(
            example_type="false_positive",
            example_id="fp-001",
        )

        mock_request_sync.assert_called_once()
        assert result is not None
        assert result["example_id"] == "fp-001"

    @patch("src.claim_relevance_check.prompt_optimization.augment_dataset.model_request_sync")
    def test_uses_pydantic_ai_model_format(self, mock_request_sync) -> None:
        mock_response = MagicMock()
        mock_response.text = '{"example_id": "tp-001", "message": "test", "fact_check_title": "title", "fact_check_content": "content", "is_relevant": true, "reasoning": "relevant"}'
        mock_request_sync.return_value = mock_response

        generate_example_with_llm(
            example_type="true_positive",
            example_id="tp-001",
            model="openai:gpt-5-mini",
        )

        call_args = mock_request_sync.call_args
        model_arg = call_args.args[0] if call_args.args else call_args.kwargs.get("model", "")
        assert model_arg == "openai:gpt-5-mini"

    @patch("src.claim_relevance_check.prompt_optimization.augment_dataset.model_request_sync")
    def test_returns_none_on_json_error(self, mock_request_sync) -> None:
        mock_response = MagicMock()
        mock_response.text = "not valid json"
        mock_request_sync.return_value = mock_response

        result = generate_example_with_llm(
            example_type="false_positive",
            example_id="fp-001",
        )

        assert result is None

    @patch("src.claim_relevance_check.prompt_optimization.augment_dataset.model_request_sync")
    def test_returns_none_on_api_error(self, mock_request_sync) -> None:
        mock_request_sync.side_effect = Exception("API error")

        result = generate_example_with_llm(
            example_type="false_positive",
            example_id="fp-001",
        )

        assert result is None

    def test_no_litellm_imports(self) -> None:
        import importlib
        from pathlib import Path

        import src.claim_relevance_check.prompt_optimization.augment_dataset as mod

        importlib.reload(mod)
        source = Path(mod.__file__).read_text()
        assert "import litellm" not in source
        assert "from litellm" not in source
