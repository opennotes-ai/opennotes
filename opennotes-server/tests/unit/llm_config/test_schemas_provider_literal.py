"""Tests ensuring LLMConfig schemas' provider Literal matches the factory's registered keys.

Regression guard for TASK-1450.13: the Literal used to advertise providers like
``google``, ``cohere``, and ``custom`` that the factory does not implement, while
omitting the actual ``vertex_ai`` key. This caused router calls with "google" to
pass schema validation and then crash inside the factory.
"""

from __future__ import annotations

from typing import get_args

import pytest
from pydantic import ValidationError

from src.llm_config.providers.factory import LLMProviderFactory
from src.llm_config.schemas import LLMConfigCreate, LLMConfigTestRequest


def _provider_literal_values(model: type, field_name: str) -> tuple[str, ...]:
    """Return the Literal choices advertised for ``field_name`` on ``model``."""
    annotation = model.model_fields[field_name].annotation
    return tuple(get_args(annotation))


class TestProviderLiteralMatchesFactory:
    """Schema Literals must stay in sync with LLMProviderFactory._providers."""

    def test_llm_config_create_provider_literal_matches_factory_keys(self) -> None:
        literal_values = set(_provider_literal_values(LLMConfigCreate, "provider"))
        factory_keys = set(LLMProviderFactory.list_providers())
        assert literal_values == factory_keys, (
            "LLMConfigCreate.provider Literal diverges from LLMProviderFactory keys: "
            f"literal={literal_values!r} factory={factory_keys!r}"
        )

    def test_llm_config_test_request_provider_literal_matches_factory_keys(self) -> None:
        literal_values = set(_provider_literal_values(LLMConfigTestRequest, "provider"))
        factory_keys = set(LLMProviderFactory.list_providers())
        assert literal_values == factory_keys, (
            "LLMConfigTestRequest.provider Literal diverges from LLMProviderFactory keys: "
            f"literal={literal_values!r} factory={factory_keys!r}"
        )

    def test_vertex_ai_is_accepted_on_create(self) -> None:
        config = LLMConfigCreate(provider="vertex_ai", api_key="any-key")
        assert config.provider == "vertex_ai"

    def test_vertex_ai_is_accepted_on_test_request(self) -> None:
        req = LLMConfigTestRequest(provider="vertex_ai", api_key="any-key")
        assert req.provider == "vertex_ai"

    @pytest.mark.parametrize("stale_value", ["google", "cohere", "custom"])
    def test_stale_provider_values_are_rejected_on_create(self, stale_value: str) -> None:
        with pytest.raises(ValidationError):
            LLMConfigCreate(provider=stale_value, api_key="any-key")  # type: ignore[arg-type]

    @pytest.mark.parametrize("stale_value", ["google", "cohere", "custom"])
    def test_stale_provider_values_are_rejected_on_test_request(self, stale_value: str) -> None:
        with pytest.raises(ValidationError):
            LLMConfigTestRequest(provider=stale_value, api_key="any-key")  # type: ignore[arg-type]
