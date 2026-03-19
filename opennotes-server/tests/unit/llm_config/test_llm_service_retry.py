"""Unit tests for LLMService retry behavior on complete, generate_embedding and describe_image."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from litellm.exceptions import BadRequestError

from src.config import settings
from src.llm_config.manager import LLMClientManager
from src.llm_config.providers.base import LLMMessage, LLMResponse
from src.llm_config.providers.litellm_provider import EmptyLLMResponseError
from src.llm_config.service import LLMService


class TestLLMServiceCompleteRetry:
    """Tests for LLMService.complete retry behavior."""

    @pytest.fixture
    def mock_client_manager(self) -> MagicMock:
        return MagicMock(spec=LLMClientManager)

    @pytest.fixture
    def llm_service(self, mock_client_manager: MagicMock) -> LLMService:
        return LLMService(client_manager=mock_client_manager)

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        return AsyncMock()

    @pytest.fixture
    def mock_llm_provider(self) -> MagicMock:
        provider = MagicMock()
        provider.api_key = "test-api-key"
        return provider

    @pytest.mark.asyncio
    async def test_complete_retries_on_empty_response_error(
        self,
        llm_service: LLMService,
        mock_client_manager: MagicMock,
        mock_db: AsyncMock,
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
                raise EmptyLLMResponseError("empty")
            return success

        mock_llm_provider.complete = AsyncMock(side_effect=side_effect)
        result = await llm_service.complete(
            db=mock_db, messages=[LLMMessage(role="user", content="test")]
        )
        assert call_count == 2
        assert result.content == '{"is_relevant": true}'

    @pytest.mark.asyncio
    async def test_complete_gives_up_after_2_attempts(
        self,
        llm_service: LLMService,
        mock_client_manager: MagicMock,
        mock_db: AsyncMock,
        mock_llm_provider: MagicMock,
    ) -> None:
        mock_client_manager.get_client = AsyncMock(return_value=mock_llm_provider)
        mock_llm_provider.complete = AsyncMock(side_effect=EmptyLLMResponseError("empty"))
        with pytest.raises(EmptyLLMResponseError):
            await llm_service.complete(
                db=mock_db, messages=[LLMMessage(role="user", content="test")]
            )
        assert mock_llm_provider.complete.call_count == 2

    @pytest.mark.asyncio
    async def test_complete_does_not_retry_value_error(
        self,
        llm_service: LLMService,
        mock_client_manager: MagicMock,
        mock_db: AsyncMock,
        mock_llm_provider: MagicMock,
    ) -> None:
        mock_client_manager.get_client = AsyncMock(return_value=mock_llm_provider)
        mock_llm_provider.complete = AsyncMock(side_effect=ValueError("bad input"))
        with pytest.raises(ValueError, match="bad input"):
            await llm_service.complete(
                db=mock_db, messages=[LLMMessage(role="user", content="test")]
            )
        assert mock_llm_provider.complete.call_count == 1


class TestLLMServiceGenerateEmbeddingRetry:
    """Tests for LLMService.generate_embedding retry behavior."""

    @pytest.fixture
    def mock_client_manager(self) -> MagicMock:
        """Create a mock LLM client manager."""
        return MagicMock(spec=LLMClientManager)

    @pytest.fixture
    def llm_service(self, mock_client_manager: MagicMock) -> LLMService:
        """Create an LLMService instance with mocked dependencies."""
        return LLMService(client_manager=mock_client_manager)

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Create a mock database session."""
        return AsyncMock()

    @pytest.fixture
    def mock_llm_provider(self) -> MagicMock:
        """Create a mock LLM provider with API key."""
        provider = MagicMock()
        provider.api_key = "test-api-key"
        return provider

    @pytest.mark.asyncio
    async def test_generate_embedding_retries_on_transient_failure(
        self,
        llm_service: LLMService,
        mock_client_manager: MagicMock,
        mock_db: AsyncMock,
        mock_llm_provider: MagicMock,
    ) -> None:
        """Test that generate_embedding retries on transient failures and succeeds."""
        mock_client_manager.get_client = AsyncMock(return_value=mock_llm_provider)
        community_server_id = uuid4()

        mock_embedding_response = MagicMock()
        mock_embedding_response.data = [{"embedding": [0.1] * 1536}]
        mock_embedding_response.usage = MagicMock(total_tokens=10)

        call_count = 0

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Transient network error")
            return mock_embedding_response

        with patch("src.llm_config.service.litellm") as mock_litellm:
            mock_litellm.aembedding = AsyncMock(side_effect=side_effect)

            embedding, provider, _model = await llm_service.generate_embedding(
                db=mock_db,
                text="Test text for embedding",
                community_server_id=community_server_id,
            )

            assert call_count == 3
            assert embedding == [0.1] * 1536
            assert provider == "litellm"

    @pytest.mark.asyncio
    async def test_generate_embedding_gives_up_after_max_retries(
        self,
        llm_service: LLMService,
        mock_client_manager: MagicMock,
        mock_db: AsyncMock,
        mock_llm_provider: MagicMock,
    ) -> None:
        """Test that generate_embedding raises after exhausting retries."""
        mock_client_manager.get_client = AsyncMock(return_value=mock_llm_provider)
        community_server_id = uuid4()

        with patch("src.llm_config.service.litellm") as mock_litellm:
            mock_litellm.aembedding = AsyncMock(
                side_effect=ConnectionError("Persistent network error")
            )

            with pytest.raises(ConnectionError, match="Persistent network error"):
                await llm_service.generate_embedding(
                    db=mock_db,
                    text="Test text for embedding",
                    community_server_id=community_server_id,
                )

            assert mock_litellm.aembedding.call_count == 3

    @pytest.mark.asyncio
    async def test_generate_embedding_hot_path_override_uses_2_attempts(
        self,
        llm_service: LLMService,
        mock_client_manager: MagicMock,
        mock_db: AsyncMock,
        mock_llm_provider: MagicMock,
    ) -> None:
        """Hot-path callers should be able to reduce retry attempts to 2."""
        mock_client_manager.get_client = AsyncMock(return_value=mock_llm_provider)
        community_server_id = uuid4()

        with patch("src.llm_config.service.litellm") as mock_litellm:
            mock_litellm.aembedding = AsyncMock(side_effect=ConnectionError("still failing"))

            with pytest.raises(ConnectionError, match="still failing"):
                await llm_service.generate_embedding(
                    db=mock_db,
                    text="Test text for embedding",
                    community_server_id=community_server_id,
                    retry_attempts=2,
                )

            assert mock_litellm.aembedding.call_count == 2

    @pytest.mark.asyncio
    @pytest.mark.parametrize("retry_attempts", [0, -1])
    async def test_generate_embedding_rejects_non_positive_retry_override(
        self,
        retry_attempts: int,
        llm_service: LLMService,
        mock_client_manager: MagicMock,
        mock_db: AsyncMock,
        mock_llm_provider: MagicMock,
    ) -> None:
        """Explicit non-positive retry overrides should fail fast."""
        mock_client_manager.get_client = AsyncMock(return_value=mock_llm_provider)
        community_server_id = uuid4()

        with patch("src.llm_config.service.litellm") as mock_litellm:
            mock_litellm.aembedding = AsyncMock()

            with pytest.raises(
                ValueError, match=f"retry_attempts must be >= 1, got {retry_attempts}"
            ):
                await llm_service.generate_embedding(
                    db=mock_db,
                    text="Test text for embedding",
                    community_server_id=community_server_id,
                    retry_attempts=retry_attempts,
                )

            assert mock_litellm.aembedding.call_count == 0

    @pytest.mark.asyncio
    async def test_generate_embedding_succeeds_without_retry_when_no_error(
        self,
        llm_service: LLMService,
        mock_client_manager: MagicMock,
        mock_db: AsyncMock,
        mock_llm_provider: MagicMock,
    ) -> None:
        """Test that generate_embedding succeeds on first try when no error."""
        mock_client_manager.get_client = AsyncMock(return_value=mock_llm_provider)
        community_server_id = uuid4()

        mock_embedding_response = MagicMock()
        mock_embedding_response.data = [{"embedding": [0.5] * 1536}]
        mock_embedding_response.usage = MagicMock(total_tokens=8)

        with patch("src.llm_config.service.litellm") as mock_litellm:
            mock_litellm.aembedding = AsyncMock(return_value=mock_embedding_response)

            embedding, _provider, _model = await llm_service.generate_embedding(
                db=mock_db,
                text="Test text",
                community_server_id=community_server_id,
            )

            assert mock_litellm.aembedding.call_count == 1
            assert embedding == [0.5] * 1536

    @pytest.mark.asyncio
    async def test_generate_embedding_passes_configured_timeout(
        self,
        llm_service: LLMService,
        mock_client_manager: MagicMock,
        mock_db: AsyncMock,
        mock_llm_provider: MagicMock,
    ) -> None:
        """Embedding requests should pass EMBEDDING_TIMEOUT_SECONDS to LiteLLM."""
        mock_client_manager.get_client = AsyncMock(return_value=mock_llm_provider)
        community_server_id = uuid4()

        mock_embedding_response = MagicMock()
        mock_embedding_response.data = [{"embedding": [0.2] * 1536}]
        mock_embedding_response.usage = MagicMock(total_tokens=3)

        with patch("src.llm_config.service.litellm") as mock_litellm:
            mock_litellm.aembedding = AsyncMock(return_value=mock_embedding_response)

            await llm_service.generate_embedding(
                db=mock_db,
                text="Test text",
                community_server_id=community_server_id,
            )

            call_kwargs = mock_litellm.aembedding.call_args.kwargs
            assert call_kwargs["timeout"] == settings.EMBEDDING_TIMEOUT_SECONDS

    @pytest.mark.asyncio
    async def test_generate_embeddings_batch_passes_configured_timeout(
        self,
        llm_service: LLMService,
        mock_client_manager: MagicMock,
        mock_db: AsyncMock,
        mock_llm_provider: MagicMock,
    ) -> None:
        """Batch embedding requests should pass EMBEDDING_TIMEOUT_SECONDS to LiteLLM."""
        mock_client_manager.get_client = AsyncMock(return_value=mock_llm_provider)
        community_server_id = uuid4()

        mock_embedding_response = MagicMock()
        mock_embedding_response.data = [
            {"index": 0, "embedding": [0.3] * 1536},
            {"index": 1, "embedding": [0.4] * 1536},
        ]
        mock_embedding_response.usage = MagicMock(total_tokens=6)

        with patch("src.llm_config.service.litellm") as mock_litellm:
            mock_litellm.aembedding = AsyncMock(return_value=mock_embedding_response)

            await llm_service.generate_embeddings_batch(
                db=mock_db,
                texts=["First text", "Second text"],
                community_server_id=community_server_id,
            )

            call_kwargs = mock_litellm.aembedding.call_args.kwargs
            assert call_kwargs["timeout"] == settings.EMBEDDING_TIMEOUT_SECONDS


class TestLLMServiceDescribeImageRetry:
    """Tests for LLMService.describe_image retry behavior."""

    @pytest.fixture
    def mock_client_manager(self) -> MagicMock:
        """Create a mock LLM client manager."""
        return MagicMock(spec=LLMClientManager)

    @pytest.fixture
    def llm_service(self, mock_client_manager: MagicMock) -> LLMService:
        """Create an LLMService instance with mocked dependencies."""
        return LLMService(client_manager=mock_client_manager)

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Create a mock database session."""
        return AsyncMock()

    @pytest.fixture
    def mock_llm_provider(self) -> MagicMock:
        """Create a mock LLM provider with API key."""
        provider = MagicMock()
        provider.api_key = "test-api-key"
        return provider

    @pytest.mark.asyncio
    async def test_describe_image_retries_on_transient_failure(
        self,
        llm_service: LLMService,
        mock_client_manager: MagicMock,
        mock_db: AsyncMock,
        mock_llm_provider: MagicMock,
    ) -> None:
        """Test that describe_image retries on transient failures and succeeds."""
        mock_client_manager.get_client = AsyncMock(return_value=mock_llm_provider)
        community_server_id = uuid4()

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
            db=mock_db,
            image_url="https://example.com/image.jpg",
            community_server_id=community_server_id,
        )

        assert call_count == 2
        assert description == "An image showing a cat"

    @pytest.mark.asyncio
    async def test_describe_image_gives_up_after_max_retries(
        self,
        llm_service: LLMService,
        mock_client_manager: MagicMock,
        mock_db: AsyncMock,
        mock_llm_provider: MagicMock,
    ) -> None:
        """Test that describe_image raises after exhausting retries."""
        mock_client_manager.get_client = AsyncMock(return_value=mock_llm_provider)
        community_server_id = uuid4()

        mock_llm_provider.complete = AsyncMock(side_effect=TimeoutError("Persistent timeout"))

        with pytest.raises(TimeoutError, match="Persistent timeout"):
            await llm_service.describe_image(
                db=mock_db,
                image_url="https://example.com/image.jpg",
                community_server_id=community_server_id,
            )

        assert mock_llm_provider.complete.call_count == 5


class TestSanitizeEmbeddingText:
    """Tests for LLMService._sanitize_embedding_text."""

    @pytest.fixture
    def llm_service(self) -> LLMService:
        return LLMService(client_manager=MagicMock(spec=LLMClientManager))

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
        text = "Hello, world! This is normal text with unicode: cafe\u0301"
        assert llm_service._sanitize_embedding_text(text) == text

    def test_empty_string(self, llm_service: LLMService) -> None:
        assert llm_service._sanitize_embedding_text("") == ""

    @pytest.mark.asyncio
    async def test_generate_embedding_sanitizes_before_aembedding(self) -> None:
        mock_client_manager = MagicMock(spec=LLMClientManager)
        service = LLMService(client_manager=mock_client_manager)
        mock_provider = MagicMock()
        mock_provider.api_key = "test-key"
        mock_client_manager.get_client = AsyncMock(return_value=mock_provider)

        mock_response = MagicMock()
        mock_response.data = [{"embedding": [0.1] * 1536}]
        mock_response.usage = MagicMock(total_tokens=10)

        with patch("src.llm_config.service.litellm") as mock_litellm:
            mock_litellm.aembedding = AsyncMock(return_value=mock_response)
            await service.generate_embedding(
                db=AsyncMock(), text="hello\x00world", community_server_id=uuid4()
            )
            call_kwargs = mock_litellm.aembedding.call_args.kwargs
            assert call_kwargs["input"] == ["helloworld"]

    @pytest.mark.asyncio
    async def test_generate_embeddings_batch_sanitizes_each_text(self) -> None:
        mock_client_manager = MagicMock(spec=LLMClientManager)
        service = LLMService(client_manager=mock_client_manager)
        mock_provider = MagicMock()
        mock_provider.api_key = "test-key"
        mock_client_manager.get_client = AsyncMock(return_value=mock_provider)

        mock_response = MagicMock()
        mock_response.data = [
            {"index": 0, "embedding": [0.1] * 1536},
            {"index": 1, "embedding": [0.2] * 1536},
        ]
        mock_response.usage = MagicMock(total_tokens=20)

        with patch(
            "src.llm_config.service.litellm.aembedding", new_callable=AsyncMock
        ) as mock_aembedding:
            mock_aembedding.return_value = mock_response
            await service.generate_embeddings_batch(
                db=AsyncMock(),
                texts=["hello\x00world", "foo\x01bar"],
                community_server_id=uuid4(),
            )
            call_kwargs = mock_aembedding.call_args.kwargs
            assert call_kwargs["input"] == ["helloworld", "foobar"]


def _make_bad_request_error(message: str = "invalid JSON") -> BadRequestError:
    return BadRequestError(
        message=message,
        model="openai/text-embedding-3-small",
        llm_provider="openai",
    )


class TestBadRequestErrorDiagnosticLogging:
    """Tests for BadRequestError diagnostic logging in embedding methods."""

    @pytest.fixture
    def llm_service(self) -> LLMService:
        mock_cm = MagicMock(spec=LLMClientManager)
        return LLMService(client_manager=mock_cm)

    @pytest.fixture
    def mock_provider(self) -> MagicMock:
        provider = MagicMock()
        provider.api_key = "test-key"
        return provider

    @pytest.mark.asyncio
    async def test_bad_request_error_is_reraised(
        self, llm_service: LLMService, mock_provider: MagicMock
    ) -> None:
        llm_service.client_manager.get_client = AsyncMock(return_value=mock_provider)
        with patch("src.llm_config.service.litellm") as mock_litellm:
            mock_litellm.aembedding = AsyncMock(side_effect=_make_bad_request_error())
            with pytest.raises(BadRequestError):
                await llm_service.generate_embedding(
                    db=AsyncMock(), text="test text", community_server_id=uuid4()
                )

    @pytest.mark.asyncio
    async def test_bad_request_error_not_retried(
        self, llm_service: LLMService, mock_provider: MagicMock
    ) -> None:
        llm_service.client_manager.get_client = AsyncMock(return_value=mock_provider)
        with patch("src.llm_config.service.litellm") as mock_litellm:
            mock_litellm.aembedding = AsyncMock(side_effect=_make_bad_request_error())
            with pytest.raises(BadRequestError):
                await llm_service.generate_embedding(
                    db=AsyncMock(), text="test text", community_server_id=uuid4()
                )
            assert mock_litellm.aembedding.call_count == 1

    @pytest.mark.asyncio
    async def test_bad_request_error_logs_text_preview(
        self, llm_service: LLMService, mock_provider: MagicMock
    ) -> None:
        llm_service.client_manager.get_client = AsyncMock(return_value=mock_provider)
        community_id = uuid4()
        with (
            patch("src.llm_config.service.litellm") as mock_litellm,
            patch("src.llm_config.service.logger") as mock_logger,
        ):
            mock_litellm.aembedding = AsyncMock(side_effect=_make_bad_request_error())
            with pytest.raises(BadRequestError):
                await llm_service.generate_embedding(
                    db=AsyncMock(), text="some test text", community_server_id=community_id
                )
            mock_logger.error.assert_called_once()
            call_kwargs = mock_logger.error.call_args
            extra = call_kwargs.kwargs.get("extra") or call_kwargs[1].get("extra")
            assert "text_preview" in extra
            assert "text_length" in extra
            assert extra["text_length"] == len("some test text")
            assert extra["community_server_id"] == str(community_id)

    @pytest.mark.asyncio
    async def test_bad_request_error_truncates_long_text(
        self, llm_service: LLMService, mock_provider: MagicMock
    ) -> None:
        llm_service.client_manager.get_client = AsyncMock(return_value=mock_provider)
        long_text = "x" * 500
        with (
            patch("src.llm_config.service.litellm") as mock_litellm,
            patch("src.llm_config.service.logger") as mock_logger,
        ):
            mock_litellm.aembedding = AsyncMock(side_effect=_make_bad_request_error())
            with pytest.raises(BadRequestError):
                await llm_service.generate_embedding(
                    db=AsyncMock(), text=long_text, community_server_id=uuid4()
                )
            extra = mock_logger.error.call_args.kwargs.get("extra") or mock_logger.error.call_args[
                1
            ].get("extra")
            assert len(extra["text_preview"]) <= 200

    @pytest.mark.asyncio
    async def test_bad_request_error_in_batch(
        self, llm_service: LLMService, mock_provider: MagicMock
    ) -> None:
        llm_service.client_manager.get_client = AsyncMock(return_value=mock_provider)
        with (
            patch(
                "src.llm_config.service.litellm.aembedding", new_callable=AsyncMock
            ) as mock_aembedding,
            patch("src.llm_config.service.logger") as mock_logger,
        ):
            mock_aembedding.side_effect = _make_bad_request_error()
            with pytest.raises(BadRequestError):
                await llm_service.generate_embeddings_batch(
                    db=AsyncMock(),
                    texts=["text one", "text two"],
                    community_server_id=uuid4(),
                )
            mock_logger.error.assert_called_once()
            extra = mock_logger.error.call_args.kwargs.get("extra") or mock_logger.error.call_args[
                1
            ].get("extra")
            assert "text_preview" in extra


class TestRetryDecoratorConfiguration:
    """Tests to verify retry decorator configuration on static retry methods."""

    def test_describe_image_has_retry_decorator(self) -> None:
        """Verify describe_image has the @retry decorator applied."""
        from src.llm_config.service import LLMService

        method = LLMService.describe_image
        assert hasattr(method, "retry")

    def test_complete_has_retry_decorator(self) -> None:
        method = LLMService.complete
        assert hasattr(method, "retry")

    def test_complete_retry_uses_2_attempts(self) -> None:
        method = LLMService.complete
        assert method.retry.stop.max_attempt_number == 2
