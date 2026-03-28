"""Unit tests for DirectProvider using pydantic_ai.direct."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.llm_config.constants import ADC_SENTINEL
from src.llm_config.model_id import ModelId
from src.llm_config.providers.base import LLMMessage
from src.llm_config.providers.direct_provider import (
    DirectCompletionParams,
    DirectProvider,
    DirectProviderSettings,
)


def _make_mock_response(
    text: str = "Hello! How can I help you?",
    model_name: str = "gpt-5.1",
    total_tokens: int = 25,
    finish_reason: str | None = "stop",
) -> MagicMock:
    usage = MagicMock()
    usage.total_tokens = total_tokens
    resp = MagicMock()
    resp.text = text
    resp.model_name = model_name
    resp.usage = usage
    resp.finish_reason = finish_reason
    return resp


class TestDirectProviderSettings:
    def test_default_values(self) -> None:
        settings = DirectProviderSettings()
        assert settings.timeout == 30.0
        assert settings.max_tokens == 4096
        assert settings.temperature == 0.7

    def test_custom_values(self) -> None:
        settings = DirectProviderSettings(
            timeout=60.0,
            max_tokens=8192,
            temperature=0.5,
        )
        assert settings.timeout == 60.0
        assert settings.max_tokens == 8192
        assert settings.temperature == 0.5

    def test_invalid_timeout_rejected(self) -> None:
        with pytest.raises(ValueError, match="greater than 0"):
            DirectProviderSettings(timeout=-1)

    def test_invalid_temperature_rejected(self) -> None:
        with pytest.raises(ValueError, match="less than or equal to 2"):
            DirectProviderSettings(temperature=3.0)


class TestDirectCompletionParams:
    def test_all_params_optional(self) -> None:
        params = DirectCompletionParams()
        assert params.model is None
        assert params.max_tokens is None
        assert params.temperature is None
        assert params.top_p is None
        assert params.frequency_penalty is None
        assert params.presence_penalty is None

    def test_set_specific_params(self) -> None:
        params = DirectCompletionParams(
            temperature=0.5,
            presence_penalty=0.3,
        )
        assert params.temperature == 0.5
        assert params.presence_penalty == 0.3
        assert params.frequency_penalty is None

    def test_model_accepts_model_id(self) -> None:
        model_id = ModelId.from_pydantic_ai("openai:gpt-5.1")
        params = DirectCompletionParams(model=model_id)
        assert params.model == model_id
        assert params.model.provider == "openai"
        assert params.model.model == "gpt-5.1"

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValueError, match="extra_forbidden"):
            DirectCompletionParams(unknown_field="value")  # type: ignore[call-arg]


class TestDirectProvider:
    @pytest.fixture
    def provider(self) -> DirectProvider:
        return DirectProvider(
            api_key="test-api-key",
            default_model="openai:gpt-5.1",
            settings=DirectProviderSettings(),
            provider_name="openai",
        )

    @pytest.mark.asyncio
    async def test_complete_calls_model_request(self, provider: DirectProvider) -> None:
        mock_resp = _make_mock_response()
        with patch(
            "src.llm_config.providers.direct_provider.model_request",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ) as mock_mr:
            messages = [LLMMessage(role="user", content="Hi")]
            await provider.complete(messages)

            mock_mr.assert_called_once()
            call_kwargs = mock_mr.call_args
            assert call_kwargs.kwargs["model"] == "openai:gpt-5.1"

    @pytest.mark.asyncio
    async def test_complete_returns_llm_response(self, provider: DirectProvider) -> None:
        mock_resp = _make_mock_response()
        with patch(
            "src.llm_config.providers.direct_provider.model_request",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            messages = [LLMMessage(role="user", content="Hi")]
            response = await provider.complete(messages)

            assert response.content == "Hello! How can I help you?"
            assert response.model == "gpt-5.1"
            assert response.tokens_used == 25
            assert response.finish_reason == "stop"
            assert response.provider == "openai"

    @pytest.mark.asyncio
    async def test_complete_uses_default_model(self, provider: DirectProvider) -> None:
        mock_resp = _make_mock_response()
        with patch(
            "src.llm_config.providers.direct_provider.model_request",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ) as mock_mr:
            messages = [LLMMessage(role="user", content="Hi")]
            await provider.complete(messages)

            call_kwargs = mock_mr.call_args.kwargs
            assert call_kwargs["model"] == "openai:gpt-5.1"

    @pytest.mark.asyncio
    async def test_complete_uses_param_model_when_specified(self, provider: DirectProvider) -> None:
        mock_resp = _make_mock_response()
        with patch(
            "src.llm_config.providers.direct_provider.model_request",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ) as mock_mr:
            messages = [LLMMessage(role="user", content="Hi")]
            params = DirectCompletionParams(
                model=ModelId.from_pydantic_ai("anthropic:claude-3-opus")
            )
            await provider.complete(messages, params)

            call_kwargs = mock_mr.call_args.kwargs
            assert call_kwargs["model"] == "anthropic:claude-3-opus"

    @pytest.mark.asyncio
    async def test_complete_handles_missing_usage(self, provider: DirectProvider) -> None:
        mock_resp = _make_mock_response()
        mock_resp.usage = None
        with patch(
            "src.llm_config.providers.direct_provider.model_request",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            messages = [LLMMessage(role="user", content="Hi")]
            response = await provider.complete(messages)
            assert response.tokens_used == 0

    @pytest.mark.asyncio
    async def test_complete_handles_empty_content(self, provider: DirectProvider) -> None:
        mock_resp = _make_mock_response(text="")
        with patch(
            "src.llm_config.providers.direct_provider.model_request",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            messages = [LLMMessage(role="user", content="Hi")]
            response = await provider.complete(messages)
            assert response.content == ""

    @pytest.mark.asyncio
    async def test_complete_handles_none_text(self, provider: DirectProvider) -> None:
        mock_resp = _make_mock_response()
        mock_resp.text = None
        with patch(
            "src.llm_config.providers.direct_provider.model_request",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            messages = [LLMMessage(role="user", content="Hi")]
            response = await provider.complete(messages)
            assert response.content == ""

    @pytest.mark.asyncio
    async def test_complete_passes_model_settings(self, provider: DirectProvider) -> None:
        mock_resp = _make_mock_response()
        with patch(
            "src.llm_config.providers.direct_provider.model_request",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ) as mock_mr:
            messages = [LLMMessage(role="user", content="Hi")]
            params = DirectCompletionParams(
                temperature=0.5,
                top_p=0.9,
                frequency_penalty=0.3,
                presence_penalty=0.2,
                max_tokens=2048,
            )
            await provider.complete(messages, params)

            call_kwargs = mock_mr.call_args.kwargs
            ms = call_kwargs["model_settings"]
            assert ms["temperature"] == 0.5
            assert ms["top_p"] == 0.9
            assert ms["frequency_penalty"] == 0.3
            assert ms["presence_penalty"] == 0.2
            assert ms["max_tokens"] == 2048

    @pytest.mark.asyncio
    async def test_complete_uses_settings_defaults(self, provider: DirectProvider) -> None:
        mock_resp = _make_mock_response()
        with patch(
            "src.llm_config.providers.direct_provider.model_request",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ) as mock_mr:
            messages = [LLMMessage(role="user", content="Hi")]
            await provider.complete(messages)

            call_kwargs = mock_mr.call_args.kwargs
            ms = call_kwargs["model_settings"]
            assert ms["max_tokens"] == 4096
            assert ms["temperature"] == 0.7
            assert ms["timeout"] == 30.0

    @pytest.mark.asyncio
    async def test_stream_complete_yields_text_chunks(self, provider: DirectProvider) -> None:
        from pydantic_ai.messages import PartDeltaEvent, TextPartDelta

        events = [
            PartDeltaEvent(
                index=0,
                delta=TextPartDelta(content_delta="Hello"),
            ),
            PartDeltaEvent(
                index=0,
                delta=TextPartDelta(content_delta=" world"),
            ),
            PartDeltaEvent(
                index=0,
                delta=TextPartDelta(content_delta="!"),
            ),
        ]

        mock_stream = MagicMock()

        async def async_iter():
            for event in events:
                yield event

        mock_stream.__aiter__ = lambda self: async_iter()
        mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
        mock_stream.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "src.llm_config.providers.direct_provider.model_request_stream",
            return_value=mock_stream,
        ):
            messages = [LLMMessage(role="user", content="Hi")]
            chunks = []
            async for chunk in provider.stream_complete(messages):
                chunks.append(chunk)

            assert chunks == ["Hello", " world", "!"]

    @pytest.mark.asyncio
    async def test_stream_complete_skips_non_text_events(self, provider: DirectProvider) -> None:
        from pydantic_ai.messages import PartDeltaEvent, PartStartEvent, TextPart, TextPartDelta

        events = [
            PartStartEvent(index=0, part=TextPart(content=""), previous_part_kind=None),
            PartDeltaEvent(index=0, delta=TextPartDelta(content_delta="Hello")),
            PartDeltaEvent(index=0, delta=TextPartDelta(content_delta=" world")),
        ]

        mock_stream = MagicMock()

        async def async_iter():
            for event in events:
                yield event

        mock_stream.__aiter__ = lambda self: async_iter()
        mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
        mock_stream.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "src.llm_config.providers.direct_provider.model_request_stream",
            return_value=mock_stream,
        ):
            messages = [LLMMessage(role="user", content="Hi")]
            chunks = []
            async for chunk in provider.stream_complete(messages):
                chunks.append(chunk)

            assert chunks == ["Hello", " world"]

    @pytest.mark.asyncio
    async def test_validate_api_key_returns_true_on_success(self, provider: DirectProvider) -> None:
        mock_resp = _make_mock_response()
        with patch(
            "src.llm_config.providers.direct_provider.model_request",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            result = await provider.validate_api_key()
            assert result is True

    @pytest.mark.asyncio
    async def test_validate_api_key_returns_false_on_failure(
        self, provider: DirectProvider
    ) -> None:
        with patch(
            "src.llm_config.providers.direct_provider.model_request",
            new_callable=AsyncMock,
            side_effect=Exception("Invalid API key"),
        ):
            result = await provider.validate_api_key()
            assert result is False

    @pytest.mark.asyncio
    async def test_close_clears_api_key(self, provider: DirectProvider) -> None:
        assert provider.api_key == "test-api-key"
        await provider.close()
        assert provider.api_key == ""

    @pytest.mark.asyncio
    async def test_complete_propagates_api_error(self, provider: DirectProvider) -> None:
        with (
            patch(
                "src.llm_config.providers.direct_provider.model_request",
                new_callable=AsyncMock,
                side_effect=Exception("API rate limit exceeded"),
            ),
            pytest.raises(Exception, match="API rate limit exceeded"),
        ):
            await provider.complete([LLMMessage(role="user", content="Hello")])

    @pytest.mark.asyncio
    async def test_complete_raises_on_empty_model(self) -> None:
        provider = DirectProvider(
            api_key="test-key",
            default_model="",
            settings=DirectProviderSettings(),
        )

        with pytest.raises(ValueError, match="Model name cannot be empty"):
            await provider.complete(
                [LLMMessage(role="user", content="Hello")],
                DirectCompletionParams(),
            )

    @pytest.mark.asyncio
    async def test_stream_complete_raises_on_empty_model(self) -> None:
        provider = DirectProvider(
            api_key="test-key",
            default_model="",
            settings=DirectProviderSettings(),
        )

        with pytest.raises(ValueError, match="Model name cannot be empty"):
            async for _ in provider.stream_complete(
                [LLMMessage(role="user", content="Hello")],
                DirectCompletionParams(),
            ):
                pass

    @pytest.mark.asyncio
    async def test_complete_uses_default_model_for_none_param_model(self) -> None:
        provider = DirectProvider(
            api_key="test-key",
            default_model="openai:gpt-5-mini",
            settings=DirectProviderSettings(),
            provider_name="openai",
        )
        mock_resp = _make_mock_response()

        with patch(
            "src.llm_config.providers.direct_provider.model_request",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ) as mock_mr:
            await provider.complete(
                [LLMMessage(role="user", content="Hello")],
                DirectCompletionParams(),
            )

            call_kwargs = mock_mr.call_args.kwargs
            assert call_kwargs["model"] == "openai:gpt-5-mini"

    def test_provider_name_is_set(self) -> None:
        provider = DirectProvider(
            api_key="test-key",
            default_model="openai:gpt-5.1",
            settings=DirectProviderSettings(),
            provider_name="openai",
        )
        assert provider._provider_name == "openai"

    def test_provider_name_defaults_to_openai(self) -> None:
        provider = DirectProvider(
            api_key="test-key",
            default_model="openai:gpt-5.1",
            settings=DirectProviderSettings(),
        )
        assert provider._provider_name == "openai"

    @pytest.mark.asyncio
    async def test_complete_returns_provider_name_in_response(self) -> None:
        anthropic_provider = DirectProvider(
            api_key="test-key",
            default_model="anthropic:claude-3-opus",
            settings=DirectProviderSettings(),
            provider_name="anthropic",
        )
        mock_resp = _make_mock_response()

        with patch(
            "src.llm_config.providers.direct_provider.model_request",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            result = await anthropic_provider.complete([LLMMessage(role="user", content="Hello")])
            assert result.provider == "anthropic"

    @pytest.mark.asyncio
    async def test_convert_messages_user(self, provider: DirectProvider) -> None:
        messages = [LLMMessage(role="user", content="Hello")]
        result = provider._convert_messages(messages)
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_convert_messages_system_as_instructions(self, provider: DirectProvider) -> None:
        mock_resp = _make_mock_response()

        with patch(
            "src.llm_config.providers.direct_provider.model_request",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ) as mock_mr:
            messages = [
                LLMMessage(role="system", content="You are helpful"),
                LLMMessage(role="user", content="Hello"),
            ]
            await provider.complete(messages)

            call_kwargs = mock_mr.call_args.kwargs
            pydantic_messages = call_kwargs["messages"]
            first_msg = pydantic_messages[0]
            assert first_msg.instructions == "You are helpful"

    @pytest.mark.asyncio
    async def test_convert_messages_assistant(self, provider: DirectProvider) -> None:
        from pydantic_ai.messages import ModelResponse as PydanticModelResponse

        messages = [
            LLMMessage(role="user", content="Hi"),
            LLMMessage(role="assistant", content="Hello there"),
        ]
        result = provider._convert_messages(messages)
        assert len(result) == 2
        assert isinstance(result[1], PydanticModelResponse)

    @pytest.mark.asyncio
    async def test_complete_handles_none_finish_reason(self, provider: DirectProvider) -> None:
        mock_resp = _make_mock_response(finish_reason=None)
        with patch(
            "src.llm_config.providers.direct_provider.model_request",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            messages = [LLMMessage(role="user", content="Hi")]
            response = await provider.complete(messages)
            assert response.finish_reason == "stop"

    @pytest.mark.asyncio
    async def test_complete_handles_none_model_name(self, provider: DirectProvider) -> None:
        mock_resp = _make_mock_response()
        mock_resp.model_name = None
        with patch(
            "src.llm_config.providers.direct_provider.model_request",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            messages = [LLMMessage(role="user", content="Hi")]
            response = await provider.complete(messages)
            assert response.model == "openai:gpt-5.1"


class TestDirectProviderVertexAI:
    @pytest.fixture
    def vertex_provider(self) -> DirectProvider:
        return DirectProvider(
            api_key=ADC_SENTINEL,
            default_model="google-vertex:gemini-2.5-flash",
            settings=DirectProviderSettings(),
            provider_name="vertex_ai",
        )

    @pytest.fixture
    def openai_provider(self) -> DirectProvider:
        return DirectProvider(
            api_key="sk-test-key",
            default_model="openai:gpt-5.1",
            settings=DirectProviderSettings(),
            provider_name="openai",
        )

    @pytest.mark.asyncio
    async def test_validate_api_key_returns_true_for_vertex_ai(
        self, vertex_provider: DirectProvider
    ) -> None:
        result = await vertex_provider.validate_api_key()
        assert result is True

    @pytest.mark.asyncio
    async def test_validate_api_key_returns_true_for_gemini(self) -> None:
        gemini_provider = DirectProvider(
            api_key=ADC_SENTINEL,
            default_model="google-gla:gemini-2.5-pro",
            settings=DirectProviderSettings(),
            provider_name="gemini",
        )
        result = await gemini_provider.validate_api_key()
        assert result is True

    @pytest.mark.asyncio
    async def test_vertex_ai_complete_returns_correct_provider(
        self, vertex_provider: DirectProvider
    ) -> None:
        mock_resp = _make_mock_response(model_name="gemini-2.5-flash")
        with patch(
            "src.llm_config.providers.direct_provider.model_request",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            result = await vertex_provider.complete([LLMMessage(role="user", content="Hello")])
            assert result.provider == "vertex_ai"

    @pytest.mark.asyncio
    async def test_vertex_ai_uses_pydantic_ai_native_adc(
        self, vertex_provider: DirectProvider
    ) -> None:
        mock_resp = _make_mock_response(model_name="gemini-2.5-flash")
        with patch(
            "src.llm_config.providers.direct_provider.model_request",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ) as mock_mr:
            await vertex_provider.complete([LLMMessage(role="user", content="Hi")])

            call_kwargs = mock_mr.call_args.kwargs
            assert "vertex_location" not in call_kwargs
            assert "vertex_project" not in call_kwargs
            assert "api_key" not in call_kwargs

    @pytest.mark.asyncio
    async def test_openai_complete_uses_model_string(self, openai_provider: DirectProvider) -> None:
        mock_resp = _make_mock_response(model_name="gpt-5.1")
        with patch(
            "src.llm_config.providers.direct_provider.model_request",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ) as mock_mr:
            await openai_provider.complete([LLMMessage(role="user", content="Hi")])

            call_kwargs = mock_mr.call_args.kwargs
            assert call_kwargs["model"] == "openai:gpt-5.1"


class TestConvertMessagesMultimodal:
    @pytest.fixture
    def provider(self) -> DirectProvider:
        return DirectProvider(
            api_key="test-api-key",
            default_model="openai:gpt-5.1",
            settings=DirectProviderSettings(),
            provider_name="openai",
        )

    def test_multimodal_content_produces_image_url_part(self, provider: DirectProvider) -> None:
        from pydantic_ai.messages import ImageUrl, ModelRequest, UserPromptPart

        messages = [
            LLMMessage(
                role="user",
                content=[
                    {"type": "text", "text": "Describe this image"},
                    {
                        "type": "image_url",
                        "image_url": {"url": "https://example.com/img.png", "detail": "auto"},
                    },
                ],
            )
        ]
        result = provider._convert_messages(messages)

        assert len(result) == 1
        req = result[0]
        assert isinstance(req, ModelRequest)
        assert len(req.parts) == 1

        user_part = req.parts[0]
        assert isinstance(user_part, UserPromptPart)
        assert isinstance(user_part.content, list)
        assert len(user_part.content) == 2

        assert user_part.content[0] == "Describe this image"
        assert isinstance(user_part.content[1], ImageUrl)
        assert user_part.content[1].url == "https://example.com/img.png"

    def test_multimodal_text_only_content(self, provider: DirectProvider) -> None:
        from pydantic_ai.messages import ModelRequest, UserPromptPart

        messages = [
            LLMMessage(
                role="user",
                content=[
                    {"type": "text", "text": "Part one"},
                    {"type": "text", "text": "Part two"},
                ],
            )
        ]
        result = provider._convert_messages(messages)

        assert len(result) == 1
        req = result[0]
        assert isinstance(req, ModelRequest)

        user_part = req.parts[0]
        assert isinstance(user_part, UserPromptPart)
        assert isinstance(user_part.content, list)
        assert user_part.content[0] == "Part one"
        assert user_part.content[1] == "Part two"

    def test_multimodal_multiple_images(self, provider: DirectProvider) -> None:
        from pydantic_ai.messages import ImageUrl, UserPromptPart

        messages = [
            LLMMessage(
                role="user",
                content=[
                    {"type": "text", "text": "Compare these images"},
                    {"type": "image_url", "image_url": {"url": "https://example.com/a.png"}},
                    {"type": "image_url", "image_url": {"url": "https://example.com/b.png"}},
                ],
            )
        ]
        result = provider._convert_messages(messages)
        user_part = result[0].parts[0]
        assert isinstance(user_part, UserPromptPart)
        assert len(user_part.content) == 3
        assert isinstance(user_part.content[1], ImageUrl)
        assert isinstance(user_part.content[2], ImageUrl)
        assert user_part.content[1].url == "https://example.com/a.png"
        assert user_part.content[2].url == "https://example.com/b.png"

    @pytest.mark.asyncio
    async def test_complete_with_multimodal_passes_correct_messages(
        self, provider: DirectProvider
    ) -> None:
        from pydantic_ai.messages import ImageUrl, UserPromptPart

        mock_resp = _make_mock_response()
        with patch(
            "src.llm_config.providers.direct_provider.model_request",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ) as mock_mr:
            messages = [
                LLMMessage(
                    role="user",
                    content=[
                        {"type": "text", "text": "Describe this image"},
                        {
                            "type": "image_url",
                            "image_url": {"url": "https://example.com/img.png", "detail": "auto"},
                        },
                    ],
                )
            ]
            await provider.complete(messages)

            call_kwargs = mock_mr.call_args.kwargs
            pydantic_messages = call_kwargs["messages"]
            user_part = pydantic_messages[0].parts[0]
            assert isinstance(user_part, UserPromptPart)
            assert isinstance(user_part.content, list)
            assert isinstance(user_part.content[1], ImageUrl)

    def test_unknown_multimodal_part_type_is_skipped(self, provider: DirectProvider) -> None:
        from pydantic_ai.messages import UserPromptPart

        messages = [
            LLMMessage(
                role="user",
                content=[
                    {"type": "text", "text": "Hello"},
                    {"type": "audio", "audio": {"url": "https://example.com/audio.mp3"}},
                ],
            )
        ]
        result = provider._convert_messages(messages)
        user_part = result[0].parts[0]
        assert isinstance(user_part, UserPromptPart)
        assert isinstance(user_part.content, list)
        assert len(user_part.content) == 1
        assert user_part.content[0] == "Hello"


class TestDirectProviderNoLitellmImports:
    def test_no_litellm_imports_in_direct_provider(self) -> None:
        import ast
        from pathlib import Path

        provider_file = (
            Path(__file__).parents[3] / "src" / "llm_config" / "providers" / "direct_provider.py"
        )
        source = provider_file.read_text()
        tree = ast.parse(source)

        litellm_imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if "litellm" in alias.name:
                        litellm_imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module and "litellm" in node.module:
                litellm_imports.append(node.module)

        assert litellm_imports == [], f"Found litellm imports: {litellm_imports}"
