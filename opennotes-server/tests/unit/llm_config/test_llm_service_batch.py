"""Unit tests for LLMService batch embedding functionality."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.llm_config.service import LLMService


class TestGenerateEmbeddingsBatch:
    """Tests for LLMService.generate_embeddings_batch() method."""

    @pytest.mark.asyncio
    async def test_empty_list_returns_empty(self):
        """Test that empty texts list returns empty results without API call."""
        mock_client_manager = MagicMock()
        service = LLMService(client_manager=mock_client_manager)

        mock_db = AsyncMock()

        results = await service.generate_embeddings_batch(
            db=mock_db,
            texts=[],
            community_server_id=uuid4(),
        )

        assert results == []
        mock_client_manager.get_client.assert_not_called()

    @pytest.mark.asyncio
    async def test_batch_embedding_single_api_call(self):
        """Test that multiple texts are embedded in a single API call."""
        mock_client_manager = MagicMock()
        mock_provider = MagicMock()
        mock_provider.api_key = "test-api-key"
        mock_client_manager.get_client = AsyncMock(return_value=mock_provider)

        service = LLMService(client_manager=mock_client_manager)

        mock_response = MagicMock()
        mock_response.data = [
            {"index": 0, "embedding": [0.1] * 1536},
            {"index": 1, "embedding": [0.2] * 1536},
            {"index": 2, "embedding": [0.3] * 1536},
        ]
        mock_response.usage = MagicMock()
        mock_response.usage.total_tokens = 100

        mock_db = AsyncMock()
        community_server_id = uuid4()

        with patch(
            "src.llm_config.service.litellm.aembedding", new_callable=AsyncMock
        ) as mock_aembedding:
            mock_aembedding.return_value = mock_response

            results = await service.generate_embeddings_batch(
                db=mock_db,
                texts=["Text A", "Text B", "Text C"],
                community_server_id=community_server_id,
            )

            mock_aembedding.assert_called_once()
            call_kwargs = mock_aembedding.call_args[1]
            assert call_kwargs["input"] == ["Text A", "Text B", "Text C"]
            assert call_kwargs["api_key"] == "test-api-key"

        assert len(results) == 3
        assert results[0][0] == [0.1] * 1536
        assert results[1][0] == [0.2] * 1536
        assert results[2][0] == [0.3] * 1536
        assert all(r[1] == "litellm" for r in results)

    @pytest.mark.asyncio
    async def test_handles_out_of_order_response(self):
        """Test that results are correctly ordered even if response indices differ."""
        mock_client_manager = MagicMock()
        mock_provider = MagicMock()
        mock_provider.api_key = "test-api-key"
        mock_client_manager.get_client = AsyncMock(return_value=mock_provider)

        service = LLMService(client_manager=mock_client_manager)

        mock_response = MagicMock()
        mock_response.data = [
            {"index": 2, "embedding": [0.3] * 1536},
            {"index": 0, "embedding": [0.1] * 1536},
            {"index": 1, "embedding": [0.2] * 1536},
        ]
        mock_response.usage = MagicMock()
        mock_response.usage.total_tokens = 100

        mock_db = AsyncMock()

        with patch(
            "src.llm_config.service.litellm.aembedding", new_callable=AsyncMock
        ) as mock_aembedding:
            mock_aembedding.return_value = mock_response

            results = await service.generate_embeddings_batch(
                db=mock_db,
                texts=["Text 0", "Text 1", "Text 2"],
                community_server_id=uuid4(),
            )

        assert results[0][0] == [0.1] * 1536
        assert results[1][0] == [0.2] * 1536
        assert results[2][0] == [0.3] * 1536

    @pytest.mark.asyncio
    async def test_raises_error_when_no_provider(self):
        """Test that ValueError is raised when no OpenAI configuration found."""
        mock_client_manager = MagicMock()
        mock_client_manager.get_client = AsyncMock(return_value=None)

        service = LLMService(client_manager=mock_client_manager)

        mock_db = AsyncMock()

        with pytest.raises(ValueError, match="No OpenAI configuration found"):
            await service.generate_embeddings_batch(
                db=mock_db,
                texts=["Some text"],
                community_server_id=uuid4(),
            )
