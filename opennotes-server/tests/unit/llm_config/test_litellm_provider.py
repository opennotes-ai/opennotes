"""Unit tests for LiteLLM provider."""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.llm_config.providers.base import LLMMessage
from src.llm_config.providers.litellm_provider import (
    LiteLLMCompletionParams,
    LiteLLMProvider,
    LiteLLMProviderSettings,
)


class TestLiteLLMProviderSettings:
    """Tests for LiteLLMProviderSettings configuration."""

    def test_default_values(self) -> None:
        """Verify default settings match expected values."""
        settings = LiteLLMProviderSettings()
        assert settings.timeout == 30.0
        assert settings.max_tokens == 4096
        assert settings.temperature == 0.7

    def test_custom_values(self) -> None:
        """Verify custom settings are accepted."""
        settings = LiteLLMProviderSettings(
            timeout=60.0,
            max_tokens=8192,
            temperature=0.5,
        )
        assert settings.timeout == 60.0
        assert settings.max_tokens == 8192
        assert settings.temperature == 0.5

    def test_invalid_timeout_rejected(self) -> None:
        """Negative timeout should be rejected."""
        with pytest.raises(ValueError, match="greater than 0"):
            LiteLLMProviderSettings(timeout=-1)

    def test_invalid_temperature_rejected(self) -> None:
        """Temperature outside 0-2 range should be rejected."""
        with pytest.raises(ValueError, match="less than or equal to 2"):
            LiteLLMProviderSettings(temperature=3.0)


class TestLiteLLMCompletionParams:
    """Tests for LiteLLMCompletionParams."""

    def test_all_params_optional(self) -> None:
        """All params should default to None."""
        params = LiteLLMCompletionParams()
        assert params.model is None
        assert params.max_tokens is None
        assert params.temperature is None
        assert params.top_p is None
        assert params.frequency_penalty is None
        assert params.presence_penalty is None

    def test_set_specific_params(self) -> None:
        """Setting specific params should work."""
        params = LiteLLMCompletionParams(
            temperature=0.5,
            presence_penalty=0.3,
        )
        assert params.temperature == 0.5
        assert params.presence_penalty == 0.3
        assert params.frequency_penalty is None


class TestLiteLLMProvider:
    """Tests for LiteLLMProvider implementation."""

    @pytest.fixture
    def provider(self) -> LiteLLMProvider:
        """Create a test provider instance."""
        return LiteLLMProvider(
            api_key="test-api-key",
            default_model="openai/gpt-5.1",
            settings=LiteLLMProviderSettings(),
        )

    @pytest.fixture
    def mock_response(self) -> MagicMock:
        """Create a mock LiteLLM response."""
        response = MagicMock()
        response.choices = [
            MagicMock(
                message=MagicMock(content="Hello! How can I help you?"),
                finish_reason="stop",
            )
        ]
        response.model = "gpt-5.1"
        response.usage = MagicMock(total_tokens=25)
        return response

    def test_filter_none_params_removes_none_values(self, provider: LiteLLMProvider) -> None:
        """_filter_none_params should remove all None values."""
        params = {
            "model": "gpt-5.1",
            "temperature": 0.7,
            "presence_penalty": None,
            "frequency_penalty": None,
            "top_p": 0.9,
        }
        filtered = provider._filter_none_params(params)
        assert filtered == {
            "model": "gpt-5.1",
            "temperature": 0.7,
            "top_p": 0.9,
        }
        assert "presence_penalty" not in filtered
        assert "frequency_penalty" not in filtered

    def test_filter_none_params_keeps_zero_values(self, provider: LiteLLMProvider) -> None:
        """_filter_none_params should keep zero (falsy but not None) values."""
        params = {
            "temperature": 0,
            "presence_penalty": 0.0,
            "max_tokens": 0,
        }
        filtered = provider._filter_none_params(params)
        assert filtered == params

    @pytest.mark.asyncio
    async def test_complete_filters_none_params(
        self, provider: LiteLLMProvider, mock_response: MagicMock
    ) -> None:
        """complete() should filter out None params before calling litellm."""
        with patch("src.llm_config.providers.litellm_provider.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(return_value=mock_response)

            messages = [LLMMessage(role="user", content="Hi")]
            await provider.complete(messages)

            call_kwargs = mock_litellm.acompletion.call_args.kwargs
            assert "presence_penalty" not in call_kwargs
            assert "frequency_penalty" not in call_kwargs
            assert "top_p" not in call_kwargs

    @pytest.mark.asyncio
    async def test_complete_includes_non_none_params(
        self, provider: LiteLLMProvider, mock_response: MagicMock
    ) -> None:
        """complete() should include params that have non-None values."""
        with patch("src.llm_config.providers.litellm_provider.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(return_value=mock_response)

            messages = [LLMMessage(role="user", content="Hi")]
            params = LiteLLMCompletionParams(presence_penalty=0.5, frequency_penalty=0.3)
            await provider.complete(messages, params)

            call_kwargs = mock_litellm.acompletion.call_args.kwargs
            assert call_kwargs["presence_penalty"] == 0.5
            assert call_kwargs["frequency_penalty"] == 0.3

    @pytest.mark.asyncio
    async def test_complete_returns_llm_response(
        self, provider: LiteLLMProvider, mock_response: MagicMock
    ) -> None:
        """complete() should return properly structured LLMResponse."""
        with patch("src.llm_config.providers.litellm_provider.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(return_value=mock_response)

            messages = [LLMMessage(role="user", content="Hi")]
            response = await provider.complete(messages)

            assert response.content == "Hello! How can I help you?"
            assert response.model == "gpt-5.1"
            assert response.tokens_used == 25
            assert response.finish_reason == "stop"
            assert response.provider == "litellm"

    @pytest.mark.asyncio
    async def test_complete_uses_default_model(
        self, provider: LiteLLMProvider, mock_response: MagicMock
    ) -> None:
        """complete() should use default model when not specified in params."""
        with patch("src.llm_config.providers.litellm_provider.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(return_value=mock_response)

            messages = [LLMMessage(role="user", content="Hi")]
            await provider.complete(messages)

            call_kwargs = mock_litellm.acompletion.call_args.kwargs
            assert call_kwargs["model"] == "openai/gpt-5.1"

    @pytest.mark.asyncio
    async def test_complete_uses_param_model_when_specified(
        self, provider: LiteLLMProvider, mock_response: MagicMock
    ) -> None:
        """complete() should use model from params when specified."""
        with patch("src.llm_config.providers.litellm_provider.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(return_value=mock_response)

            messages = [LLMMessage(role="user", content="Hi")]
            params = LiteLLMCompletionParams(model="anthropic/claude-3-opus")
            await provider.complete(messages, params)

            call_kwargs = mock_litellm.acompletion.call_args.kwargs
            assert call_kwargs["model"] == "anthropic/claude-3-opus"

    @pytest.mark.asyncio
    async def test_complete_handles_missing_usage(self, provider: LiteLLMProvider) -> None:
        """complete() should handle response with missing usage data."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Hi"), finish_reason="stop")]
        mock_response.model = "gpt-5.1"
        mock_response.usage = None

        with patch("src.llm_config.providers.litellm_provider.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(return_value=mock_response)

            messages = [LLMMessage(role="user", content="Hi")]
            response = await provider.complete(messages)

            assert response.tokens_used == 0

    @pytest.mark.asyncio
    async def test_complete_handles_empty_content(self, provider: LiteLLMProvider) -> None:
        """complete() should handle response with empty content."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content=None), finish_reason="stop")]
        mock_response.model = "gpt-5.1"
        mock_response.usage = MagicMock(total_tokens=10)

        with patch("src.llm_config.providers.litellm_provider.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(return_value=mock_response)

            messages = [LLMMessage(role="user", content="Hi")]
            response = await provider.complete(messages)

            assert response.content == ""

    @pytest.mark.asyncio
    async def test_stream_complete_yields_chunks(self, provider: LiteLLMProvider) -> None:
        """stream_complete() should yield content chunks."""

        async def mock_stream():
            chunks = [
                MagicMock(choices=[MagicMock(delta=MagicMock(content="Hello"))]),
                MagicMock(choices=[MagicMock(delta=MagicMock(content=" world"))]),
                MagicMock(choices=[MagicMock(delta=MagicMock(content="!"))]),
            ]
            for chunk in chunks:
                yield chunk

        with patch("src.llm_config.providers.litellm_provider.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(return_value=mock_stream())

            messages = [LLMMessage(role="user", content="Hi")]
            chunks = []
            async for chunk in provider.stream_complete(messages):
                chunks.append(chunk)

            assert chunks == ["Hello", " world", "!"]

    @pytest.mark.asyncio
    async def test_stream_complete_skips_empty_chunks(self, provider: LiteLLMProvider) -> None:
        """stream_complete() should skip chunks with empty/None content."""

        async def mock_stream():
            chunks = [
                MagicMock(choices=[MagicMock(delta=MagicMock(content="Hello"))]),
                MagicMock(choices=[MagicMock(delta=MagicMock(content=None))]),
                MagicMock(choices=[MagicMock(delta=MagicMock(content=""))]),
                MagicMock(choices=[MagicMock(delta=MagicMock(content=" world"))]),
            ]
            for chunk in chunks:
                yield chunk

        with patch("src.llm_config.providers.litellm_provider.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(return_value=mock_stream())

            messages = [LLMMessage(role="user", content="Hi")]
            chunks = []
            async for chunk in provider.stream_complete(messages):
                chunks.append(chunk)

            assert chunks == ["Hello", " world"]

    @pytest.mark.asyncio
    async def test_validate_api_key_returns_true_on_success(
        self, provider: LiteLLMProvider, mock_response: MagicMock
    ) -> None:
        """validate_api_key() should return True when API call succeeds."""
        with patch("src.llm_config.providers.litellm_provider.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(return_value=mock_response)

            result = await provider.validate_api_key()

            assert result is True
            call_kwargs = mock_litellm.acompletion.call_args.kwargs
            assert call_kwargs["max_tokens"] == 1

    @pytest.mark.asyncio
    async def test_validate_api_key_returns_false_on_failure(
        self, provider: LiteLLMProvider
    ) -> None:
        """validate_api_key() should return False when API call fails."""
        with patch("src.llm_config.providers.litellm_provider.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(side_effect=Exception("Invalid API key"))

            result = await provider.validate_api_key()

            assert result is False

    @pytest.mark.asyncio
    async def test_close_clears_api_key(self, provider: LiteLLMProvider) -> None:
        """close() should clear the API key."""
        assert provider.api_key == "test-api-key"

        await provider.close()

        assert provider.api_key == ""

    @pytest.mark.asyncio
    async def test_complete_propagates_api_error(self, provider: LiteLLMProvider) -> None:
        """complete() should propagate API errors."""
        with patch("src.llm_config.providers.litellm_provider.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(side_effect=Exception("API rate limit exceeded"))

            with pytest.raises(Exception, match="API rate limit exceeded"):
                await provider.complete([LLMMessage(role="user", content="Hello")])

    @pytest.mark.asyncio
    async def test_complete_with_empty_messages(
        self, provider: LiteLLMProvider, mock_response: MagicMock
    ) -> None:
        """complete() should handle empty messages list."""
        with patch("src.llm_config.providers.litellm_provider.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(return_value=mock_response)

            result = await provider.complete([])

            call_kwargs = mock_litellm.acompletion.call_args.kwargs
            assert call_kwargs["messages"] == []
            assert isinstance(result.content, str)

    @pytest.mark.asyncio
    async def test_stream_complete_with_penalty_params(self, provider: LiteLLMProvider) -> None:
        """stream_complete() should pass penalty parameters."""
        from src.llm_config.providers.litellm_provider import LiteLLMCompletionParams

        async def mock_stream() -> AsyncGenerator[MagicMock, None]:
            chunk = MagicMock()
            chunk.choices = [MagicMock()]
            chunk.choices[0].delta.content = "Hi"
            yield chunk

        with patch("src.llm_config.providers.litellm_provider.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(return_value=mock_stream())

            params = LiteLLMCompletionParams(
                top_p=0.9,
                frequency_penalty=0.5,
                presence_penalty=0.3,
            )

            chunks = []
            async for chunk in provider.stream_complete(
                [LLMMessage(role="user", content="Hi")],
                params=params,
            ):
                chunks.append(chunk)

            call_kwargs = mock_litellm.acompletion.call_args.kwargs
            assert call_kwargs.get("top_p") == 0.9
            assert call_kwargs.get("frequency_penalty") == 0.5
            assert call_kwargs.get("presence_penalty") == 0.3

    def test_provider_name_is_set(self) -> None:
        """LiteLLMProvider should store provider_name."""
        from src.llm_config.providers.litellm_provider import (
            LiteLLMProvider,
            LiteLLMProviderSettings,
        )

        provider = LiteLLMProvider(
            api_key="test-key",
            default_model="gpt-5.1",
            settings=LiteLLMProviderSettings(),
            provider_name="openai",
        )

        assert provider._provider_name == "openai"

    def test_provider_name_defaults_to_litellm(self) -> None:
        """LiteLLMProvider should default provider_name to 'litellm'."""
        from src.llm_config.providers.litellm_provider import (
            LiteLLMProvider,
            LiteLLMProviderSettings,
        )

        provider = LiteLLMProvider(
            api_key="test-key",
            default_model="gpt-5.1",
            settings=LiteLLMProviderSettings(),
        )

        assert provider._provider_name == "litellm"

    @pytest.mark.asyncio
    async def test_complete_returns_provider_name_in_response(
        self, provider: LiteLLMProvider, mock_response: MagicMock
    ) -> None:
        """complete() should return the actual provider name in response."""
        from src.llm_config.providers.litellm_provider import (
            LiteLLMProvider,
            LiteLLMProviderSettings,
        )

        openai_provider = LiteLLMProvider(
            api_key="test-key",
            default_model="gpt-5.1",
            settings=LiteLLMProviderSettings(),
            provider_name="openai",
        )

        with patch("src.llm_config.providers.litellm_provider.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(return_value=mock_response)

            result = await openai_provider.complete([LLMMessage(role="user", content="Hello")])

            assert result.provider == "openai"

    @pytest.mark.asyncio
    async def test_complete_raises_on_empty_model(self) -> None:
        """complete() should raise ValueError when model is empty after fallback."""
        provider = LiteLLMProvider(
            api_key="test-key",
            default_model="",
            settings=LiteLLMProviderSettings(),
        )

        with pytest.raises(ValueError, match="Model name cannot be empty"):
            await provider.complete(
                [LLMMessage(role="user", content="Hello")],
                LiteLLMCompletionParams(model=""),
            )

    @pytest.mark.asyncio
    async def test_complete_uses_default_model_for_empty_param_model(
        self, mock_response: MagicMock
    ) -> None:
        """complete() should fall back to default_model when params.model is empty."""
        provider = LiteLLMProvider(
            api_key="test-key",
            default_model="gpt-5-mini",
            settings=LiteLLMProviderSettings(),
        )

        with patch("src.llm_config.providers.litellm_provider.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(return_value=mock_response)

            await provider.complete(
                [LLMMessage(role="user", content="Hello")],
                LiteLLMCompletionParams(model=""),
            )

            call_kwargs = mock_litellm.acompletion.call_args.kwargs
            assert call_kwargs["model"] == "gpt-5-mini"

    @pytest.mark.asyncio
    async def test_stream_complete_raises_on_empty_model(self) -> None:
        """stream_complete() should raise ValueError when model is empty after fallback."""
        provider = LiteLLMProvider(
            api_key="test-key",
            default_model="",
            settings=LiteLLMProviderSettings(),
        )

        with pytest.raises(ValueError, match="Model name cannot be empty"):
            async for _ in provider.stream_complete(
                [LLMMessage(role="user", content="Hello")],
                LiteLLMCompletionParams(model=""),
            ):
                pass

    @pytest.mark.asyncio
    async def test_stream_complete_uses_default_model_for_empty_param_model(self) -> None:
        """stream_complete() should fall back to default_model when params.model is empty."""
        provider = LiteLLMProvider(
            api_key="test-key",
            default_model="gpt-5-mini",
            settings=LiteLLMProviderSettings(),
        )

        async def mock_stream():
            chunk = MagicMock()
            chunk.choices = [MagicMock(delta=MagicMock(content="Hi"))]
            yield chunk

        with patch("src.llm_config.providers.litellm_provider.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(return_value=mock_stream())

            chunks = []
            async for chunk in provider.stream_complete(
                [LLMMessage(role="user", content="Hello")],
                LiteLLMCompletionParams(model=""),
            ):
                chunks.append(chunk)

            call_kwargs = mock_litellm.acompletion.call_args.kwargs
            assert call_kwargs["model"] == "gpt-5-mini"


class TestLiteLLMProviderVertexAI:
    """Tests for Vertex AI-specific behavior in LiteLLMProvider."""

    @pytest.fixture
    def vertex_provider(self) -> LiteLLMProvider:
        return LiteLLMProvider(
            api_key="ADC",
            default_model="gemini-2.5-flash",
            settings=LiteLLMProviderSettings(),
            provider_name="vertex_ai",
        )

    @pytest.fixture
    def openai_provider(self) -> LiteLLMProvider:
        return LiteLLMProvider(
            api_key="sk-test-key",
            default_model="gpt-5.1",
            settings=LiteLLMProviderSettings(),
            provider_name="openai",
        )

    @pytest.fixture
    def mock_response(self) -> MagicMock:
        response = MagicMock()
        response.choices = [
            MagicMock(
                message=MagicMock(content="Test response"),
                finish_reason="stop",
            )
        ]
        response.model = "gemini-2.5-flash"
        response.usage = MagicMock(total_tokens=15)
        return response

    @pytest.mark.asyncio
    async def test_vertex_ai_omits_api_key(
        self, vertex_provider: LiteLLMProvider, mock_response: MagicMock
    ) -> None:
        """When provider_name='vertex_ai', api_key should NOT be passed to litellm."""
        with patch("src.llm_config.providers.litellm_provider.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(return_value=mock_response)

            await vertex_provider.complete([LLMMessage(role="user", content="Hi")])

            call_kwargs = mock_litellm.acompletion.call_args.kwargs
            assert "api_key" not in call_kwargs

    @pytest.mark.asyncio
    async def test_openai_includes_api_key(
        self, openai_provider: LiteLLMProvider, mock_response: MagicMock
    ) -> None:
        """When provider_name='openai', api_key SHOULD be passed to litellm."""
        mock_response.model = "gpt-5.1"
        with patch("src.llm_config.providers.litellm_provider.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(return_value=mock_response)

            await openai_provider.complete([LLMMessage(role="user", content="Hi")])

            call_kwargs = mock_litellm.acompletion.call_args.kwargs
            assert call_kwargs["api_key"] == "sk-test-key"

    @pytest.mark.asyncio
    async def test_vertex_ai_stream_omits_api_key(self, vertex_provider: LiteLLMProvider) -> None:
        """stream_complete() with vertex_ai should NOT pass api_key."""

        async def mock_stream():
            chunk = MagicMock()
            chunk.choices = [MagicMock(delta=MagicMock(content="Hi"))]
            yield chunk

        with patch("src.llm_config.providers.litellm_provider.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(return_value=mock_stream())

            async for _ in vertex_provider.stream_complete([LLMMessage(role="user", content="Hi")]):
                pass

            call_kwargs = mock_litellm.acompletion.call_args.kwargs
            assert "api_key" not in call_kwargs

    @pytest.mark.asyncio
    async def test_validate_api_key_returns_true_for_vertex_ai(
        self, vertex_provider: LiteLLMProvider
    ) -> None:
        """validate_api_key() should return True immediately for vertex_ai (ADC)."""
        result = await vertex_provider.validate_api_key()
        assert result is True

    @pytest.mark.asyncio
    async def test_validate_api_key_returns_true_for_gemini(self) -> None:
        """validate_api_key() should return True immediately for gemini provider."""
        gemini_provider = LiteLLMProvider(
            api_key="ADC",
            default_model="gemini-2.5-pro",
            settings=LiteLLMProviderSettings(),
            provider_name="gemini",
        )
        result = await gemini_provider.validate_api_key()
        assert result is True

    @pytest.mark.asyncio
    async def test_vertex_ai_complete_returns_correct_provider(
        self, vertex_provider: LiteLLMProvider, mock_response: MagicMock
    ) -> None:
        """complete() with vertex_ai should return 'vertex_ai' as provider."""
        with patch("src.llm_config.providers.litellm_provider.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(return_value=mock_response)

            result = await vertex_provider.complete([LLMMessage(role="user", content="Hello")])

            assert result.provider == "vertex_ai"

    @pytest.mark.asyncio
    async def test_gemini_provider_omits_api_key(self) -> None:
        """When provider_name='gemini', api_key should NOT be passed to litellm."""
        gemini_provider = LiteLLMProvider(
            api_key="ADC",
            default_model="gemini-2.5-pro",
            settings=LiteLLMProviderSettings(),
            provider_name="gemini",
        )
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock(message=MagicMock(content="Hi"), finish_reason="stop")]
        mock_resp.model = "gemini-2.5-pro"
        mock_resp.usage = MagicMock(total_tokens=5)

        with patch("src.llm_config.providers.litellm_provider.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(return_value=mock_resp)

            await gemini_provider.complete([LLMMessage(role="user", content="Hi")])

            call_kwargs = mock_litellm.acompletion.call_args.kwargs
            assert "api_key" not in call_kwargs
