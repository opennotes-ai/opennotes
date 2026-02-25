"""Tests for LLMService provider inference from model strings."""

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.llm_config.manager import LLMClientManager
from src.llm_config.model_id import ModelId
from src.llm_config.providers.base import LLMMessage, LLMResponse
from src.llm_config.service import LLMService


@pytest.fixture
def mock_client_manager() -> MagicMock:
    return MagicMock(spec=LLMClientManager)


@pytest.fixture
def llm_service(mock_client_manager: MagicMock) -> LLMService:
    return LLMService(client_manager=mock_client_manager)


@pytest.fixture
def mock_db() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_llm_response() -> LLMResponse:
    return LLMResponse(
        content="Test response",
        model="gemini-2.5-flash",
        tokens_used=10,
        finish_reason="stop",
        provider="vertex_ai",
    )


class TestCompleteProviderInference:
    """Tests that complete() infers provider from ModelId."""

    @pytest.mark.asyncio
    async def test_complete_infers_vertex_ai_from_model(
        self,
        llm_service: LLMService,
        mock_client_manager: MagicMock,
        mock_db: AsyncMock,
        mock_llm_response: LLMResponse,
    ) -> None:
        """complete() with vertex_ai ModelId should use vertex_ai provider."""
        mock_provider = MagicMock()
        mock_provider.complete = AsyncMock(return_value=mock_llm_response)
        mock_client_manager.get_client = AsyncMock(return_value=mock_provider)

        messages = [LLMMessage(role="user", content="Hi")]

        await llm_service.complete(
            db=mock_db,
            messages=messages,
            model=ModelId.from_litellm("vertex_ai/gemini-2.5-flash"),
        )

        mock_client_manager.get_client.assert_called_once_with(mock_db, None, "vertex_ai")

    @pytest.mark.asyncio
    async def test_complete_infers_openai_from_model(
        self,
        llm_service: LLMService,
        mock_client_manager: MagicMock,
        mock_db: AsyncMock,
        mock_llm_response: LLMResponse,
    ) -> None:
        """complete() with openai ModelId should use openai provider."""
        mock_provider = MagicMock()
        mock_provider.complete = AsyncMock(return_value=mock_llm_response)
        mock_client_manager.get_client = AsyncMock(return_value=mock_provider)

        messages = [LLMMessage(role="user", content="Hi")]

        await llm_service.complete(
            db=mock_db,
            messages=messages,
            model=ModelId.from_litellm("openai/gpt-5.1"),
        )

        mock_client_manager.get_client.assert_called_once_with(mock_db, None, "openai")

    @pytest.mark.asyncio
    async def test_complete_preserves_model_id_in_params(
        self,
        llm_service: LLMService,
        mock_client_manager: MagicMock,
        mock_db: AsyncMock,
        mock_llm_response: LLMResponse,
    ) -> None:
        """complete() should preserve the ModelId in LiteLLMCompletionParams."""
        mock_provider = MagicMock()
        mock_provider.complete = AsyncMock(return_value=mock_llm_response)
        mock_client_manager.get_client = AsyncMock(return_value=mock_provider)

        messages = [LLMMessage(role="user", content="Hi")]
        model_id = ModelId.from_litellm("vertex_ai/gemini-2.5-flash")

        await llm_service.complete(
            db=mock_db,
            messages=messages,
            model=model_id,
        )

        call_args = mock_provider.complete.call_args
        params = call_args[0][1]
        assert params.model == model_id

    @pytest.mark.asyncio
    async def test_complete_without_model_uses_explicit_provider(
        self,
        llm_service: LLMService,
        mock_client_manager: MagicMock,
        mock_db: AsyncMock,
        mock_llm_response: LLMResponse,
    ) -> None:
        """complete() with no model uses the explicit provider parameter."""
        mock_provider = MagicMock()
        mock_provider.complete = AsyncMock(return_value=mock_llm_response)
        mock_client_manager.get_client = AsyncMock(return_value=mock_provider)

        messages = [LLMMessage(role="user", content="Hi")]

        await llm_service.complete(
            db=mock_db,
            messages=messages,
            provider="anthropic",
        )

        mock_client_manager.get_client.assert_called_once_with(mock_db, None, "anthropic")


class TestStreamCompleteProviderInference:
    """Tests that stream_complete() infers provider from ModelId."""

    @pytest.mark.asyncio
    async def test_stream_complete_infers_vertex_ai(
        self,
        llm_service: LLMService,
        mock_client_manager: MagicMock,
        mock_db: AsyncMock,
    ) -> None:
        """stream_complete() with vertex_ai ModelId should use vertex_ai."""
        mock_provider = MagicMock()

        async def mock_stream(*args, **kwargs):
            yield "chunk"

        mock_provider.stream_complete = mock_stream
        mock_client_manager.get_client = AsyncMock(return_value=mock_provider)

        messages = [LLMMessage(role="user", content="Hi")]

        chunks = []
        async for chunk in llm_service.stream_complete(
            db=mock_db,
            messages=messages,
            model=ModelId.from_litellm("vertex_ai/gemini-2.5-flash"),
        ):
            chunks.append(chunk)

        mock_client_manager.get_client.assert_called_once_with(mock_db, None, "vertex_ai")
        assert chunks == ["chunk"]


class TestDescribeImageProviderRouting:
    """Tests that describe_image() routes through provider.complete()."""

    @pytest.mark.asyncio
    async def test_describe_image_routes_through_provider_complete(
        self,
        llm_service: LLMService,
        mock_client_manager: MagicMock,
        mock_db: AsyncMock,
    ) -> None:
        """describe_image() should call provider.complete() not litellm directly."""
        response = LLMResponse(
            content="A cat sitting on a mat",
            model="gpt-5.1",
            tokens_used=30,
            finish_reason="stop",
            provider="openai",
        )
        mock_provider = MagicMock()
        mock_provider.complete = AsyncMock(return_value=response)
        mock_client_manager.get_client = AsyncMock(return_value=mock_provider)

        result = await llm_service.describe_image(
            db=mock_db,
            image_url="https://example.com/cat.jpg",
        )

        assert result == "A cat sitting on a mat"
        mock_provider.complete.assert_called_once()

        call_args = mock_provider.complete.call_args
        messages = call_args[0][0]
        assert len(messages) == 1
        assert messages[0].role == "user"
        assert isinstance(messages[0].content, list)

    @pytest.mark.asyncio
    async def test_describe_image_infers_vertex_ai_from_model(
        self,
        llm_service: LLMService,
        mock_client_manager: MagicMock,
        mock_db: AsyncMock,
    ) -> None:
        """describe_image() with vertex_ai ModelId should use vertex_ai provider."""
        response = LLMResponse(
            content="An image of mountains",
            model="gemini-2.5-flash",
            tokens_used=25,
            finish_reason="stop",
            provider="vertex_ai",
        )
        mock_provider = MagicMock()
        mock_provider.complete = AsyncMock(return_value=response)
        mock_client_manager.get_client = AsyncMock(return_value=mock_provider)

        await llm_service.describe_image(
            db=mock_db,
            image_url="https://example.com/mountain.jpg",
            model=ModelId.from_litellm("vertex_ai/gemini-2.5-flash"),
        )

        mock_client_manager.get_client.assert_called_once_with(mock_db, None, "vertex_ai")


class TestProviderConflictWarning:
    """Tests that a warning is logged when explicit provider conflicts with ModelId provider."""

    @pytest.mark.asyncio
    async def test_complete_warns_when_provider_conflicts_with_model_provider(
        self,
        llm_service: LLMService,
        mock_client_manager: MagicMock,
        mock_db: AsyncMock,
        mock_llm_response: LLMResponse,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """ModelId provider takes precedence over explicit provider; warning is logged."""
        mock_provider = MagicMock()
        mock_provider.complete = AsyncMock(return_value=mock_llm_response)
        mock_client_manager.get_client = AsyncMock(return_value=mock_provider)

        messages = [LLMMessage(role="user", content="Hi")]

        with caplog.at_level(logging.WARNING, logger="src.llm_config.service"):
            await llm_service.complete(
                db=mock_db,
                messages=messages,
                provider="anthropic",
                model=ModelId.from_litellm("openai/gpt-5.1"),
            )

        assert any(
            "Model prefix provider differs from explicit provider param" in record.message
            for record in caplog.records
        )
        mock_client_manager.get_client.assert_called_once_with(mock_db, None, "openai")

    @pytest.mark.asyncio
    async def test_stream_complete_warns_when_provider_conflicts_with_model_provider(
        self,
        llm_service: LLMService,
        mock_client_manager: MagicMock,
        mock_db: AsyncMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """stream_complete() also logs warning on provider/model provider conflict."""
        mock_provider = MagicMock()

        async def mock_stream(*args, **kwargs):
            yield "chunk"

        mock_provider.stream_complete = mock_stream
        mock_client_manager.get_client = AsyncMock(return_value=mock_provider)

        messages = [LLMMessage(role="user", content="Hi")]

        with caplog.at_level(logging.WARNING, logger="src.llm_config.service"):
            async for _ in llm_service.stream_complete(
                db=mock_db,
                messages=messages,
                provider="anthropic",
                model=ModelId.from_litellm("vertex_ai/gemini-2.5-flash"),
            ):
                pass

        assert any(
            "Model prefix provider differs from explicit provider param" in record.message
            for record in caplog.records
        )
        mock_client_manager.get_client.assert_called_once_with(mock_db, None, "vertex_ai")

    @pytest.mark.asyncio
    async def test_no_warning_when_provider_is_default_openai(
        self,
        llm_service: LLMService,
        mock_client_manager: MagicMock,
        mock_db: AsyncMock,
        mock_llm_response: LLMResponse,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """No warning when provider is the default 'openai' (caller did not pass it explicitly)."""
        mock_provider = MagicMock()
        mock_provider.complete = AsyncMock(return_value=mock_llm_response)
        mock_client_manager.get_client = AsyncMock(return_value=mock_provider)

        messages = [LLMMessage(role="user", content="Hi")]

        with caplog.at_level(logging.WARNING, logger="src.llm_config.service"):
            await llm_service.complete(
                db=mock_db,
                messages=messages,
                model=ModelId.from_litellm("vertex_ai/gemini-2.5-flash"),
            )

        assert not any(
            "Model prefix provider differs from explicit provider param" in record.message
            for record in caplog.records
        )
        mock_client_manager.get_client.assert_called_once_with(mock_db, None, "vertex_ai")

    @pytest.mark.asyncio
    async def test_complete_model_provider_overrides_explicit_provider(
        self,
        llm_service: LLMService,
        mock_client_manager: MagicMock,
        mock_db: AsyncMock,
        mock_llm_response: LLMResponse,
    ) -> None:
        """When ModelId has openai and provider='anthropic', openai wins."""
        mock_provider = MagicMock()
        mock_provider.complete = AsyncMock(return_value=mock_llm_response)
        mock_client_manager.get_client = AsyncMock(return_value=mock_provider)

        messages = [LLMMessage(role="user", content="Hi")]

        await llm_service.complete(
            db=mock_db,
            messages=messages,
            provider="anthropic",
            model=ModelId.from_litellm("openai/gpt-5.1"),
        )

        mock_client_manager.get_client.assert_called_once_with(mock_db, None, "openai")

    @pytest.mark.asyncio
    async def test_no_warning_when_provider_matches_model_provider(
        self,
        llm_service: LLMService,
        mock_client_manager: MagicMock,
        mock_db: AsyncMock,
        mock_llm_response: LLMResponse,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """No warning when explicit provider matches the ModelId provider."""
        mock_provider = MagicMock()
        mock_provider.complete = AsyncMock(return_value=mock_llm_response)
        mock_client_manager.get_client = AsyncMock(return_value=mock_provider)

        messages = [LLMMessage(role="user", content="Hi")]

        with caplog.at_level(logging.WARNING, logger="src.llm_config.service"):
            await llm_service.complete(
                db=mock_db,
                messages=messages,
                provider="vertex_ai",
                model=ModelId.from_litellm("vertex_ai/gemini-2.5-flash"),
            )

        assert not any(
            "Model prefix provider differs from explicit provider param" in record.message
            for record in caplog.records
        )
        mock_client_manager.get_client.assert_called_once_with(mock_db, None, "vertex_ai")


class TestPydanticAIFlavorProviderNormalization:
    """Tests that pydantic-ai flavored ModelId normalizes to litellm provider for client lookup."""

    @pytest.mark.asyncio
    async def test_complete_normalizes_google_vertex_to_vertex_ai(
        self,
        llm_service: LLMService,
        mock_client_manager: MagicMock,
        mock_db: AsyncMock,
        mock_llm_response: LLMResponse,
    ) -> None:
        mock_provider = MagicMock()
        mock_provider.complete = AsyncMock(return_value=mock_llm_response)
        mock_client_manager.get_client = AsyncMock(return_value=mock_provider)

        messages = [LLMMessage(role="user", content="Hi")]

        await llm_service.complete(
            db=mock_db,
            messages=messages,
            model=ModelId.from_pydantic_ai("google-vertex:gemini-2.5-flash"),
        )

        mock_client_manager.get_client.assert_called_once_with(mock_db, None, "vertex_ai")

    @pytest.mark.asyncio
    async def test_complete_normalizes_google_gla_to_gemini(
        self,
        llm_service: LLMService,
        mock_client_manager: MagicMock,
        mock_db: AsyncMock,
        mock_llm_response: LLMResponse,
    ) -> None:
        mock_provider = MagicMock()
        mock_provider.complete = AsyncMock(return_value=mock_llm_response)
        mock_client_manager.get_client = AsyncMock(return_value=mock_provider)

        messages = [LLMMessage(role="user", content="Hi")]

        await llm_service.complete(
            db=mock_db,
            messages=messages,
            model=ModelId.from_pydantic_ai("google-gla:gemini-2.5-flash"),
        )

        mock_client_manager.get_client.assert_called_once_with(mock_db, None, "gemini")

    @pytest.mark.asyncio
    async def test_stream_complete_normalizes_pydantic_ai_provider(
        self,
        llm_service: LLMService,
        mock_client_manager: MagicMock,
        mock_db: AsyncMock,
    ) -> None:
        mock_provider = MagicMock()

        async def mock_stream(*args, **kwargs):
            yield "chunk"

        mock_provider.stream_complete = mock_stream
        mock_client_manager.get_client = AsyncMock(return_value=mock_provider)

        messages = [LLMMessage(role="user", content="Hi")]

        chunks = []
        async for chunk in llm_service.stream_complete(
            db=mock_db,
            messages=messages,
            model=ModelId.from_pydantic_ai("google-vertex:gemini-2.5-flash"),
        ):
            chunks.append(chunk)

        mock_client_manager.get_client.assert_called_once_with(mock_db, None, "vertex_ai")
        assert chunks == ["chunk"]

    @pytest.mark.asyncio
    async def test_describe_image_normalizes_pydantic_ai_provider(
        self,
        llm_service: LLMService,
        mock_client_manager: MagicMock,
        mock_db: AsyncMock,
    ) -> None:
        response = LLMResponse(
            content="A mountain landscape",
            model="gemini-2.5-flash",
            tokens_used=25,
            finish_reason="stop",
            provider="vertex_ai",
        )
        mock_provider = MagicMock()
        mock_provider.complete = AsyncMock(return_value=response)
        mock_client_manager.get_client = AsyncMock(return_value=mock_provider)

        await llm_service.describe_image(
            db=mock_db,
            image_url="https://example.com/mountain.jpg",
            model=ModelId.from_pydantic_ai("google-vertex:gemini-2.5-flash"),
        )

        mock_client_manager.get_client.assert_called_once_with(mock_db, None, "vertex_ai")

    @pytest.mark.asyncio
    async def test_no_warning_when_explicit_provider_matches_pydantic_ai_raw(
        self,
        llm_service: LLMService,
        mock_client_manager: MagicMock,
        mock_db: AsyncMock,
        mock_llm_response: LLMResponse,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        mock_provider = MagicMock()
        mock_provider.complete = AsyncMock(return_value=mock_llm_response)
        mock_client_manager.get_client = AsyncMock(return_value=mock_provider)

        messages = [LLMMessage(role="user", content="Hi")]

        with caplog.at_level(logging.WARNING, logger="src.llm_config.service"):
            await llm_service.complete(
                db=mock_db,
                messages=messages,
                provider="google-vertex",
                model=ModelId.from_pydantic_ai("google-vertex:gemini-2.5-flash"),
            )

        assert not any(
            "Model prefix provider differs from explicit provider param" in record.message
            for record in caplog.records
        )

    @pytest.mark.asyncio
    async def test_no_warning_when_explicit_provider_matches_litellm_normalized(
        self,
        llm_service: LLMService,
        mock_client_manager: MagicMock,
        mock_db: AsyncMock,
        mock_llm_response: LLMResponse,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        mock_provider = MagicMock()
        mock_provider.complete = AsyncMock(return_value=mock_llm_response)
        mock_client_manager.get_client = AsyncMock(return_value=mock_provider)

        messages = [LLMMessage(role="user", content="Hi")]

        with caplog.at_level(logging.WARNING, logger="src.llm_config.service"):
            await llm_service.complete(
                db=mock_db,
                messages=messages,
                provider="vertex_ai",
                model=ModelId.from_pydantic_ai("google-vertex:gemini-2.5-flash"),
            )

        assert not any(
            "Model prefix provider differs from explicit provider param" in record.message
            for record in caplog.records
        )

    @pytest.mark.asyncio
    async def test_pydantic_ai_openai_passes_through_unchanged(
        self,
        llm_service: LLMService,
        mock_client_manager: MagicMock,
        mock_db: AsyncMock,
        mock_llm_response: LLMResponse,
    ) -> None:
        mock_provider = MagicMock()
        mock_provider.complete = AsyncMock(return_value=mock_llm_response)
        mock_client_manager.get_client = AsyncMock(return_value=mock_provider)

        messages = [LLMMessage(role="user", content="Hi")]

        await llm_service.complete(
            db=mock_db,
            messages=messages,
            model=ModelId.from_pydantic_ai("openai:gpt-5.1"),
        )

        mock_client_manager.get_client.assert_called_once_with(mock_db, None, "openai")


class TestDescribeImageSettingsProviderRouting:
    """Tests that describe_image uses provider from settings.VISION_MODEL (task-1137.07)."""

    @pytest.fixture
    def mock_client_manager(self) -> MagicMock:
        return MagicMock(spec=LLMClientManager)

    @pytest.fixture
    def llm_service(self, mock_client_manager: MagicMock) -> LLMService:
        return LLMService(client_manager=mock_client_manager)

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_describe_image_uses_provider_from_vision_model_setting(
        self,
        llm_service: LLMService,
        mock_client_manager: MagicMock,
        mock_db: AsyncMock,
    ) -> None:
        """describe_image routes through provider parsed from VISION_MODEL setting."""
        response = LLMResponse(
            content="A mountain landscape",
            model="gemini-2.5-flash",
            tokens_used=25,
            finish_reason="stop",
            provider="vertex_ai",
        )
        mock_provider = MagicMock()
        mock_provider.complete = AsyncMock(return_value=response)
        mock_client_manager.get_client = AsyncMock(return_value=mock_provider)

        with patch("src.llm_config.service.settings") as mock_settings:
            mock_settings.VISION_MODEL = ModelId.from_litellm("vertex_ai/gemini-2.5-flash")
            mock_settings.VISION_PROMPT = "Describe this image."

            result = await llm_service.describe_image(
                db=mock_db,
                image_url="https://example.com/mountain.jpg",
            )

        assert result == "A mountain landscape"
        mock_client_manager.get_client.assert_called_once_with(mock_db, None, "vertex_ai")

    @pytest.mark.asyncio
    async def test_describe_image_defaults_to_openai_from_settings(
        self,
        llm_service: LLMService,
        mock_client_manager: MagicMock,
        mock_db: AsyncMock,
    ) -> None:
        """describe_image defaults to openai provider when VISION_MODEL has openai prefix."""
        response = LLMResponse(
            content="A cat on a mat",
            model="gpt-5.1",
            tokens_used=20,
            finish_reason="stop",
            provider="openai",
        )
        mock_provider = MagicMock()
        mock_provider.complete = AsyncMock(return_value=response)
        mock_client_manager.get_client = AsyncMock(return_value=mock_provider)

        with patch("src.llm_config.service.settings") as mock_settings:
            mock_settings.VISION_MODEL = ModelId.from_litellm("openai/gpt-5.1")
            mock_settings.VISION_PROMPT = "Describe this image."

            result = await llm_service.describe_image(
                db=mock_db,
                image_url="https://example.com/cat.jpg",
            )

        assert result == "A cat on a mat"
        mock_client_manager.get_client.assert_called_once_with(mock_db, None, "openai")
