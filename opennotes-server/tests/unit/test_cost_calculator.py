"""
Unit tests for cost calculator pricing types and models.dev fetcher.

Tests the ModelPricing TypedDict, related type aliases, and
fetch_models_dev_pricing async function.
"""

from decimal import Decimal
from typing import get_type_hints
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import httpx
import pytest


class TestModelPricingTypeDefinition:
    """Test that ModelPricing TypedDict has correct structure."""

    def test_model_pricing_has_input_price_field(self) -> None:
        """ModelPricing should have an input_price field."""
        from src.llm_config.cost_calculator import ModelPricing

        hints = get_type_hints(ModelPricing)
        assert "input_price" in hints

    def test_model_pricing_input_price_is_decimal(self) -> None:
        """ModelPricing.input_price should be typed as Decimal."""
        from src.llm_config.cost_calculator import ModelPricing

        hints = get_type_hints(ModelPricing)
        assert hints["input_price"] is Decimal

    def test_model_pricing_has_output_price_field(self) -> None:
        """ModelPricing should have an output_price field."""
        from src.llm_config.cost_calculator import ModelPricing

        hints = get_type_hints(ModelPricing)
        assert "output_price" in hints

    def test_model_pricing_output_price_is_decimal(self) -> None:
        """ModelPricing.output_price should be typed as Decimal."""
        from src.llm_config.cost_calculator import ModelPricing

        hints = get_type_hints(ModelPricing)
        assert hints["output_price"] is Decimal

    def test_model_pricing_can_be_instantiated(self) -> None:
        """ModelPricing should be instantiable with valid values."""
        from src.llm_config.cost_calculator import ModelPricing

        pricing: ModelPricing = {
            "input_price": Decimal("0.01"),
            "output_price": Decimal("0.03"),
        }
        assert pricing["input_price"] == Decimal("0.01")
        assert pricing["output_price"] == Decimal("0.03")


class TestProviderPricingTypeAlias:
    """Test that ProviderPricing type alias is correctly defined."""

    def test_provider_pricing_is_dict_of_model_pricing(self) -> None:
        """ProviderPricing should be a dict mapping model_id to ModelPricing."""
        from src.llm_config.cost_calculator import ProviderPricing

        pricing: ProviderPricing = {
            "gpt-4": {
                "input_price": Decimal("0.03"),
                "output_price": Decimal("0.06"),
            },
            "gpt-3.5-turbo": {
                "input_price": Decimal("0.0005"),
                "output_price": Decimal("0.0015"),
            },
        }
        assert "gpt-4" in pricing
        assert pricing["gpt-4"]["input_price"] == Decimal("0.03")

    def test_provider_pricing_values_are_model_pricing(self) -> None:
        """Each value in ProviderPricing should be a valid ModelPricing."""
        from src.llm_config.cost_calculator import ModelPricing, ProviderPricing

        model_pricing: ModelPricing = {
            "input_price": Decimal("0.01"),
            "output_price": Decimal("0.02"),
        }
        provider_pricing: ProviderPricing = {"test-model": model_pricing}

        assert provider_pricing["test-model"] == model_pricing


class TestAllPricingTypeAlias:
    """Test that AllPricing type alias is correctly defined."""

    def test_all_pricing_is_dict_of_provider_pricing(self) -> None:
        """AllPricing should be a dict mapping provider_id to ProviderPricing."""
        from src.llm_config.cost_calculator import AllPricing

        pricing: AllPricing = {
            "openai": {
                "gpt-4": {
                    "input_price": Decimal("0.03"),
                    "output_price": Decimal("0.06"),
                },
            },
            "anthropic": {
                "claude-3-opus": {
                    "input_price": Decimal("0.015"),
                    "output_price": Decimal("0.075"),
                },
            },
        }
        assert "openai" in pricing
        assert "anthropic" in pricing
        assert pricing["openai"]["gpt-4"]["input_price"] == Decimal("0.03")

    def test_all_pricing_nested_structure(self) -> None:
        """AllPricing should support provider -> model -> pricing hierarchy."""
        from src.llm_config.cost_calculator import AllPricing, ModelPricing, ProviderPricing

        model: ModelPricing = {
            "input_price": Decimal("0.001"),
            "output_price": Decimal("0.002"),
        }
        provider: ProviderPricing = {"test-model": model}
        all_pricing: AllPricing = {"test-provider": provider}

        assert all_pricing["test-provider"]["test-model"]["input_price"] == Decimal("0.001")
        assert all_pricing["test-provider"]["test-model"]["output_price"] == Decimal("0.002")


pytestmark = pytest.mark.unit


class TestFetchModelsDevPricing:
    """Tests for fetch_models_dev_pricing async function."""

    @pytest.mark.asyncio
    async def test_returns_all_pricing_on_success(self) -> None:
        """fetch_models_dev_pricing returns AllPricing dict on successful API response."""
        from src.llm_config.cost_calculator import fetch_models_dev_pricing

        api_response = {
            "openai": {
                "id": "openai",
                "models": {
                    "gpt-4": {
                        "id": "gpt-4",
                        "cost": {
                            "input": 30,
                            "output": 60,
                        },
                    },
                },
            },
        }

        mock_response = MagicMock()
        mock_response.json.return_value = api_response
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await fetch_models_dev_pricing()

        assert result is not None
        assert "openai" in result
        assert "gpt-4" in result["openai"]

    @pytest.mark.asyncio
    async def test_correctly_maps_api_format_to_per_1k_tokens(self) -> None:
        """API prices per 1M tokens are converted to per 1K tokens (divide by 1000)."""
        from src.llm_config.cost_calculator import fetch_models_dev_pricing

        api_response = {
            "openai": {
                "id": "openai",
                "models": {
                    "gpt-4": {
                        "id": "gpt-4",
                        "cost": {
                            "input": 30,
                            "output": 60,
                        },
                    },
                },
            },
        }

        mock_response = MagicMock()
        mock_response.json.return_value = api_response
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await fetch_models_dev_pricing()

        assert result is not None
        assert result["openai"]["gpt-4"]["input_price"] == Decimal("0.03")
        assert result["openai"]["gpt-4"]["output_price"] == Decimal("0.06")

    @pytest.mark.asyncio
    async def test_returns_none_on_http_error(self) -> None:
        """fetch_models_dev_pricing returns None when HTTP error occurs."""
        from src.llm_config.cost_calculator import fetch_models_dev_pricing

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(
                side_effect=httpx.HTTPStatusError(
                    "Server Error",
                    request=MagicMock(),
                    response=MagicMock(status_code=500),
                )
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await fetch_models_dev_pricing()

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_timeout(self) -> None:
        """fetch_models_dev_pricing returns None when timeout occurs."""
        from src.llm_config.cost_calculator import fetch_models_dev_pricing

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("Request timed out"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await fetch_models_dev_pricing()

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_invalid_json(self) -> None:
        """fetch_models_dev_pricing returns None when response is invalid JSON."""
        import json

        from src.llm_config.cost_calculator import fetch_models_dev_pricing

        mock_response = MagicMock()
        mock_response.json.side_effect = json.JSONDecodeError("Invalid JSON", "", 0)
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await fetch_models_dev_pricing()

        assert result is None

    @pytest.mark.asyncio
    async def test_handles_multiple_providers_and_models(self) -> None:
        """fetch_models_dev_pricing handles multiple providers with multiple models."""
        from src.llm_config.cost_calculator import fetch_models_dev_pricing

        api_response = {
            "openai": {
                "id": "openai",
                "models": {
                    "gpt-4": {"cost": {"input": 30, "output": 60}},
                    "gpt-3.5-turbo": {"cost": {"input": 0.5, "output": 1.5}},
                },
            },
            "anthropic": {
                "id": "anthropic",
                "models": {
                    "claude-3-opus": {"cost": {"input": 15, "output": 75}},
                },
            },
        }

        mock_response = MagicMock()
        mock_response.json.return_value = api_response
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await fetch_models_dev_pricing()

        assert result is not None
        assert len(result) == 2
        assert "openai" in result
        assert "anthropic" in result
        assert len(result["openai"]) == 2
        assert result["openai"]["gpt-3.5-turbo"]["input_price"] == Decimal("0.0005")
        assert result["anthropic"]["claude-3-opus"]["output_price"] == Decimal("0.075")


class TestMapModelsDevResponse:
    """Tests for _map_models_dev_response helper function."""

    def test_skips_provider_without_models_key(self) -> None:
        """Providers without 'models' key are skipped."""
        from src.llm_config.cost_calculator import _map_models_dev_response

        data = {
            "invalid_provider": {"id": "invalid"},
            "valid_provider": {
                "models": {
                    "model-1": {"cost": {"input": 10, "output": 20}},
                },
            },
        }

        result = _map_models_dev_response(data)

        assert "invalid_provider" not in result
        assert "valid_provider" in result

    def test_skips_model_without_cost_key(self) -> None:
        """Models without 'cost' key are skipped."""
        from src.llm_config.cost_calculator import _map_models_dev_response

        data = {
            "provider": {
                "models": {
                    "no-cost-model": {"id": "no-cost"},
                    "valid-model": {"cost": {"input": 5, "output": 10}},
                },
            },
        }

        result = _map_models_dev_response(data)

        assert "no-cost-model" not in result["provider"]
        assert "valid-model" in result["provider"]

    def test_skips_model_with_missing_input_price(self) -> None:
        """Models missing input price are skipped."""
        from src.llm_config.cost_calculator import _map_models_dev_response

        data = {
            "provider": {
                "models": {
                    "missing-input": {"cost": {"output": 10}},
                    "valid": {"cost": {"input": 5, "output": 10}},
                },
            },
        }

        result = _map_models_dev_response(data)

        assert "missing-input" not in result["provider"]
        assert "valid" in result["provider"]

    def test_skips_model_with_missing_output_price(self) -> None:
        """Models missing output price are skipped."""
        from src.llm_config.cost_calculator import _map_models_dev_response

        data = {
            "provider": {
                "models": {
                    "missing-output": {"cost": {"input": 5}},
                    "valid": {"cost": {"input": 5, "output": 10}},
                },
            },
        }

        result = _map_models_dev_response(data)

        assert "missing-output" not in result["provider"]
        assert "valid" in result["provider"]

    def test_returns_empty_dict_for_no_valid_data(self) -> None:
        """Returns empty dict when no valid pricing data is found."""
        from src.llm_config.cost_calculator import _map_models_dev_response

        data = {
            "provider": {
                "models": {
                    "invalid": {"no_cost": True},
                },
            },
        }

        result = _map_models_dev_response(data)

        assert result == {}

    def test_skips_provider_with_empty_valid_models(self) -> None:
        """Providers with no valid models after filtering are not included."""
        from src.llm_config.cost_calculator import _map_models_dev_response

        data = {
            "empty_provider": {
                "models": {
                    "invalid": {"no_cost": True},
                },
            },
            "valid_provider": {
                "models": {
                    "valid": {"cost": {"input": 1, "output": 2}},
                },
            },
        }

        result = _map_models_dev_response(data)

        assert "empty_provider" not in result
        assert "valid_provider" in result

    def test_handles_non_dict_models_value(self) -> None:
        """Handles case where 'models' is not a dict."""
        from src.llm_config.cost_calculator import _map_models_dev_response

        data = {
            "provider": {
                "models": "not a dict",
            },
        }

        result = _map_models_dev_response(data)

        assert result == {}

    def test_handles_non_dict_cost_value(self) -> None:
        """Handles case where 'cost' is not a dict."""
        from src.llm_config.cost_calculator import _map_models_dev_response

        data = {
            "provider": {
                "models": {
                    "model": {"cost": "not a dict"},
                },
            },
        }

        result = _map_models_dev_response(data)

        assert result == {}

    def test_handles_non_dict_provider_data(self) -> None:
        """Handles case where provider data is not a dict."""
        from src.llm_config.cost_calculator import _map_models_dev_response

        data = {
            "provider": "not a dict",
        }

        result = _map_models_dev_response(data)

        assert result == {}

    def test_handles_non_dict_model_data(self) -> None:
        """Handles case where model data is not a dict."""
        from src.llm_config.cost_calculator import _map_models_dev_response

        data = {
            "provider": {
                "models": {
                    "model": "not a dict",
                },
            },
        }

        result = _map_models_dev_response(data)

        assert result == {}

    def test_handles_zero_prices(self) -> None:
        """Zero prices are valid and included."""
        from src.llm_config.cost_calculator import _map_models_dev_response

        data = {
            "provider": {
                "models": {
                    "free-model": {"cost": {"input": 0, "output": 0}},
                },
            },
        }

        result = _map_models_dev_response(data)

        assert "free-model" in result["provider"]
        assert result["provider"]["free-model"]["input_price"] == Decimal("0")
        assert result["provider"]["free-model"]["output_price"] == Decimal("0")


class TestSerializePricing:
    """Tests for _serialize_pricing helper function."""

    def test_converts_decimal_to_string(self) -> None:
        """_serialize_pricing converts Decimal values to strings for JSON storage."""
        from src.llm_config.cost_calculator import AllPricing, ModelPricing, _serialize_pricing

        pricing: AllPricing = {
            "openai": {
                "gpt-4": ModelPricing(
                    input_price=Decimal("0.03"),
                    output_price=Decimal("0.06"),
                ),
            },
        }

        result = _serialize_pricing(pricing)

        assert result["openai"]["gpt-4"]["input_price"] == "0.03"
        assert result["openai"]["gpt-4"]["output_price"] == "0.06"
        assert isinstance(result["openai"]["gpt-4"]["input_price"], str)
        assert isinstance(result["openai"]["gpt-4"]["output_price"], str)

    def test_preserves_structure(self) -> None:
        """_serialize_pricing maintains the provider -> model -> pricing hierarchy."""
        from src.llm_config.cost_calculator import AllPricing, ModelPricing, _serialize_pricing

        pricing: AllPricing = {
            "openai": {
                "gpt-4": ModelPricing(input_price=Decimal("0.03"), output_price=Decimal("0.06")),
                "gpt-3.5-turbo": ModelPricing(
                    input_price=Decimal("0.0005"), output_price=Decimal("0.0015")
                ),
            },
            "anthropic": {
                "claude-3-opus": ModelPricing(
                    input_price=Decimal("0.015"), output_price=Decimal("0.075")
                ),
            },
        }

        result = _serialize_pricing(pricing)

        assert len(result) == 2
        assert len(result["openai"]) == 2
        assert len(result["anthropic"]) == 1


class TestDeserializePricing:
    """Tests for _deserialize_pricing helper function."""

    def test_converts_string_to_decimal(self) -> None:
        """_deserialize_pricing converts string values back to Decimal."""
        from src.llm_config.cost_calculator import _deserialize_pricing

        data = {
            "openai": {
                "gpt-4": {
                    "input_price": "0.03",
                    "output_price": "0.06",
                },
            },
        }

        result = _deserialize_pricing(data)

        assert result["openai"]["gpt-4"]["input_price"] == Decimal("0.03")
        assert result["openai"]["gpt-4"]["output_price"] == Decimal("0.06")
        assert isinstance(result["openai"]["gpt-4"]["input_price"], Decimal)
        assert isinstance(result["openai"]["gpt-4"]["output_price"], Decimal)

    def test_preserves_structure(self) -> None:
        """_deserialize_pricing maintains the provider -> model -> pricing hierarchy."""
        from src.llm_config.cost_calculator import _deserialize_pricing

        data = {
            "openai": {
                "gpt-4": {"input_price": "0.03", "output_price": "0.06"},
                "gpt-3.5-turbo": {"input_price": "0.0005", "output_price": "0.0015"},
            },
            "anthropic": {
                "claude-3-opus": {"input_price": "0.015", "output_price": "0.075"},
            },
        }

        result = _deserialize_pricing(data)

        assert len(result) == 2
        assert len(result["openai"]) == 2
        assert len(result["anthropic"]) == 1


class TestGetLlmPricing:
    """Tests for get_llm_pricing async function with caching."""

    @pytest.fixture(autouse=True)
    def clear_cache(self) -> None:
        """Clear in-memory pricing cache before each test."""
        from src.llm_config.cost_calculator import clear_pricing_cache

        clear_pricing_cache()

    @pytest.mark.asyncio
    async def test_returns_cached_data_on_cache_hit(self) -> None:
        """get_llm_pricing returns cached data without calling fetch on cache hit."""
        from src.llm_config.cost_calculator import get_llm_pricing

        cached_data = {
            "openai": {
                "gpt-4": {
                    "input_price": "0.03",
                    "output_price": "0.06",
                },
            },
        }

        with (
            patch(
                "src.llm_config.cost_calculator.cache_manager.get", new_callable=AsyncMock
            ) as mock_get,
            patch(
                "src.llm_config.cost_calculator.fetch_models_dev_pricing", new_callable=AsyncMock
            ) as mock_fetch,
        ):
            mock_get.return_value = cached_data

            result = await get_llm_pricing()

            mock_get.assert_called_once_with("llm_pricing:all")
            mock_fetch.assert_not_called()
            assert result["openai"]["gpt-4"]["input_price"] == Decimal("0.03")

    @pytest.mark.asyncio
    async def test_fetches_from_api_on_cache_miss(self) -> None:
        """get_llm_pricing fetches from API when cache is empty."""
        from src.llm_config.cost_calculator import ModelPricing, get_llm_pricing

        api_pricing = {
            "openai": {
                "gpt-4": ModelPricing(
                    input_price=Decimal("0.03"),
                    output_price=Decimal("0.06"),
                ),
            },
        }

        with (
            patch(
                "src.llm_config.cost_calculator.cache_manager.get", new_callable=AsyncMock
            ) as mock_get,
            patch("src.llm_config.cost_calculator.cache_manager.set", new_callable=AsyncMock),
            patch(
                "src.llm_config.cost_calculator.fetch_models_dev_pricing", new_callable=AsyncMock
            ) as mock_fetch,
        ):
            mock_get.return_value = None
            mock_fetch.return_value = api_pricing

            result = await get_llm_pricing()

            mock_get.assert_called_once()
            mock_fetch.assert_called_once()
            assert result["openai"]["gpt-4"]["input_price"] == Decimal("0.03")

    @pytest.mark.asyncio
    async def test_raises_error_on_api_failure(self) -> None:
        """get_llm_pricing raises PricingUnavailableError when API fails."""
        from src.llm_config.cost_calculator import PricingUnavailableError, get_llm_pricing

        with (
            patch(
                "src.llm_config.cost_calculator.cache_manager.get", new_callable=AsyncMock
            ) as mock_get,
            patch(
                "src.llm_config.cost_calculator.fetch_models_dev_pricing", new_callable=AsyncMock
            ) as mock_fetch,
        ):
            mock_get.return_value = None
            mock_fetch.return_value = None

            with pytest.raises(PricingUnavailableError):
                await get_llm_pricing()

            mock_fetch.assert_called_once()

    @pytest.mark.asyncio
    async def test_caches_result_after_successful_fetch(self) -> None:
        """get_llm_pricing caches the result with correct TTL after successful API fetch."""
        from src.llm_config.cost_calculator import (
            LLM_PRICING_CACHE_KEY,
            ModelPricing,
            get_llm_pricing,
        )

        api_pricing = {
            "openai": {
                "gpt-4": ModelPricing(
                    input_price=Decimal("0.03"),
                    output_price=Decimal("0.06"),
                ),
            },
        }

        with (
            patch(
                "src.llm_config.cost_calculator.cache_manager.get", new_callable=AsyncMock
            ) as mock_get,
            patch(
                "src.llm_config.cost_calculator.cache_manager.set", new_callable=AsyncMock
            ) as mock_set,
            patch(
                "src.llm_config.cost_calculator.fetch_models_dev_pricing", new_callable=AsyncMock
            ) as mock_fetch,
            patch("src.llm_config.cost_calculator.settings") as mock_settings,
        ):
            mock_get.return_value = None
            mock_fetch.return_value = api_pricing
            mock_settings.CACHE_LLM_PRICING_TTL = 86400

            await get_llm_pricing()

            mock_set.assert_called_once()
            call_args = mock_set.call_args
            assert call_args[0][0] == LLM_PRICING_CACHE_KEY
            assert call_args[1]["ttl"] == 86400
            serialized = call_args[0][1]
            assert serialized["openai"]["gpt-4"]["input_price"] == "0.03"

    @pytest.mark.asyncio
    async def test_does_not_cache_on_api_failure(self) -> None:
        """get_llm_pricing does not cache when API fails."""
        from src.llm_config.cost_calculator import PricingUnavailableError, get_llm_pricing

        with (
            patch(
                "src.llm_config.cost_calculator.cache_manager.get", new_callable=AsyncMock
            ) as mock_get,
            patch(
                "src.llm_config.cost_calculator.cache_manager.set", new_callable=AsyncMock
            ) as mock_set,
            patch(
                "src.llm_config.cost_calculator.fetch_models_dev_pricing", new_callable=AsyncMock
            ) as mock_fetch,
        ):
            mock_get.return_value = None
            mock_fetch.return_value = None

            with pytest.raises(PricingUnavailableError):
                await get_llm_pricing()

            mock_set.assert_not_called()


class TestLLMCostCalculatorAsyncMethods:
    """Tests for async versions of LLMCostCalculator methods using dynamic pricing."""

    @pytest.fixture(autouse=True)
    def clear_cache(self) -> None:
        """Clear in-memory pricing cache before each test."""
        from src.llm_config.cost_calculator import clear_pricing_cache

        clear_pricing_cache()

    @pytest.fixture
    def mock_pricing_data(self) -> dict:
        """Provides mock pricing data for tests."""
        from src.llm_config.cost_calculator import ModelPricing

        return {
            "openai": {
                "gpt-4": ModelPricing(
                    input_price=Decimal("0.03"),
                    output_price=Decimal("0.06"),
                ),
                "gpt-4o": ModelPricing(
                    input_price=Decimal("0.005"),
                    output_price=Decimal("0.015"),
                ),
            },
            "anthropic": {
                "claude-3-opus": ModelPricing(
                    input_price=Decimal("0.015"),
                    output_price=Decimal("0.075"),
                ),
            },
        }

    @pytest.mark.asyncio
    async def test_calculate_cost_async_uses_dynamic_pricing(self, mock_pricing_data: dict) -> None:
        """calculate_cost_async should use pricing from get_llm_pricing."""
        from src.llm_config.cost_calculator import LLMCostCalculator

        with patch(
            "src.llm_config.cost_calculator.get_llm_pricing", new_callable=AsyncMock
        ) as mock_get_pricing:
            mock_get_pricing.return_value = mock_pricing_data

            result = await LLMCostCalculator.calculate_cost_async(
                provider="openai",
                model="gpt-4",
                input_tokens=1000,
                output_tokens=500,
            )

            mock_get_pricing.assert_called_once()
            expected = (Decimal("1000") / Decimal("1000") * Decimal("0.03")) + (
                Decimal("500") / Decimal("1000") * Decimal("0.06")
            )
            assert result == expected.quantize(Decimal("0.000001"))

    @pytest.mark.asyncio
    async def test_calculate_cost_async_handles_case_insensitive_provider(
        self, mock_pricing_data: dict
    ) -> None:
        """calculate_cost_async should handle uppercase provider names."""
        from src.llm_config.cost_calculator import LLMCostCalculator

        with patch(
            "src.llm_config.cost_calculator.get_llm_pricing", new_callable=AsyncMock
        ) as mock_get_pricing:
            mock_get_pricing.return_value = mock_pricing_data

            result = await LLMCostCalculator.calculate_cost_async(
                provider="OpenAI",
                model="gpt-4",
                input_tokens=1000,
                output_tokens=1000,
            )

            assert result == Decimal("0.090000")

    @pytest.mark.asyncio
    async def test_calculate_cost_async_raises_for_unknown_provider(
        self, mock_pricing_data: dict
    ) -> None:
        """calculate_cost_async should raise ValueError for unknown provider."""
        from src.llm_config.cost_calculator import LLMCostCalculator

        with patch(
            "src.llm_config.cost_calculator.get_llm_pricing", new_callable=AsyncMock
        ) as mock_get_pricing:
            mock_get_pricing.return_value = mock_pricing_data

            with pytest.raises(ValueError, match="Unknown provider: unknown"):
                await LLMCostCalculator.calculate_cost_async(
                    provider="unknown",
                    model="model",
                    input_tokens=100,
                    output_tokens=100,
                )

    @pytest.mark.asyncio
    async def test_calculate_cost_async_raises_for_unknown_model(
        self, mock_pricing_data: dict
    ) -> None:
        """calculate_cost_async should raise ValueError for unknown model."""
        from src.llm_config.cost_calculator import LLMCostCalculator

        with patch(
            "src.llm_config.cost_calculator.get_llm_pricing", new_callable=AsyncMock
        ) as mock_get_pricing:
            mock_get_pricing.return_value = mock_pricing_data

            with pytest.raises(ValueError, match="Unknown model 'unknown-model'"):
                await LLMCostCalculator.calculate_cost_async(
                    provider="openai",
                    model="unknown-model",
                    input_tokens=100,
                    output_tokens=100,
                )

    @pytest.mark.asyncio
    async def test_calculate_cost_async_error_lists_available_models(
        self, mock_pricing_data: dict
    ) -> None:
        """Error message for unknown model should list available models."""
        from src.llm_config.cost_calculator import LLMCostCalculator

        with patch(
            "src.llm_config.cost_calculator.get_llm_pricing", new_callable=AsyncMock
        ) as mock_get_pricing:
            mock_get_pricing.return_value = mock_pricing_data

            with pytest.raises(ValueError, match="gpt-4"):
                await LLMCostCalculator.calculate_cost_async(
                    provider="openai",
                    model="unknown",
                    input_tokens=100,
                    output_tokens=100,
                )

    @pytest.mark.asyncio
    async def test_get_model_pricing_async_returns_pricing_tuple(
        self, mock_pricing_data: dict
    ) -> None:
        """get_model_pricing_async should return (input_price, output_price) tuple."""
        from src.llm_config.cost_calculator import LLMCostCalculator

        with patch(
            "src.llm_config.cost_calculator.get_llm_pricing", new_callable=AsyncMock
        ) as mock_get_pricing:
            mock_get_pricing.return_value = mock_pricing_data

            result = await LLMCostCalculator.get_model_pricing_async(
                provider="openai",
                model="gpt-4",
            )

            assert result == (Decimal("0.03"), Decimal("0.06"))

    @pytest.mark.asyncio
    async def test_get_model_pricing_async_case_insensitive(self, mock_pricing_data: dict) -> None:
        """get_model_pricing_async should handle uppercase provider names."""
        from src.llm_config.cost_calculator import LLMCostCalculator

        with patch(
            "src.llm_config.cost_calculator.get_llm_pricing", new_callable=AsyncMock
        ) as mock_get_pricing:
            mock_get_pricing.return_value = mock_pricing_data

            result = await LLMCostCalculator.get_model_pricing_async(
                provider="ANTHROPIC",
                model="claude-3-opus",
            )

            assert result == (Decimal("0.015"), Decimal("0.075"))

    @pytest.mark.asyncio
    async def test_get_model_pricing_async_raises_for_unknown_provider(
        self, mock_pricing_data: dict
    ) -> None:
        """get_model_pricing_async should raise ValueError for unknown provider."""
        from src.llm_config.cost_calculator import LLMCostCalculator

        with patch(
            "src.llm_config.cost_calculator.get_llm_pricing", new_callable=AsyncMock
        ) as mock_get_pricing:
            mock_get_pricing.return_value = mock_pricing_data

            with pytest.raises(ValueError, match="Unknown provider: unknown"):
                await LLMCostCalculator.get_model_pricing_async(
                    provider="unknown",
                    model="model",
                )

    @pytest.mark.asyncio
    async def test_get_model_pricing_async_raises_for_unknown_model(
        self, mock_pricing_data: dict
    ) -> None:
        """get_model_pricing_async should raise ValueError for unknown model."""
        from src.llm_config.cost_calculator import LLMCostCalculator

        with patch(
            "src.llm_config.cost_calculator.get_llm_pricing", new_callable=AsyncMock
        ) as mock_get_pricing:
            mock_get_pricing.return_value = mock_pricing_data

            with pytest.raises(ValueError, match="Unknown model 'nonexistent'"):
                await LLMCostCalculator.get_model_pricing_async(
                    provider="openai",
                    model="nonexistent",
                )

    @pytest.mark.asyncio
    async def test_list_supported_providers_async_returns_providers(
        self, mock_pricing_data: dict
    ) -> None:
        """list_supported_providers_async should return list of providers from dynamic pricing."""
        from src.llm_config.cost_calculator import LLMCostCalculator

        with patch(
            "src.llm_config.cost_calculator.get_llm_pricing", new_callable=AsyncMock
        ) as mock_get_pricing:
            mock_get_pricing.return_value = mock_pricing_data

            result = await LLMCostCalculator.list_supported_providers_async()

            assert set(result) == {"openai", "anthropic"}

    @pytest.mark.asyncio
    async def test_list_provider_models_async_returns_models(self, mock_pricing_data: dict) -> None:
        """list_provider_models_async should return list of models for provider."""
        from src.llm_config.cost_calculator import LLMCostCalculator

        with patch(
            "src.llm_config.cost_calculator.get_llm_pricing", new_callable=AsyncMock
        ) as mock_get_pricing:
            mock_get_pricing.return_value = mock_pricing_data

            result = await LLMCostCalculator.list_provider_models_async(provider="openai")

            assert set(result) == {"gpt-4", "gpt-4o"}

    @pytest.mark.asyncio
    async def test_list_provider_models_async_case_insensitive(
        self, mock_pricing_data: dict
    ) -> None:
        """list_provider_models_async should handle uppercase provider names."""
        from src.llm_config.cost_calculator import LLMCostCalculator

        with patch(
            "src.llm_config.cost_calculator.get_llm_pricing", new_callable=AsyncMock
        ) as mock_get_pricing:
            mock_get_pricing.return_value = mock_pricing_data

            result = await LLMCostCalculator.list_provider_models_async(provider="OPENAI")

            assert set(result) == {"gpt-4", "gpt-4o"}

    @pytest.mark.asyncio
    async def test_list_provider_models_async_raises_for_unknown_provider(
        self, mock_pricing_data: dict
    ) -> None:
        """list_provider_models_async should raise ValueError for unknown provider."""
        from src.llm_config.cost_calculator import LLMCostCalculator

        with patch(
            "src.llm_config.cost_calculator.get_llm_pricing", new_callable=AsyncMock
        ) as mock_get_pricing:
            mock_get_pricing.return_value = mock_pricing_data

            with pytest.raises(ValueError, match="Unknown provider: unknown"):
                await LLMCostCalculator.list_provider_models_async(provider="unknown")

    @pytest.mark.asyncio
    async def test_calculate_cost_from_total_tokens_async_uses_dynamic_pricing(
        self, mock_pricing_data: dict
    ) -> None:
        """calculate_cost_from_total_tokens_async should use dynamic pricing."""
        from src.llm_config.cost_calculator import LLMCostCalculator

        with patch(
            "src.llm_config.cost_calculator.get_llm_pricing", new_callable=AsyncMock
        ) as mock_get_pricing:
            mock_get_pricing.return_value = mock_pricing_data

            result = await LLMCostCalculator.calculate_cost_from_total_tokens_async(
                provider="openai",
                model="gpt-4",
                total_tokens=2000,
                output_ratio=0.5,
            )

            expected = await LLMCostCalculator.calculate_cost_async(
                provider="openai",
                model="gpt-4",
                input_tokens=1000,
                output_tokens=1000,
            )
            assert result == expected

    @pytest.mark.asyncio
    async def test_calculate_cost_from_total_tokens_async_validates_ratio(
        self, mock_pricing_data: dict
    ) -> None:
        """calculate_cost_from_total_tokens_async should validate output_ratio bounds."""
        from src.llm_config.cost_calculator import LLMCostCalculator

        with patch(
            "src.llm_config.cost_calculator.get_llm_pricing", new_callable=AsyncMock
        ) as mock_get_pricing:
            mock_get_pricing.return_value = mock_pricing_data

            with pytest.raises(ValueError, match=r"output_ratio must be between 0\.0 and 1\.0"):
                await LLMCostCalculator.calculate_cost_from_total_tokens_async(
                    provider="openai",
                    model="gpt-4",
                    total_tokens=1000,
                    output_ratio=1.5,
                )

    @pytest.mark.asyncio
    async def test_calculate_cost_from_total_tokens_async_with_custom_ratio(
        self, mock_pricing_data: dict
    ) -> None:
        """calculate_cost_from_total_tokens_async should apply custom output_ratio."""
        from src.llm_config.cost_calculator import LLMCostCalculator

        with patch(
            "src.llm_config.cost_calculator.get_llm_pricing", new_callable=AsyncMock
        ) as mock_get_pricing:
            mock_get_pricing.return_value = mock_pricing_data

            result = await LLMCostCalculator.calculate_cost_from_total_tokens_async(
                provider="openai",
                model="gpt-4",
                total_tokens=1000,
                output_ratio=0.3,
            )

            input_tokens = 700
            output_tokens = 300
            expected = (Decimal(input_tokens) / Decimal(1000) * Decimal("0.03")) + (
                Decimal(output_tokens) / Decimal(1000) * Decimal("0.06")
            )
            assert result == expected.quantize(Decimal("0.000001"))


class TestFetchModelsDevPricingSync:
    """Tests for fetch_models_dev_pricing_sync function."""

    def test_fetches_and_parses_api_response(self) -> None:
        """fetch_models_dev_pricing_sync should fetch and parse models.dev API."""
        from src.llm_config.cost_calculator import fetch_models_dev_pricing_sync

        api_response = {
            "openai": {
                "models": {
                    "gpt-4": {
                        "cost": {
                            "input": 30.0,
                            "output": 60.0,
                        }
                    }
                }
            }
        }

        with patch("src.llm_config.cost_calculator.httpx.Client") as mock_client_class:
            mock_client = mock_client_class.return_value.__enter__.return_value
            mock_response = Mock()
            mock_response.json.return_value = api_response
            mock_client.get.return_value = mock_response

            result = fetch_models_dev_pricing_sync()

            assert result is not None
            assert "openai" in result
            assert result["openai"]["gpt-4"]["input_price"] == Decimal("0.03")
            assert result["openai"]["gpt-4"]["output_price"] == Decimal("0.06")

    def test_returns_none_on_http_error(self) -> None:
        """fetch_models_dev_pricing_sync should return None on HTTP error."""
        import httpx

        from src.llm_config.cost_calculator import fetch_models_dev_pricing_sync

        with patch("src.llm_config.cost_calculator.httpx.Client") as mock_client_class:
            mock_client = mock_client_class.return_value.__enter__.return_value
            mock_client.get.side_effect = httpx.HTTPError("Connection failed")

            result = fetch_models_dev_pricing_sync()

            assert result is None

    def test_returns_none_on_timeout(self) -> None:
        """fetch_models_dev_pricing_sync should return None on timeout."""
        import httpx

        from src.llm_config.cost_calculator import fetch_models_dev_pricing_sync

        with patch("src.llm_config.cost_calculator.httpx.Client") as mock_client_class:
            mock_client = mock_client_class.return_value.__enter__.return_value
            mock_client.get.side_effect = httpx.TimeoutException("Timeout")

            result = fetch_models_dev_pricing_sync()

            assert result is None


class TestGetLlmPricingSync:
    """Tests for get_llm_pricing_sync function."""

    @pytest.fixture(autouse=True)
    def clear_cache(self) -> None:
        """Clear in-memory pricing cache before each test."""
        from src.llm_config.cost_calculator import clear_pricing_cache

        clear_pricing_cache()

    def test_returns_cached_data_when_available(self) -> None:
        """get_llm_pricing_sync returns in-memory cached data without fetch."""
        import src.llm_config.cost_calculator as cost_module
        from src.llm_config.cost_calculator import ModelPricing, get_llm_pricing_sync

        cached_pricing = {
            "test_provider": {
                "test_model": ModelPricing(
                    input_price=Decimal("0.01"),
                    output_price=Decimal("0.02"),
                ),
            },
        }
        cost_module._cache["pricing"] = cached_pricing

        with patch("src.llm_config.cost_calculator.fetch_models_dev_pricing_sync") as mock_fetch:
            result = get_llm_pricing_sync()

            mock_fetch.assert_not_called()
            assert result == cached_pricing

    def test_fetches_from_api_on_cache_miss(self) -> None:
        """get_llm_pricing_sync fetches from API when cache is empty."""
        from src.llm_config.cost_calculator import ModelPricing, get_llm_pricing_sync

        api_pricing = {
            "openai": {
                "gpt-4": ModelPricing(
                    input_price=Decimal("0.03"),
                    output_price=Decimal("0.06"),
                ),
            },
        }

        with patch("src.llm_config.cost_calculator.fetch_models_dev_pricing_sync") as mock_fetch:
            mock_fetch.return_value = api_pricing

            result = get_llm_pricing_sync()

            mock_fetch.assert_called_once()
            assert result["openai"]["gpt-4"]["input_price"] == Decimal("0.03")

    def test_raises_error_on_api_failure(self) -> None:
        """get_llm_pricing_sync raises PricingUnavailableError when API fails."""
        from src.llm_config.cost_calculator import PricingUnavailableError, get_llm_pricing_sync

        with patch("src.llm_config.cost_calculator.fetch_models_dev_pricing_sync") as mock_fetch:
            mock_fetch.return_value = None

            with pytest.raises(PricingUnavailableError):
                get_llm_pricing_sync()

            mock_fetch.assert_called_once()

    def test_populates_cache_after_successful_fetch(self) -> None:
        """get_llm_pricing_sync populates in-memory cache after fetch."""
        import src.llm_config.cost_calculator as cost_module
        from src.llm_config.cost_calculator import ModelPricing, get_llm_pricing_sync

        api_pricing = {
            "openai": {
                "gpt-4": ModelPricing(
                    input_price=Decimal("0.03"),
                    output_price=Decimal("0.06"),
                ),
            },
        }

        with patch("src.llm_config.cost_calculator.fetch_models_dev_pricing_sync") as mock_fetch:
            mock_fetch.return_value = api_pricing

            get_llm_pricing_sync()

            assert cost_module._cache["pricing"] == api_pricing


class TestClearPricingCache:
    """Tests for clear_pricing_cache function."""

    def test_clears_in_memory_cache(self) -> None:
        """clear_pricing_cache should reset the module-level cache."""
        import src.llm_config.cost_calculator as cost_module
        from src.llm_config.cost_calculator import ModelPricing, clear_pricing_cache

        cost_module._cache["pricing"] = {
            "test": {
                "model": ModelPricing(
                    input_price=Decimal("0.01"),
                    output_price=Decimal("0.02"),
                ),
            },
        }

        clear_pricing_cache()

        assert cost_module._cache["pricing"] is None


class TestLLMCostCalculatorSyncMethodsWithDynamicPricing:
    """Tests for sync methods using dynamic pricing."""

    @pytest.fixture(autouse=True)
    def clear_cache(self) -> None:
        """Clear in-memory pricing cache before each test."""
        from src.llm_config.cost_calculator import clear_pricing_cache

        clear_pricing_cache()

    @pytest.fixture
    def mock_pricing_data(self) -> dict:
        """Provides mock pricing data for tests."""
        from src.llm_config.cost_calculator import ModelPricing

        return {
            "openai": {
                "gpt-4": ModelPricing(
                    input_price=Decimal("0.03"),
                    output_price=Decimal("0.06"),
                ),
            },
            "anthropic": {
                "claude-3-opus": ModelPricing(
                    input_price=Decimal("0.015"),
                    output_price=Decimal("0.075"),
                ),
            },
        }

    def test_calculate_cost_uses_dynamic_pricing(self, mock_pricing_data: dict) -> None:
        """calculate_cost should use dynamic pricing from get_llm_pricing_sync."""
        from src.llm_config.cost_calculator import LLMCostCalculator

        with patch("src.llm_config.cost_calculator.get_llm_pricing_sync") as mock_get_pricing:
            mock_get_pricing.return_value = mock_pricing_data

            result = LLMCostCalculator.calculate_cost(
                provider="openai",
                model="gpt-4",
                input_tokens=1000,
                output_tokens=1000,
            )

            mock_get_pricing.assert_called()
            assert result == Decimal("0.090000")

    def test_get_model_pricing_uses_dynamic_pricing(self, mock_pricing_data: dict) -> None:
        """get_model_pricing should use dynamic pricing."""
        from src.llm_config.cost_calculator import LLMCostCalculator

        with patch("src.llm_config.cost_calculator.get_llm_pricing_sync") as mock_get_pricing:
            mock_get_pricing.return_value = mock_pricing_data

            result = LLMCostCalculator.get_model_pricing(
                provider="openai",
                model="gpt-4",
            )

            assert result == (Decimal("0.03"), Decimal("0.06"))

    def test_list_supported_providers_uses_dynamic_pricing(self, mock_pricing_data: dict) -> None:
        """list_supported_providers should use dynamic pricing."""
        from src.llm_config.cost_calculator import LLMCostCalculator

        with patch("src.llm_config.cost_calculator.get_llm_pricing_sync") as mock_get_pricing:
            mock_get_pricing.return_value = mock_pricing_data

            result = LLMCostCalculator.list_supported_providers()

            assert set(result) == {"openai", "anthropic"}

    def test_list_provider_models_uses_dynamic_pricing(self, mock_pricing_data: dict) -> None:
        """list_provider_models should use dynamic pricing."""
        from src.llm_config.cost_calculator import LLMCostCalculator

        with patch("src.llm_config.cost_calculator.get_llm_pricing_sync") as mock_get_pricing:
            mock_get_pricing.return_value = mock_pricing_data

            result = LLMCostCalculator.list_provider_models("openai")

            assert result == ["gpt-4"]

    def test_calculate_cost_raises_for_unknown_provider(self, mock_pricing_data: dict) -> None:
        """calculate_cost should raise ValueError for unknown provider."""
        from src.llm_config.cost_calculator import LLMCostCalculator

        with patch("src.llm_config.cost_calculator.get_llm_pricing_sync") as mock_get_pricing:
            mock_get_pricing.return_value = mock_pricing_data

            with pytest.raises(ValueError, match="Unknown provider: unknown"):
                LLMCostCalculator.calculate_cost(
                    provider="unknown",
                    model="model",
                    input_tokens=100,
                    output_tokens=100,
                )

    def test_calculate_cost_raises_for_unknown_model(self, mock_pricing_data: dict) -> None:
        """calculate_cost should raise ValueError for unknown model."""
        from src.llm_config.cost_calculator import LLMCostCalculator

        with patch("src.llm_config.cost_calculator.get_llm_pricing_sync") as mock_get_pricing:
            mock_get_pricing.return_value = mock_pricing_data

            with pytest.raises(ValueError, match="Unknown model 'unknown-model'"):
                LLMCostCalculator.calculate_cost(
                    provider="openai",
                    model="unknown-model",
                    input_tokens=100,
                    output_tokens=100,
                )
