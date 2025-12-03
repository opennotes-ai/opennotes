"""
Cost calculator for LLM API usage.

Provides pricing information for different LLM providers and models,
with automatic cost calculation based on token usage.
"""

import logging
from decimal import Decimal
from typing import TypedDict

import httpx

from src.cache.cache import cache_manager
from src.config import settings

logger = logging.getLogger(__name__)

MODELS_DEV_API_URL = "https://models.dev/api.json"
MODELS_DEV_TIMEOUT = 30.0

LLM_PRICING_CACHE_KEY = "llm_pricing:all"

# Module-level in-memory cache shared between sync and async methods
# Using a mutable container to avoid 'global' statement warnings
_cache: dict[str, "AllPricing | None"] = {"pricing": None}


class ModelPricing(TypedDict):
    """Pricing information for a single model."""

    input_price: Decimal
    output_price: Decimal


ProviderPricing = dict[str, ModelPricing]
AllPricing = dict[str, ProviderPricing]


class LLMCostCalculator:
    """
    Calculates costs for LLM API usage based on provider-specific pricing.

    Pricing is fetched dynamically from models.dev API with caching.
    All prices are in USD per 1000 tokens.
    """

    @classmethod
    def calculate_cost(
        cls,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> Decimal:
        """
        Calculate the cost of an LLM API call based on token usage.

        Uses dynamic pricing from models.dev API with caching.

        Args:
            provider: Provider name (e.g., 'openai', 'anthropic')
            model: Model identifier (e.g., 'gpt-4', 'claude-3-opus-20240229')
            input_tokens: Number of input (prompt) tokens
            output_tokens: Number of output (completion) tokens

        Returns:
            Cost in USD as a Decimal (precise to 6 decimal places)

        Raises:
            ValueError: If provider or model is not found in pricing data
        """
        pricing_data = get_llm_pricing_sync()
        provider = provider.lower()

        if provider not in pricing_data:
            raise ValueError(f"Unknown provider: {provider}")

        if model not in pricing_data[provider]:
            raise ValueError(
                f"Unknown model '{model}' for provider '{provider}'. "
                f"Available models: {', '.join(pricing_data[provider].keys())}"
            )

        model_pricing = pricing_data[provider][model]
        input_cost = (Decimal(input_tokens) / Decimal(1000)) * model_pricing["input_price"]
        output_cost = (Decimal(output_tokens) / Decimal(1000)) * model_pricing["output_price"]

        total_cost = input_cost + output_cost

        return total_cost.quantize(Decimal("0.000001"))

    @classmethod
    def calculate_cost_from_total_tokens(
        cls,
        provider: str,
        model: str,
        total_tokens: int,
        output_ratio: float = 0.5,
    ) -> Decimal:
        """
        Calculate cost when only total token count is available.

        Uses an estimated output ratio to split tokens between input and output.
        Default assumes 50% input, 50% output, but this can be adjusted based
        on typical usage patterns for the model.

        Args:
            provider: Provider name
            model: Model identifier
            total_tokens: Total number of tokens used
            output_ratio: Estimated ratio of output tokens to total (0.0-1.0)

        Returns:
            Estimated cost in USD as a Decimal

        Raises:
            ValueError: If provider/model not found or output_ratio invalid
        """
        if not 0.0 <= output_ratio <= 1.0:
            raise ValueError("output_ratio must be between 0.0 and 1.0")

        output_tokens = int(total_tokens * output_ratio)
        input_tokens = total_tokens - output_tokens

        return cls.calculate_cost(provider, model, input_tokens, output_tokens)

    @classmethod
    def get_model_pricing(
        cls,
        provider: str,
        model: str,
    ) -> tuple[Decimal, Decimal]:
        """
        Get pricing information for a specific model.

        Uses dynamic pricing from models.dev API with caching.

        Args:
            provider: Provider name
            model: Model identifier

        Returns:
            Tuple of (input_price_per_1k_tokens, output_price_per_1k_tokens)

        Raises:
            ValueError: If provider or model is not found
        """
        pricing_data = get_llm_pricing_sync()
        provider = provider.lower()

        if provider not in pricing_data:
            raise ValueError(f"Unknown provider: {provider}")

        if model not in pricing_data[provider]:
            raise ValueError(f"Unknown model '{model}' for provider '{provider}'")

        p = pricing_data[provider][model]
        return (p["input_price"], p["output_price"])

    @classmethod
    def list_supported_providers(cls) -> list[str]:
        """
        List all supported LLM providers.

        Uses dynamic pricing from models.dev API with caching.

        Returns:
            List of provider names
        """
        pricing_data = get_llm_pricing_sync()
        return list(pricing_data.keys())

    @classmethod
    def list_provider_models(cls, provider: str) -> list[str]:
        """
        List all supported models for a specific provider.

        Uses dynamic pricing from models.dev API with caching.

        Args:
            provider: Provider name

        Returns:
            List of model identifiers

        Raises:
            ValueError: If provider is not found
        """
        pricing_data = get_llm_pricing_sync()
        provider = provider.lower()

        if provider not in pricing_data:
            raise ValueError(f"Unknown provider: {provider}")

        return list(pricing_data[provider].keys())

    @classmethod
    async def calculate_cost_async(
        cls,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> Decimal:
        """
        Calculate cost using dynamic pricing from models.dev API.

        Args:
            provider: Provider name (e.g., 'openai', 'anthropic')
            model: Model identifier (e.g., 'gpt-4', 'claude-3-opus-20240229')
            input_tokens: Number of input (prompt) tokens
            output_tokens: Number of output (completion) tokens

        Returns:
            Cost in USD as a Decimal (precise to 6 decimal places)

        Raises:
            ValueError: If provider or model is not found in pricing data
        """
        pricing_data = await get_llm_pricing()
        provider = provider.lower()

        if provider not in pricing_data:
            raise ValueError(f"Unknown provider: {provider}")

        if model not in pricing_data[provider]:
            raise ValueError(
                f"Unknown model '{model}' for provider '{provider}'. "
                f"Available models: {', '.join(pricing_data[provider].keys())}"
            )

        model_pricing = pricing_data[provider][model]
        input_cost = (Decimal(input_tokens) / Decimal(1000)) * model_pricing["input_price"]
        output_cost = (Decimal(output_tokens) / Decimal(1000)) * model_pricing["output_price"]

        return (input_cost + output_cost).quantize(Decimal("0.000001"))

    @classmethod
    async def calculate_cost_from_total_tokens_async(
        cls,
        provider: str,
        model: str,
        total_tokens: int,
        output_ratio: float = 0.5,
    ) -> Decimal:
        """
        Calculate cost when only total token count is available, using dynamic pricing.

        Uses an estimated output ratio to split tokens between input and output.
        Default assumes 50% input, 50% output.

        Args:
            provider: Provider name
            model: Model identifier
            total_tokens: Total number of tokens used
            output_ratio: Estimated ratio of output tokens to total (0.0-1.0)

        Returns:
            Estimated cost in USD as a Decimal

        Raises:
            ValueError: If provider/model not found or output_ratio invalid
        """
        if not 0.0 <= output_ratio <= 1.0:
            raise ValueError("output_ratio must be between 0.0 and 1.0")

        output_tokens = int(total_tokens * output_ratio)
        input_tokens = total_tokens - output_tokens

        return await cls.calculate_cost_async(provider, model, input_tokens, output_tokens)

    @classmethod
    async def get_model_pricing_async(
        cls,
        provider: str,
        model: str,
    ) -> tuple[Decimal, Decimal]:
        """
        Get pricing information for a specific model using dynamic data.

        Args:
            provider: Provider name
            model: Model identifier

        Returns:
            Tuple of (input_price_per_1k_tokens, output_price_per_1k_tokens)

        Raises:
            ValueError: If provider or model is not found
        """
        pricing_data = await get_llm_pricing()
        provider = provider.lower()

        if provider not in pricing_data:
            raise ValueError(f"Unknown provider: {provider}")

        if model not in pricing_data[provider]:
            raise ValueError(f"Unknown model '{model}' for provider '{provider}'")

        p = pricing_data[provider][model]
        return (p["input_price"], p["output_price"])

    @classmethod
    async def list_supported_providers_async(cls) -> list[str]:
        """
        List all supported LLM providers from dynamic pricing data.

        Returns:
            List of provider names
        """
        pricing_data = await get_llm_pricing()
        return list(pricing_data.keys())

    @classmethod
    async def list_provider_models_async(cls, provider: str) -> list[str]:
        """
        List all supported models for a specific provider from dynamic pricing data.

        Args:
            provider: Provider name

        Returns:
            List of model identifiers

        Raises:
            ValueError: If provider is not found
        """
        pricing_data = await get_llm_pricing()
        provider = provider.lower()

        if provider not in pricing_data:
            raise ValueError(f"Unknown provider: {provider}")

        return list(pricing_data[provider].keys())


async def fetch_models_dev_pricing() -> AllPricing | None:
    """
    Fetch pricing data from models.dev API.

    Returns:
        AllPricing dict mapping provider -> model -> pricing, or None on error
    """
    try:
        async with httpx.AsyncClient(timeout=MODELS_DEV_TIMEOUT) as client:
            response = await client.get(MODELS_DEV_API_URL)
            response.raise_for_status()
            data = response.json()

        return _map_models_dev_response(data)
    except (httpx.HTTPError, httpx.TimeoutException) as e:
        logger.warning(f"Failed to fetch pricing from models.dev: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error fetching pricing: {e}")
        return None


def _map_models_dev_response(data: dict) -> AllPricing:
    """Map models.dev API response to our pricing format."""
    result: AllPricing = {}

    for provider_id, provider_data in data.items():
        if not isinstance(provider_data, dict) or "models" not in provider_data:
            continue

        models = provider_data["models"]
        if not isinstance(models, dict):
            continue

        provider_pricing: ProviderPricing = {}
        for model_id, model_data in models.items():
            if not isinstance(model_data, dict):
                continue
            cost = model_data.get("cost", {})
            if not isinstance(cost, dict):
                continue

            input_price = cost.get("input")
            output_price = cost.get("output")

            if input_price is not None and output_price is not None:
                provider_pricing[model_id] = ModelPricing(
                    input_price=Decimal(str(input_price)) / 1000,
                    output_price=Decimal(str(output_price)) / 1000,
                )

        if provider_pricing:
            result[provider_id] = provider_pricing

    return result


class PricingUnavailableError(Exception):
    """Raised when LLM pricing data cannot be fetched from any source."""


async def get_llm_pricing() -> AllPricing:
    """
    Get LLM pricing data with caching.

    Order of precedence:
    1. In-memory cache (shared with sync methods)
    2. Redis cache (if available)
    3. Fresh fetch from models.dev API

    Returns:
        AllPricing dict with provider -> model -> pricing

    Raises:
        PricingUnavailableError: If pricing cannot be fetched from any source
    """
    if _cache["pricing"] is not None:
        return _cache["pricing"]

    cached = await cache_manager.get(LLM_PRICING_CACHE_KEY)
    if cached is not None:
        pricing = _deserialize_pricing(cached)
        _cache["pricing"] = pricing
        return pricing

    pricing = await fetch_models_dev_pricing()
    if pricing is not None:
        _cache["pricing"] = pricing
        await cache_manager.set(
            LLM_PRICING_CACHE_KEY,
            _serialize_pricing(pricing),
            ttl=settings.CACHE_LLM_PRICING_TTL,
        )
        return pricing

    logger.error("Failed to fetch LLM pricing from all sources")
    raise PricingUnavailableError(
        "Unable to fetch LLM pricing data. Check network connectivity to models.dev API."
    )


def _serialize_pricing(pricing: AllPricing) -> dict:
    """Serialize pricing for cache storage (Decimal -> str)."""
    return {
        provider: {
            model: {
                "input_price": str(p["input_price"]),
                "output_price": str(p["output_price"]),
            }
            for model, p in models.items()
        }
        for provider, models in pricing.items()
    }


def _deserialize_pricing(data: dict) -> AllPricing:
    """Deserialize pricing from cache (str -> Decimal)."""
    return {
        provider: {
            model: ModelPricing(
                input_price=Decimal(p["input_price"]),
                output_price=Decimal(p["output_price"]),
            )
            for model, p in models.items()
        }
        for provider, models in data.items()
    }


def fetch_models_dev_pricing_sync() -> AllPricing | None:
    """
    Fetch pricing data from models.dev API synchronously.

    Returns:
        AllPricing dict mapping provider -> model -> pricing, or None on error
    """
    try:
        with httpx.Client(timeout=MODELS_DEV_TIMEOUT) as client:
            response = client.get(MODELS_DEV_API_URL)
            response.raise_for_status()
            data = response.json()

        return _map_models_dev_response(data)
    except (httpx.HTTPError, httpx.TimeoutException) as e:
        logger.warning(f"Failed to fetch pricing from models.dev (sync): {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error fetching pricing (sync): {e}")
        return None


def get_llm_pricing_sync() -> AllPricing:
    """
    Get LLM pricing data synchronously with in-memory cache.

    Order of precedence:
    1. In-memory cache (populated by async methods or previous sync calls)
    2. Fresh fetch from models.dev API (sync)

    Returns:
        AllPricing dict with provider -> model -> pricing

    Raises:
        PricingUnavailableError: If pricing cannot be fetched from any source
    """
    if _cache["pricing"] is not None:
        return _cache["pricing"]

    pricing = fetch_models_dev_pricing_sync()
    if pricing is not None:
        _cache["pricing"] = pricing
        return pricing

    logger.error("Failed to fetch LLM pricing from all sources (sync)")
    raise PricingUnavailableError(
        "Unable to fetch LLM pricing data. Check network connectivity to models.dev API."
    )


def clear_pricing_cache() -> None:
    """
    Clear the in-memory pricing cache.

    Useful for testing and forcing a fresh fetch on next call.
    """
    _cache["pricing"] = None
