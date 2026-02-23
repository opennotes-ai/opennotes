"""Unit tests for LLMService retry behavior on generate_embedding and describe_image."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.llm_config.manager import LLMClientManager
from src.llm_config.providers.base import LLMResponse
from src.llm_config.service import LLMService


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

            assert mock_litellm.aembedding.call_count == 5

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


class TestRetryDecoratorConfiguration:
    """Tests to verify retry decorator configuration matches between methods."""

    def test_generate_embedding_has_retry_decorator(self) -> None:
        """Verify generate_embedding has the @retry decorator applied."""
        from src.llm_config.service import LLMService

        method = LLMService.generate_embedding
        assert hasattr(method, "retry")

    def test_describe_image_has_retry_decorator(self) -> None:
        """Verify describe_image has the @retry decorator applied."""
        from src.llm_config.service import LLMService

        method = LLMService.describe_image
        assert hasattr(method, "retry")

    def test_retry_configuration_matches(self) -> None:
        """Verify both methods have matching retry configurations."""
        from src.llm_config.service import LLMService

        embed_method = LLMService.generate_embedding
        image_method = LLMService.describe_image

        embed_retry = embed_method.retry
        image_retry = image_method.retry

        assert embed_retry.stop.max_attempt_number == image_retry.stop.max_attempt_number
        assert embed_retry.wait.multiplier == image_retry.wait.multiplier
        assert embed_retry.wait.min == image_retry.wait.min
        assert embed_retry.wait.max == image_retry.wait.max
