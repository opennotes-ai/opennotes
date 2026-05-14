"""Unit tests for LLMService retry behavior on complete, generate_embedding and describe_image."""

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from pydantic_ai.exceptions import ModelAPIError, ModelHTTPError

from src.llm_config.manager import LLMClientManager
from src.llm_config.providers.base import LLMMessage, LLMResponse
from src.llm_config.service import TRANSIENT_EXCEPTIONS, LLMService, _is_retryable


def _make_model_http_error(status_code: int = 502) -> ModelHTTPError:
    return ModelHTTPError(status_code=status_code, model_name="test-model", body=None)


def _make_model_api_error(message: str = "API failure") -> ModelAPIError:
    return ModelAPIError(model_name="test-model", message=message)


@dataclass
class _FakeEmbeddingResult:
    embeddings: list[list[float]]
    inputs: list[str]
    input_type: str
    model_name: str
    provider_name: str


def _make_embedder_mock(**overrides: object) -> MagicMock:
    mock = MagicMock()
    mock.embed_documents = AsyncMock(**overrides)
    mock.embed_query = AsyncMock(**overrides)
    return mock


def test_chunk_embedding_embedder_uses_explicit_196_constructor_shape() -> None:
    from src.services import chunk_embedding

    settings = MagicMock()
    settings.EMBEDDING_MODEL.to_pydantic_ai.return_value = "google-gla:gemini-embedding-001"

    chunk_embedding.reset_chunk_embedding_services()
    try:
        with (
            patch.object(chunk_embedding, "get_settings", return_value=settings),
            patch.object(chunk_embedding, "Embedder") as mock_embedder,
        ):
            embedder = chunk_embedding._get_embedder()

        assert embedder is mock_embedder.return_value
        mock_embedder.assert_called_once_with(
            "google-gla:gemini-embedding-001",
            defer_model_check=True,
        )
    finally:
        chunk_embedding.reset_chunk_embedding_services()


class TestLLMServiceCompleteRetry:
    """Tests for LLMService.complete retry behavior."""

    @pytest.fixture
    def mock_client_manager(self) -> MagicMock:
        return MagicMock(spec=LLMClientManager)

    @pytest.fixture
    def llm_service(self, mock_client_manager: MagicMock) -> LLMService:
        return LLMService(client_manager=mock_client_manager, embedder=MagicMock())

    @pytest.fixture
    def mock_llm_provider(self) -> MagicMock:
        provider = MagicMock()
        provider.api_key = "test-api-key"
        return provider

    @pytest.mark.asyncio
    async def test_complete_retries_on_model_http_error(
        self,
        llm_service: LLMService,
        mock_client_manager: MagicMock,
        mock_llm_provider: MagicMock,
    ) -> None:
        mock_client_manager.get_client = AsyncMock(return_value=mock_llm_provider)
        success = LLMResponse(
            content='{"is_relevant": true}',
            model="test",
            tokens_used=10,
            finish_reason="stop",
            provider="openai",
        )
        call_count = 0

        async def side_effect(*a, **kw):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise _make_model_http_error(502)
            return success

        mock_llm_provider.complete = AsyncMock(side_effect=side_effect)
        result = await llm_service.complete(messages=[LLMMessage(role="user", content="test")])
        assert call_count == 2
        assert result.content == '{"is_relevant": true}'

    @pytest.mark.asyncio
    async def test_complete_retries_on_model_api_error(
        self,
        llm_service: LLMService,
        mock_client_manager: MagicMock,
        mock_llm_provider: MagicMock,
    ) -> None:
        mock_client_manager.get_client = AsyncMock(return_value=mock_llm_provider)
        success = LLMResponse(
            content="ok",
            model="test",
            tokens_used=5,
            finish_reason="stop",
            provider="openai",
        )
        call_count = 0

        async def side_effect(*a, **kw):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise _make_model_api_error("Temporary API failure")
            return success

        mock_llm_provider.complete = AsyncMock(side_effect=side_effect)
        result = await llm_service.complete(messages=[LLMMessage(role="user", content="test")])
        assert call_count == 2
        assert result.content == "ok"

    @pytest.mark.asyncio
    async def test_complete_gives_up_after_2_attempts(
        self,
        llm_service: LLMService,
        mock_client_manager: MagicMock,
        mock_llm_provider: MagicMock,
    ) -> None:
        mock_client_manager.get_client = AsyncMock(return_value=mock_llm_provider)
        mock_llm_provider.complete = AsyncMock(side_effect=_make_model_http_error(503))
        with pytest.raises(ModelHTTPError):
            await llm_service.complete(messages=[LLMMessage(role="user", content="test")])
        assert mock_llm_provider.complete.call_count == 2

    @pytest.mark.asyncio
    async def test_complete_does_not_retry_value_error(
        self,
        llm_service: LLMService,
        mock_client_manager: MagicMock,
        mock_llm_provider: MagicMock,
    ) -> None:
        mock_client_manager.get_client = AsyncMock(return_value=mock_llm_provider)
        mock_llm_provider.complete = AsyncMock(side_effect=ValueError("bad input"))
        with pytest.raises(ValueError, match="bad input"):
            await llm_service.complete(messages=[LLMMessage(role="user", content="test")])
        assert mock_llm_provider.complete.call_count == 1

    @pytest.mark.asyncio
    async def test_complete_does_not_retry_4xx_http_error(
        self,
        llm_service: LLMService,
        mock_client_manager: MagicMock,
        mock_llm_provider: MagicMock,
    ) -> None:
        mock_client_manager.get_client = AsyncMock(return_value=mock_llm_provider)
        mock_llm_provider.complete = AsyncMock(side_effect=_make_model_http_error(400))
        with pytest.raises(ModelHTTPError):
            await llm_service.complete(messages=[LLMMessage(role="user", content="test")])
        assert mock_llm_provider.complete.call_count == 1


class TestLLMServiceGenerateEmbeddingRetry:
    """Tests for LLMService.generate_embedding retry behavior."""

    @pytest.fixture
    def mock_embedder(self) -> MagicMock:
        return _make_embedder_mock()

    @pytest.fixture
    def llm_service(self, mock_embedder: MagicMock) -> LLMService:
        return LLMService(
            client_manager=MagicMock(spec=LLMClientManager),
            embedder=mock_embedder,
        )

    @pytest.mark.asyncio
    async def test_generate_embedding_retries_on_transient_failure(
        self,
        llm_service: LLMService,
        mock_embedder: MagicMock,
    ) -> None:
        success_result = _FakeEmbeddingResult(
            embeddings=[[0.1] * 1536],
            inputs=["Test text for embedding"],
            input_type="document",
            model_name="text-embedding-3-small",
            provider_name="openai",
        )
        call_count = 0

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Transient network error")
            return success_result

        mock_embedder.embed_documents = AsyncMock(side_effect=side_effect)

        embedding, provider, model = await llm_service.generate_embedding(
            text="Test text for embedding",
        )

        assert call_count == 3
        assert embedding == [0.1] * 1536
        assert provider == "openai"
        assert model == "text-embedding-3-small"

    @pytest.mark.asyncio
    async def test_generate_embedding_retries_on_model_http_error(
        self,
        llm_service: LLMService,
        mock_embedder: MagicMock,
    ) -> None:
        success_result = _FakeEmbeddingResult(
            embeddings=[[0.1] * 1536],
            inputs=["Test text for embedding"],
            input_type="document",
            model_name="text-embedding-3-small",
            provider_name="openai",
        )
        call_count = 0

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise _make_model_http_error(429)
            return success_result

        mock_embedder.embed_documents = AsyncMock(side_effect=side_effect)

        embedding, _provider, _model = await llm_service.generate_embedding(
            text="Test text for embedding",
        )

        assert call_count == 2
        assert embedding == [0.1] * 1536

    @pytest.mark.asyncio
    async def test_generate_embedding_gives_up_after_max_retries(
        self,
        llm_service: LLMService,
        mock_embedder: MagicMock,
    ) -> None:
        mock_embedder.embed_documents = AsyncMock(
            side_effect=ConnectionError("Persistent network error")
        )

        with pytest.raises(ConnectionError, match="Persistent network error"):
            await llm_service.generate_embedding(text="Test text for embedding")

        assert mock_embedder.embed_documents.call_count == 3

    @pytest.mark.asyncio
    async def test_generate_embedding_hot_path_override_uses_2_attempts(
        self,
        llm_service: LLMService,
        mock_embedder: MagicMock,
    ) -> None:
        mock_embedder.embed_documents = AsyncMock(side_effect=ConnectionError("still failing"))

        with pytest.raises(ConnectionError, match="still failing"):
            await llm_service.generate_embedding(
                text="Test text for embedding",
                retry_attempts=2,
            )

        assert mock_embedder.embed_documents.call_count == 2

    @pytest.mark.asyncio
    @pytest.mark.parametrize("retry_attempts", [0, -1])
    async def test_generate_embedding_rejects_non_positive_retry_override(
        self,
        retry_attempts: int,
        llm_service: LLMService,
        mock_embedder: MagicMock,
    ) -> None:
        with pytest.raises(ValueError, match=f"retry_attempts must be >= 1, got {retry_attempts}"):
            await llm_service.generate_embedding(
                text="Test text for embedding",
                retry_attempts=retry_attempts,
            )

        mock_embedder.embed_documents.assert_not_called()

    @pytest.mark.asyncio
    async def test_generate_embedding_succeeds_without_retry_when_no_error(
        self,
        llm_service: LLMService,
        mock_embedder: MagicMock,
    ) -> None:
        success_result = _FakeEmbeddingResult(
            embeddings=[[0.5] * 1536],
            inputs=["Test text"],
            input_type="document",
            model_name="text-embedding-3-small",
            provider_name="openai",
        )
        mock_embedder.embed_documents = AsyncMock(return_value=success_result)

        embedding, provider, _model = await llm_service.generate_embedding(text="Test text")

        assert mock_embedder.embed_documents.call_count == 1
        assert embedding == [0.5] * 1536
        assert provider == "openai"

    @pytest.mark.asyncio
    async def test_generate_embedding_uses_embed_query_for_query_type(
        self,
        llm_service: LLMService,
        mock_embedder: MagicMock,
    ) -> None:
        success_result = _FakeEmbeddingResult(
            embeddings=[[0.5] * 1536],
            inputs=["query text"],
            input_type="query",
            model_name="text-embedding-3-small",
            provider_name="openai",
        )
        mock_embedder.embed_query = AsyncMock(return_value=success_result)

        embedding, _provider, _model = await llm_service.generate_embedding(
            text="query text", input_type="query"
        )

        mock_embedder.embed_query.assert_awaited_once()
        mock_embedder.embed_documents.assert_not_called()
        assert embedding == [0.5] * 1536

    @pytest.mark.asyncio
    async def test_generate_embedding_uses_embed_documents_for_document_type(
        self,
        llm_service: LLMService,
        mock_embedder: MagicMock,
    ) -> None:
        success_result = _FakeEmbeddingResult(
            embeddings=[[0.5] * 1536],
            inputs=["doc text"],
            input_type="document",
            model_name="text-embedding-3-small",
            provider_name="openai",
        )
        mock_embedder.embed_documents = AsyncMock(return_value=success_result)

        await llm_service.generate_embedding(text="doc text", input_type="document")

        mock_embedder.embed_documents.assert_awaited_once()
        mock_embedder.embed_query.assert_not_called()


class TestLLMServiceDescribeImageRetry:
    """Tests for LLMService.describe_image retry behavior."""

    @pytest.fixture
    def mock_client_manager(self) -> MagicMock:
        return MagicMock(spec=LLMClientManager)

    @pytest.fixture
    def llm_service(self, mock_client_manager: MagicMock) -> LLMService:
        return LLMService(client_manager=mock_client_manager, embedder=MagicMock())

    @pytest.fixture
    def mock_llm_provider(self) -> MagicMock:
        provider = MagicMock()
        provider.api_key = "test-api-key"
        return provider

    @pytest.mark.asyncio
    async def test_describe_image_retries_on_transient_failure(
        self,
        llm_service: LLMService,
        mock_client_manager: MagicMock,
        mock_llm_provider: MagicMock,
    ) -> None:
        mock_client_manager.get_client = AsyncMock(return_value=mock_llm_provider)

        success_response = LLMResponse(
            content="An image showing a cat",
            model="gpt-5.1",
            tokens_used=20,
            finish_reason="stop",
            provider="openai",
        )

        call_count = 0

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise TimeoutError("Request timed out")
            return success_response

        mock_llm_provider.complete = AsyncMock(side_effect=side_effect)

        description = await llm_service.describe_image(
            image_url="https://example.com/image.jpg",
        )

        assert call_count == 2
        assert description == "An image showing a cat"

    @pytest.mark.asyncio
    async def test_describe_image_retries_on_model_http_error(
        self,
        llm_service: LLMService,
        mock_client_manager: MagicMock,
        mock_llm_provider: MagicMock,
    ) -> None:
        mock_client_manager.get_client = AsyncMock(return_value=mock_llm_provider)

        success_response = LLMResponse(
            content="A landscape photo",
            model="gpt-5.1",
            tokens_used=15,
            finish_reason="stop",
            provider="openai",
        )

        call_count = 0

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise _make_model_http_error(429)
            return success_response

        mock_llm_provider.complete = AsyncMock(side_effect=side_effect)

        description = await llm_service.describe_image(
            image_url="https://example.com/landscape.jpg",
        )

        assert call_count == 3
        assert description == "A landscape photo"

    @pytest.mark.asyncio
    async def test_describe_image_gives_up_after_max_retries(
        self,
        llm_service: LLMService,
        mock_client_manager: MagicMock,
        mock_llm_provider: MagicMock,
    ) -> None:
        mock_client_manager.get_client = AsyncMock(return_value=mock_llm_provider)

        mock_llm_provider.complete = AsyncMock(side_effect=TimeoutError("Persistent timeout"))

        with pytest.raises(TimeoutError, match="Persistent timeout"):
            await llm_service.describe_image(
                image_url="https://example.com/image.jpg",
            )

        assert mock_llm_provider.complete.call_count == 5


class TestSanitizeEmbeddingText:
    """Tests for LLMService._sanitize_embedding_text."""

    @pytest.fixture
    def llm_service(self) -> LLMService:
        return LLMService(client_manager=MagicMock(spec=LLMClientManager), embedder=MagicMock())

    def test_strips_null_byte(self, llm_service: LLMService) -> None:
        assert llm_service._sanitize_embedding_text("hello\x00world") == "helloworld"

    def test_strips_control_chars(self, llm_service: LLMService) -> None:
        text = "a\x01b\x02c\x10d\x1fe"
        assert llm_service._sanitize_embedding_text(text) == "abcde"

    def test_preserves_tab_newline_cr(self, llm_service: LLMService) -> None:
        text = "line1\n\tindented\r\nline2"
        assert llm_service._sanitize_embedding_text(text) == text

    def test_strips_del_and_c1_control_chars(self, llm_service: LLMService) -> None:
        text = "a\x7fb\x80c\x9fd"
        assert llm_service._sanitize_embedding_text(text) == "abcd"

    def test_clean_text_passes_through(self, llm_service: LLMService) -> None:
        text = "Hello, world\\! This is normal text with unicode: cafe\u0301"
        assert llm_service._sanitize_embedding_text(text) == text

    def test_empty_string(self, llm_service: LLMService) -> None:
        assert llm_service._sanitize_embedding_text("") == ""

    @pytest.mark.asyncio
    async def test_generate_embedding_sanitizes_before_embed(self) -> None:
        result = _FakeEmbeddingResult(
            embeddings=[[0.1] * 1536],
            inputs=["helloworld"],
            input_type="document",
            model_name="text-embedding-3-small",
            provider_name="openai",
        )
        mock_embedder = _make_embedder_mock(return_value=result)
        service = LLMService(
            client_manager=MagicMock(spec=LLMClientManager), embedder=mock_embedder
        )

        await service.generate_embedding(text="hello\x00world")

        call_args = mock_embedder.embed_documents.call_args
        assert call_args[0][0] == "helloworld"

    @pytest.mark.asyncio
    async def test_generate_embeddings_batch_sanitizes_each_text(self) -> None:
        result = _FakeEmbeddingResult(
            embeddings=[[0.1] * 1536, [0.2] * 1536],
            inputs=["helloworld", "foobar"],
            input_type="document",
            model_name="text-embedding-3-small",
            provider_name="openai",
        )
        mock_embedder = _make_embedder_mock(return_value=result)
        service = LLMService(
            client_manager=MagicMock(spec=LLMClientManager), embedder=mock_embedder
        )

        await service.generate_embeddings_batch(texts=["hello\x00world", "foo\x01bar"])

        call_args = mock_embedder.embed_documents.call_args
        assert call_args[0][0] == ["helloworld", "foobar"]


class TestTransientExceptionsTuple:
    """Tests to verify TRANSIENT_EXCEPTIONS contains pydantic-ai exceptions, not raw httpx."""

    def test_includes_model_http_error(self) -> None:
        assert ModelHTTPError in TRANSIENT_EXCEPTIONS

    def test_includes_model_api_error(self) -> None:
        assert ModelAPIError in TRANSIENT_EXCEPTIONS

    def test_includes_connection_error(self) -> None:
        assert ConnectionError in TRANSIENT_EXCEPTIONS

    def test_includes_timeout_error(self) -> None:
        assert TimeoutError in TRANSIENT_EXCEPTIONS

    def test_does_not_include_httpx_connect_error(self) -> None:
        assert httpx.ConnectError not in TRANSIENT_EXCEPTIONS

    def test_does_not_include_httpx_timeout_exception(self) -> None:
        assert httpx.TimeoutException not in TRANSIENT_EXCEPTIONS


class TestRetryDecoratorConfiguration:
    """Tests to verify retry decorator configuration on static retry methods."""

    def test_describe_image_has_retry_decorator(self) -> None:
        method = LLMService.describe_image
        assert hasattr(method, "retry")

    def test_complete_has_retry_decorator(self) -> None:
        method = LLMService.complete
        assert hasattr(method, "retry")

    def test_complete_retry_uses_2_attempts(self) -> None:
        method = LLMService.complete
        assert method.retry.stop.max_attempt_number == 2

    def test_generate_embeddings_batch_has_retry_decorator(self) -> None:
        method = LLMService.generate_embeddings_batch
        assert hasattr(method, "retry")

    def test_generate_embeddings_batch_retry_uses_5_attempts(self) -> None:
        method = LLMService.generate_embeddings_batch
        assert method.retry.stop.max_attempt_number == 5


class TestRetryPredicate:
    """Tests for _is_retryable predicate that filters permanent 4xx errors."""

    def test_retries_model_http_error_429(self) -> None:
        assert _is_retryable(_make_model_http_error(429)) is True

    def test_retries_model_http_error_500(self) -> None:
        assert _is_retryable(_make_model_http_error(500)) is True

    def test_retries_model_http_error_502(self) -> None:
        assert _is_retryable(_make_model_http_error(502)) is True

    def test_retries_model_http_error_503(self) -> None:
        assert _is_retryable(_make_model_http_error(503)) is True

    def test_does_not_retry_model_http_error_400(self) -> None:
        assert _is_retryable(_make_model_http_error(400)) is False

    def test_does_not_retry_model_http_error_401(self) -> None:
        assert _is_retryable(_make_model_http_error(401)) is False

    def test_does_not_retry_model_http_error_403(self) -> None:
        assert _is_retryable(_make_model_http_error(403)) is False

    def test_does_not_retry_model_http_error_404(self) -> None:
        assert _is_retryable(_make_model_http_error(404)) is False

    def test_does_not_retry_model_http_error_422(self) -> None:
        assert _is_retryable(_make_model_http_error(422)) is False

    def test_retries_model_api_error(self) -> None:
        assert _is_retryable(_make_model_api_error()) is True

    def test_retries_connection_error(self) -> None:
        assert _is_retryable(ConnectionError("network")) is True

    def test_retries_timeout_error(self) -> None:
        assert _is_retryable(TimeoutError("timed out")) is True

    def test_does_not_retry_value_error(self) -> None:
        assert _is_retryable(ValueError("bad input")) is False

    def test_does_not_retry_runtime_error(self) -> None:
        assert _is_retryable(RuntimeError("oops")) is False


class TestLLMServiceBatchEmbeddingRetry:
    """Tests for LLMService.generate_embeddings_batch retry behavior."""

    @pytest.fixture
    def mock_embedder(self) -> MagicMock:
        return _make_embedder_mock()

    @pytest.fixture
    def llm_service(self, mock_embedder: MagicMock) -> LLMService:
        return LLMService(
            client_manager=MagicMock(spec=LLMClientManager),
            embedder=mock_embedder,
        )

    @pytest.mark.asyncio
    async def test_batch_retries_on_transient_failure(
        self,
        llm_service: LLMService,
        mock_embedder: MagicMock,
    ) -> None:
        success_result = _FakeEmbeddingResult(
            embeddings=[[0.1] * 1536, [0.2] * 1536],
            inputs=["Text A", "Text B"],
            input_type="document",
            model_name="text-embedding-3-small",
            provider_name="openai",
        )
        call_count = 0

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Transient network error")
            return success_result

        mock_embedder.embed_documents = AsyncMock(side_effect=side_effect)

        results = await llm_service.generate_embeddings_batch(
            texts=["Text A", "Text B"],
        )

        assert call_count == 3
        assert len(results) == 2
        assert results[0][0] == [0.1] * 1536

    @pytest.mark.asyncio
    async def test_batch_does_not_retry_on_400(
        self,
        llm_service: LLMService,
        mock_embedder: MagicMock,
    ) -> None:
        mock_embedder.embed_documents = AsyncMock(side_effect=_make_model_http_error(400))
        with pytest.raises(ModelHTTPError):
            await llm_service.generate_embeddings_batch(texts=["Text A"])
        assert mock_embedder.embed_documents.call_count == 1

    @pytest.mark.asyncio
    async def test_batch_gives_up_after_5_attempts(
        self,
        llm_service: LLMService,
        mock_embedder: MagicMock,
    ) -> None:
        mock_embedder.embed_documents = AsyncMock(side_effect=ConnectionError("Persistent failure"))
        with pytest.raises(ConnectionError, match="Persistent failure"):
            await llm_service.generate_embeddings_batch(texts=["Text A"])
        assert mock_embedder.embed_documents.call_count == 5
