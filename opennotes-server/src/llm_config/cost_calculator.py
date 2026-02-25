"""
Cost calculator for LLM API usage.

Provides cost calculation for different LLM providers and models
using litellm's built-in pricing data.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from litellm import completion_cost, cost_per_token, model_cost

from src.llm_config.model_id import ModelId

logger = logging.getLogger(__name__)


class LLMCostCalculator:
    """
    Calculates costs for LLM API usage based on litellm's bundled pricing data.

    Uses litellm.model_cost for pricing information - no external API calls needed.
    All costs are returned in USD.
    """

    @classmethod
    def calculate_cost(
        cls,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> Decimal:
        """
        Calculate the cost of an LLM API call based on token usage.

        Args:
            model: Model identifier (e.g., 'gpt-4', 'claude-3-opus-20240229',
                   or with provider prefix 'anthropic/claude-3-opus-20240229')
            input_tokens: Number of input (prompt) tokens
            output_tokens: Number of output (completion) tokens

        Returns:
            Cost in USD as a Decimal (precise to 6 decimal places)

        Raises:
            ValueError: If model is not found in litellm's pricing data
        """
        try:
            input_cost, output_cost = cost_per_token(
                model=model,
                prompt_tokens=input_tokens,
                completion_tokens=output_tokens,
            )
            total = Decimal(str(input_cost)) + Decimal(str(output_cost))
            return total.quantize(Decimal("0.000001"))
        except Exception as e:
            raise ValueError(f"Unable to calculate cost for model '{model}': {e}") from e

    @classmethod
    def calculate_cost_from_response(
        cls,
        response: Any,
        model: str | None = None,
    ) -> Decimal:
        """
        Calculate cost from a litellm completion response object.

        This is the preferred method when you have a response from litellm.completion()
        as it handles prompt caching and other provider-specific cost variations.

        Args:
            response: The completion response object from litellm.completion()
            model: Optional model override (uses response's model if not specified)

        Returns:
            Cost in USD as a Decimal (precise to 6 decimal places)
        """
        cost = completion_cost(completion_response=response, model=model)
        return Decimal(str(cost)).quantize(Decimal("0.000001"))

    @classmethod
    def get_model_pricing(
        cls,
        model: str,
    ) -> tuple[Decimal, Decimal]:
        """
        Get pricing information for a specific model.

        Prices are returned as cost per token (not per 1K tokens).

        Args:
            model: Model identifier (e.g., 'gpt-4', 'anthropic/claude-3-opus')

        Returns:
            Tuple of (input_cost_per_token, output_cost_per_token) as Decimals

        Raises:
            ValueError: If model is not found in litellm's pricing data
        """
        if model not in model_cost:
            available_models = cls._get_similar_models(model)
            hint = f" Similar models: {', '.join(available_models[:5])}" if available_models else ""
            raise ValueError(f"Unknown model: {model}.{hint}")

        info = model_cost[model]
        input_price = Decimal(str(info.get("input_cost_per_token", 0)))
        output_price = Decimal(str(info.get("output_cost_per_token", 0)))
        return (input_price, output_price)

    @classmethod
    def list_supported_models(cls) -> list[str]:
        """
        List all models with pricing in litellm's model_cost dictionary.

        Returns:
            List of model identifiers (may include provider prefixes)
        """
        return list(model_cost.keys())

    @classmethod
    def is_model_supported(cls, model: str) -> bool:
        """
        Check if a model is supported (has pricing data).

        Args:
            model: Model identifier to check

        Returns:
            True if model has pricing data, False otherwise
        """
        return model in model_cost

    @classmethod
    def _get_similar_models(cls, model: str, limit: int = 5) -> list[str]:
        """
        Get models that contain the search term.

        Helper for error messages to suggest similar models.
        """
        search = model.lower()
        matches = [m for m in model_cost if search in m.lower()]
        return sorted(matches)[:limit]

    @classmethod
    async def calculate_cost_async(
        cls,
        model_id: ModelId,
        input_tokens: int,
        output_tokens: int,
    ) -> Decimal:
        """
        Async wrapper for calculate_cost (litellm's cost functions are synchronous).

        Args:
            model_id: ModelId identifying the provider and model
            input_tokens: Number of input (prompt) tokens
            output_tokens: Number of output (completion) tokens

        Returns:
            Cost in USD as a Decimal (precise to 6 decimal places)
        """
        litellm_model = model_id.to_litellm()
        try:
            return cls.calculate_cost(litellm_model, input_tokens, output_tokens)
        except ValueError:
            return cls.calculate_cost(model_id.model, input_tokens, output_tokens)

    @classmethod
    async def calculate_cost_from_total_tokens_async(
        cls,
        model_id: ModelId,
        total_tokens: int,
    ) -> Decimal:
        """
        Calculate cost when only total tokens are known (no input/output breakdown).

        Uses a conservative 50/50 split between input and output tokens.
        This is an approximation - prefer calculate_cost_async when token breakdown is available.

        Args:
            model_id: ModelId identifying the provider and model
            total_tokens: Total token count (input + output)

        Returns:
            Cost in USD as a Decimal (precise to 6 decimal places)
        """
        input_tokens = total_tokens // 2
        output_tokens = total_tokens - input_tokens
        return await cls.calculate_cost_async(model_id, input_tokens, output_tokens)
