"""Unit tests for LiteLLMProvider empty response guard."""

from unittest.mock import AsyncMock, patch

import pytest
from litellm.exceptions import JSONSchemaValidationError

from src.llm_config.providers.base import LLMMessage
from src.llm_config.providers.litellm_provider import (
    EmptyLLMResponseError,
    LiteLLMCompletionParams,
    LiteLLMProvider,
    LiteLLMProviderSettings,
)


class TestEmptyResponseGuard:
    @pytest.fixture
    def provider(self) -> LiteLLMProvider:
        return LiteLLMProvider(
            api_key="test-key",
            default_model="openai/gpt-5-mini",
            settings=LiteLLMProviderSettings(),
            provider_name="openai",
        )

    @pytest.mark.asyncio
    async def test_empty_string_raw_response_raises_empty_llm_response_error(
        self, provider: LiteLLMProvider
    ) -> None:
        exc = JSONSchemaValidationError(
            model="gpt-5-mini",
            llm_provider="openai",
            raw_response="",
            schema="RelevanceCheckResult",
        )
        with patch("src.llm_config.providers.litellm_provider.litellm") as mock:
            mock.acompletion = AsyncMock(side_effect=exc)
            with pytest.raises(EmptyLLMResponseError, match="empty response"):
                await provider.complete(
                    [LLMMessage(role="user", content="test")],
                    LiteLLMCompletionParams(),
                )

    @pytest.mark.asyncio
    async def test_whitespace_only_raw_response_raises_empty_llm_response_error(
        self, provider: LiteLLMProvider
    ) -> None:
        exc = JSONSchemaValidationError(
            model="gpt-5-mini",
            llm_provider="openai",
            raw_response="   ",
            schema="RelevanceCheckResult",
        )
        with patch("src.llm_config.providers.litellm_provider.litellm") as mock:
            mock.acompletion = AsyncMock(side_effect=exc)
            with pytest.raises(EmptyLLMResponseError):
                await provider.complete(
                    [LLMMessage(role="user", content="test")],
                    LiteLLMCompletionParams(),
                )

    @pytest.mark.asyncio
    async def test_nonempty_raw_response_reraises_json_schema_error(
        self, provider: LiteLLMProvider
    ) -> None:
        exc = JSONSchemaValidationError(
            model="gpt-5-mini",
            llm_provider="openai",
            raw_response='{"bad": true}',
            schema="RelevanceCheckResult",
        )
        with patch("src.llm_config.providers.litellm_provider.litellm") as mock:
            mock.acompletion = AsyncMock(side_effect=exc)
            with pytest.raises(JSONSchemaValidationError):
                await provider.complete(
                    [LLMMessage(role="user", content="test")],
                    LiteLLMCompletionParams(),
                )

    @pytest.mark.asyncio
    async def test_none_raw_response_raises_empty_llm_response_error(
        self, provider: LiteLLMProvider
    ) -> None:
        exc = JSONSchemaValidationError(
            model="gpt-5-mini",
            llm_provider="openai",
            raw_response="",
            schema="RelevanceCheckResult",
        )
        exc.raw_response = None  # type: ignore[attr-defined]
        with patch("src.llm_config.providers.litellm_provider.litellm") as mock:
            mock.acompletion = AsyncMock(side_effect=exc)
            with pytest.raises(EmptyLLMResponseError):
                await provider.complete(
                    [LLMMessage(role="user", content="test")],
                    LiteLLMCompletionParams(),
                )

    @pytest.mark.asyncio
    async def test_empty_response_error_chains_original_exception(
        self, provider: LiteLLMProvider
    ) -> None:
        exc = JSONSchemaValidationError(
            model="gpt-5-mini",
            llm_provider="openai",
            raw_response="",
            schema="RelevanceCheckResult",
        )
        with patch("src.llm_config.providers.litellm_provider.litellm") as mock:
            mock.acompletion = AsyncMock(side_effect=exc)
            with pytest.raises(EmptyLLMResponseError) as exc_info:
                await provider.complete(
                    [LLMMessage(role="user", content="test")],
                    LiteLLMCompletionParams(),
                )
            assert exc_info.value.__cause__ is exc
