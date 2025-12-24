"""
Unit tests for LLMCostCalculator using litellm pricing.

Tests the cost calculation methods that use litellm's built-in
cost_per_token, completion_cost, and model_cost data.
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


class TestLLMCostCalculatorCalculateCost:
    """Tests for LLMCostCalculator.calculate_cost()."""

    def test_calculates_cost_for_known_model(self) -> None:
        """calculate_cost returns correct cost for a known model."""
        from src.llm_config.cost_calculator import LLMCostCalculator

        with patch("src.llm_config.cost_calculator.cost_per_token") as mock_cost:
            mock_cost.return_value = (0.00003, 0.00006)

            result = LLMCostCalculator.calculate_cost(
                model="gpt-4",
                input_tokens=1000,
                output_tokens=500,
            )

            mock_cost.assert_called_once_with(
                model="gpt-4",
                prompt_tokens=1000,
                completion_tokens=500,
            )
            expected = Decimal("0.00003") + Decimal("0.00006")
            assert result == expected.quantize(Decimal("0.000001"))

    def test_returns_decimal_with_precision(self) -> None:
        """calculate_cost returns Decimal with 6 decimal places."""
        from src.llm_config.cost_calculator import LLMCostCalculator

        with patch("src.llm_config.cost_calculator.cost_per_token") as mock_cost:
            mock_cost.return_value = (0.001, 0.002)

            result = LLMCostCalculator.calculate_cost(
                model="gpt-4",
                input_tokens=100,
                output_tokens=100,
            )

            assert isinstance(result, Decimal)
            assert result == Decimal("0.003000")

    def test_raises_value_error_for_unknown_model(self) -> None:
        """calculate_cost raises ValueError for unknown models."""
        from src.llm_config.cost_calculator import LLMCostCalculator

        with patch("src.llm_config.cost_calculator.cost_per_token") as mock_cost:
            mock_cost.side_effect = Exception("Model not found")

            with pytest.raises(ValueError, match="Unable to calculate cost"):
                LLMCostCalculator.calculate_cost(
                    model="unknown-model-xyz",
                    input_tokens=100,
                    output_tokens=100,
                )

    def test_handles_zero_tokens(self) -> None:
        """calculate_cost handles zero token counts correctly."""
        from src.llm_config.cost_calculator import LLMCostCalculator

        with patch("src.llm_config.cost_calculator.cost_per_token") as mock_cost:
            mock_cost.return_value = (0.0, 0.0)

            result = LLMCostCalculator.calculate_cost(
                model="gpt-4",
                input_tokens=0,
                output_tokens=0,
            )

            assert result == Decimal("0.000000")

    def test_handles_large_token_counts(self) -> None:
        """calculate_cost handles large token counts correctly."""
        from src.llm_config.cost_calculator import LLMCostCalculator

        with patch("src.llm_config.cost_calculator.cost_per_token") as mock_cost:
            mock_cost.return_value = (3.0, 6.0)

            result = LLMCostCalculator.calculate_cost(
                model="gpt-4",
                input_tokens=100000,
                output_tokens=100000,
            )

            assert result == Decimal("9.000000")


class TestLLMCostCalculatorCalculateCostFromResponse:
    """Tests for LLMCostCalculator.calculate_cost_from_response()."""

    def test_calculates_cost_from_response_object(self) -> None:
        """calculate_cost_from_response correctly processes response objects."""
        from src.llm_config.cost_calculator import LLMCostCalculator

        mock_response = MagicMock()
        mock_response.model = "gpt-4"
        mock_response.usage = MagicMock(prompt_tokens=100, completion_tokens=50)

        with patch("src.llm_config.cost_calculator.completion_cost") as mock_cost:
            mock_cost.return_value = 0.0045

            result = LLMCostCalculator.calculate_cost_from_response(response=mock_response)

            mock_cost.assert_called_once_with(
                completion_response=mock_response,
                model=None,
            )
            assert result == Decimal("0.004500")

    def test_uses_model_override_when_provided(self) -> None:
        """calculate_cost_from_response uses model override when specified."""
        from src.llm_config.cost_calculator import LLMCostCalculator

        mock_response = MagicMock()

        with patch("src.llm_config.cost_calculator.completion_cost") as mock_cost:
            mock_cost.return_value = 0.01

            LLMCostCalculator.calculate_cost_from_response(
                response=mock_response,
                model="anthropic/claude-3-opus",
            )

            mock_cost.assert_called_once_with(
                completion_response=mock_response,
                model="anthropic/claude-3-opus",
            )

    def test_returns_decimal_with_correct_precision(self) -> None:
        """calculate_cost_from_response returns Decimal with 6 decimal places."""
        from src.llm_config.cost_calculator import LLMCostCalculator

        mock_response = MagicMock()

        with patch("src.llm_config.cost_calculator.completion_cost") as mock_cost:
            mock_cost.return_value = 0.123456789

            result = LLMCostCalculator.calculate_cost_from_response(response=mock_response)

            assert isinstance(result, Decimal)
            assert result == Decimal("0.123457")


class TestLLMCostCalculatorGetModelPricing:
    """Tests for LLMCostCalculator.get_model_pricing()."""

    def test_returns_pricing_tuple_for_known_model(self) -> None:
        """get_model_pricing returns (input_cost, output_cost) tuple."""
        from src.llm_config.cost_calculator import LLMCostCalculator

        mock_model_cost = {
            "gpt-4": {
                "input_cost_per_token": 0.00003,
                "output_cost_per_token": 0.00006,
            },
        }

        with patch("src.llm_config.cost_calculator.model_cost", mock_model_cost):
            result = LLMCostCalculator.get_model_pricing(model="gpt-4")

            assert result == (Decimal("0.00003"), Decimal("0.00006"))

    def test_returns_decimal_values(self) -> None:
        """get_model_pricing returns Decimal instances."""
        from src.llm_config.cost_calculator import LLMCostCalculator

        mock_model_cost = {
            "gpt-4": {
                "input_cost_per_token": 0.00003,
                "output_cost_per_token": 0.00006,
            },
        }

        with patch("src.llm_config.cost_calculator.model_cost", mock_model_cost):
            input_price, output_price = LLMCostCalculator.get_model_pricing(model="gpt-4")

            assert isinstance(input_price, Decimal)
            assert isinstance(output_price, Decimal)

    def test_raises_value_error_for_unknown_model(self) -> None:
        """get_model_pricing raises ValueError for unknown model."""
        from src.llm_config.cost_calculator import LLMCostCalculator

        mock_model_cost = {"gpt-4": {}}

        with (
            patch("src.llm_config.cost_calculator.model_cost", mock_model_cost),
            pytest.raises(ValueError, match="Unknown model: nonexistent-model"),
        ):
            LLMCostCalculator.get_model_pricing(model="nonexistent-model")

    def test_suggests_similar_models_in_error(self) -> None:
        """get_model_pricing suggests similar models in error message."""
        from src.llm_config.cost_calculator import LLMCostCalculator

        mock_model_cost = {
            "gpt-4": {},
            "gpt-4-turbo": {},
            "gpt-4-vision": {},
        }

        with (
            patch("src.llm_config.cost_calculator.model_cost", mock_model_cost),
            pytest.raises(ValueError, match=r"Similar models:.*gpt-4"),
        ):
            LLMCostCalculator.get_model_pricing(model="gpt")

    def test_handles_missing_cost_fields(self) -> None:
        """get_model_pricing returns 0 for missing cost fields."""
        from src.llm_config.cost_calculator import LLMCostCalculator

        mock_model_cost = {
            "free-model": {},
        }

        with patch("src.llm_config.cost_calculator.model_cost", mock_model_cost):
            result = LLMCostCalculator.get_model_pricing(model="free-model")

            assert result == (Decimal("0"), Decimal("0"))


class TestLLMCostCalculatorListSupportedModels:
    """Tests for LLMCostCalculator.list_supported_models()."""

    def test_returns_list_of_model_names(self) -> None:
        """list_supported_models returns list of all model names."""
        from src.llm_config.cost_calculator import LLMCostCalculator

        mock_model_cost = {
            "gpt-4": {},
            "gpt-3.5-turbo": {},
            "anthropic/claude-3-opus": {},
        }

        with patch("src.llm_config.cost_calculator.model_cost", mock_model_cost):
            result = LLMCostCalculator.list_supported_models()

            assert isinstance(result, list)
            assert set(result) == {"gpt-4", "gpt-3.5-turbo", "anthropic/claude-3-opus"}

    def test_returns_empty_list_when_no_models(self) -> None:
        """list_supported_models returns empty list when no models available."""
        from src.llm_config.cost_calculator import LLMCostCalculator

        with patch("src.llm_config.cost_calculator.model_cost", {}):
            result = LLMCostCalculator.list_supported_models()

            assert result == []


class TestLLMCostCalculatorIsModelSupported:
    """Tests for LLMCostCalculator.is_model_supported()."""

    def test_returns_true_for_supported_model(self) -> None:
        """is_model_supported returns True for model in model_cost."""
        from src.llm_config.cost_calculator import LLMCostCalculator

        mock_model_cost = {"gpt-4": {}}

        with patch("src.llm_config.cost_calculator.model_cost", mock_model_cost):
            result = LLMCostCalculator.is_model_supported("gpt-4")

            assert result is True

    def test_returns_false_for_unsupported_model(self) -> None:
        """is_model_supported returns False for model not in model_cost."""
        from src.llm_config.cost_calculator import LLMCostCalculator

        mock_model_cost = {"gpt-4": {}}

        with patch("src.llm_config.cost_calculator.model_cost", mock_model_cost):
            result = LLMCostCalculator.is_model_supported("unknown-model")

            assert result is False


class TestLLMCostCalculatorGetSimilarModels:
    """Tests for LLMCostCalculator._get_similar_models()."""

    def test_finds_models_containing_search_term(self) -> None:
        """_get_similar_models returns models containing the search term."""
        from src.llm_config.cost_calculator import LLMCostCalculator

        mock_model_cost = {
            "gpt-4": {},
            "gpt-4-turbo": {},
            "gpt-4-vision": {},
            "gpt-3.5-turbo": {},
            "claude-3-opus": {},
        }

        with patch("src.llm_config.cost_calculator.model_cost", mock_model_cost):
            result = LLMCostCalculator._get_similar_models("gpt-4")

            assert "gpt-4" in result
            assert "gpt-4-turbo" in result
            assert "gpt-4-vision" in result
            assert "gpt-3.5-turbo" not in result
            assert "claude-3-opus" not in result

    def test_case_insensitive_search(self) -> None:
        """_get_similar_models is case insensitive."""
        from src.llm_config.cost_calculator import LLMCostCalculator

        mock_model_cost = {
            "GPT-4": {},
            "gpt-4-turbo": {},
        }

        with patch("src.llm_config.cost_calculator.model_cost", mock_model_cost):
            result = LLMCostCalculator._get_similar_models("gpt")

            assert "GPT-4" in result
            assert "gpt-4-turbo" in result

    def test_limits_results(self) -> None:
        """_get_similar_models respects the limit parameter."""
        from src.llm_config.cost_calculator import LLMCostCalculator

        mock_model_cost = {f"model-{i}": {} for i in range(10)}

        with patch("src.llm_config.cost_calculator.model_cost", mock_model_cost):
            result = LLMCostCalculator._get_similar_models("model", limit=3)

            assert len(result) == 3

    def test_returns_empty_list_when_no_matches(self) -> None:
        """_get_similar_models returns empty list when no matches found."""
        from src.llm_config.cost_calculator import LLMCostCalculator

        mock_model_cost = {"gpt-4": {}, "claude-3": {}}

        with patch("src.llm_config.cost_calculator.model_cost", mock_model_cost):
            result = LLMCostCalculator._get_similar_models("llama")

            assert result == []


class TestLLMCostCalculatorCalculateCostAsync:
    """Tests for LLMCostCalculator.calculate_cost_async()."""

    @pytest.mark.asyncio
    async def test_calculates_cost_with_provider_prefix(self) -> None:
        """calculate_cost_async adds provider prefix when model has no slash."""
        from src.llm_config.cost_calculator import LLMCostCalculator

        with patch("src.llm_config.cost_calculator.cost_per_token") as mock_cost:
            mock_cost.return_value = (0.00003, 0.00006)

            result = await LLMCostCalculator.calculate_cost_async(
                provider="openai",
                model="gpt-4",
                input_tokens=1000,
                output_tokens=500,
            )

            mock_cost.assert_called_once_with(
                model="openai/gpt-4",
                prompt_tokens=1000,
                completion_tokens=500,
            )
            assert result == Decimal("0.000090")

    @pytest.mark.asyncio
    async def test_does_not_add_prefix_when_model_has_slash(self) -> None:
        """calculate_cost_async preserves model when it already has a provider prefix."""
        from src.llm_config.cost_calculator import LLMCostCalculator

        with patch("src.llm_config.cost_calculator.cost_per_token") as mock_cost:
            mock_cost.return_value = (0.001, 0.002)

            result = await LLMCostCalculator.calculate_cost_async(
                provider="anthropic",
                model="anthropic/claude-3-opus",
                input_tokens=100,
                output_tokens=100,
            )

            mock_cost.assert_called_once_with(
                model="anthropic/claude-3-opus",
                prompt_tokens=100,
                completion_tokens=100,
            )
            assert result == Decimal("0.003000")

    @pytest.mark.asyncio
    async def test_falls_back_to_unprefixed_model(self) -> None:
        """calculate_cost_async falls back to model without prefix on ValueError."""
        from src.llm_config.cost_calculator import LLMCostCalculator

        with patch("src.llm_config.cost_calculator.cost_per_token") as mock_cost:
            mock_cost.side_effect = [
                Exception("Model not found"),
                (0.00001, 0.00002),
            ]

            result = await LLMCostCalculator.calculate_cost_async(
                provider="openai",
                model="gpt-4",
                input_tokens=100,
                output_tokens=100,
            )

            assert mock_cost.call_count == 2
            assert result == Decimal("0.000030")


class TestLLMCostCalculatorCalculateCostFromTotalTokensAsync:
    """Tests for LLMCostCalculator.calculate_cost_from_total_tokens_async()."""

    @pytest.mark.asyncio
    async def test_splits_tokens_evenly(self) -> None:
        """calculate_cost_from_total_tokens_async splits tokens 50/50."""
        from src.llm_config.cost_calculator import LLMCostCalculator

        with patch("src.llm_config.cost_calculator.cost_per_token") as mock_cost:
            mock_cost.return_value = (0.00001, 0.00002)

            result = await LLMCostCalculator.calculate_cost_from_total_tokens_async(
                provider="openai",
                model="gpt-4",
                total_tokens=100,
            )

            mock_cost.assert_called_once_with(
                model="openai/gpt-4",
                prompt_tokens=50,
                completion_tokens=50,
            )
            assert result == Decimal("0.000030")

    @pytest.mark.asyncio
    async def test_handles_odd_total_tokens(self) -> None:
        """calculate_cost_from_total_tokens_async handles odd token counts."""
        from src.llm_config.cost_calculator import LLMCostCalculator

        with patch("src.llm_config.cost_calculator.cost_per_token") as mock_cost:
            mock_cost.return_value = (0.00001, 0.00002)

            result = await LLMCostCalculator.calculate_cost_from_total_tokens_async(
                provider="openai",
                model="gpt-4",
                total_tokens=101,
            )

            mock_cost.assert_called_once_with(
                model="openai/gpt-4",
                prompt_tokens=50,
                completion_tokens=51,
            )
            assert isinstance(result, Decimal)


class TestLLMCostCalculatorIntegration:
    """Integration tests that use real litellm.model_cost data."""

    def test_model_cost_contains_expected_models(self) -> None:
        """litellm.model_cost contains well-known models."""
        from litellm import model_cost

        assert len(model_cost) > 0

    def test_calculate_cost_works_with_real_model(self) -> None:
        """calculate_cost works with an actual model from litellm."""
        from src.llm_config.cost_calculator import LLMCostCalculator

        result = LLMCostCalculator.calculate_cost(
            model="gpt-4",
            input_tokens=1000,
            output_tokens=500,
        )

        assert isinstance(result, Decimal)
        assert result > Decimal("0")

    def test_is_model_supported_with_real_models(self) -> None:
        """is_model_supported correctly identifies real models."""
        from src.llm_config.cost_calculator import LLMCostCalculator

        assert LLMCostCalculator.is_model_supported("gpt-4") is True
        assert LLMCostCalculator.is_model_supported("this-model-does-not-exist-xyz") is False

    def test_get_model_pricing_with_real_model(self) -> None:
        """get_model_pricing returns valid pricing for real model."""
        from src.llm_config.cost_calculator import LLMCostCalculator

        input_price, output_price = LLMCostCalculator.get_model_pricing("gpt-4")

        assert isinstance(input_price, Decimal)
        assert isinstance(output_price, Decimal)
        assert input_price >= Decimal("0")
        assert output_price >= Decimal("0")
