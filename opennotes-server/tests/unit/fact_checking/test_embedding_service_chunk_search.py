"""Unit tests for EmbeddingService migration to chunk-based hybrid search.

Tests that EmbeddingService.similarity_search uses hybrid_search_with_chunks
instead of the legacy hybrid_search function.

This migration enables:
- Chunk-level search granularity
- TF-IDF-like weight reduction for common content
- Better semantic matching through content chunking
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
class TestEmbeddingServiceUsesChunkSearch:
    """Test that EmbeddingService.similarity_search uses chunk-based search."""

    async def test_similarity_search_calls_hybrid_search_with_chunks(self):
        """Test that similarity_search calls hybrid_search_with_chunks.

        This is the core migration test - EmbeddingService should use the new
        chunk-based search for all similarity searches.
        """
        from src.fact_checking.embedding_service import EmbeddingService

        mock_llm_service = MagicMock()
        service = EmbeddingService(mock_llm_service)

        mock_db = AsyncMock()
        mock_db.execute.return_value.scalar_one_or_none.return_value = "test-uuid"

        mock_embedding = [0.1] * 1536

        with (
            patch.object(
                service, "generate_embedding", return_value=mock_embedding
            ) as mock_gen_embedding,
            patch(
                "src.fact_checking.embedding_service.hybrid_search_with_chunks"
            ) as mock_chunk_search,
        ):
            mock_chunk_search.return_value = []

            await service.similarity_search(
                db=mock_db,
                query_text="test query",
                community_server_id="123456789",
                dataset_tags=["test"],
            )

            mock_gen_embedding.assert_called_once()
            mock_chunk_search.assert_called_once()

    async def test_similarity_search_passes_correct_params_to_chunk_search(self):
        """Test that similarity_search passes correct parameters to hybrid_search_with_chunks."""
        from src.fact_checking.embedding_service import EmbeddingService

        mock_llm_service = MagicMock()
        service = EmbeddingService(mock_llm_service)

        mock_db = AsyncMock()
        mock_db.execute.return_value.scalar_one_or_none.return_value = "test-uuid"

        mock_embedding = [0.1] * 1536
        test_query = "test query about vaccines"
        test_tags = ["snopes", "health"]
        test_threshold = 0.7
        test_limit = 10

        with (
            patch.object(service, "generate_embedding", return_value=mock_embedding),
            patch(
                "src.fact_checking.embedding_service.hybrid_search_with_chunks"
            ) as mock_chunk_search,
        ):
            mock_chunk_search.return_value = []

            await service.similarity_search(
                db=mock_db,
                query_text=test_query,
                community_server_id="123456789",
                dataset_tags=test_tags,
                similarity_threshold=test_threshold,
                limit=test_limit,
            )

            mock_chunk_search.assert_called_once()
            call_kwargs = mock_chunk_search.call_args.kwargs

            assert call_kwargs["session"] == mock_db
            assert call_kwargs["query_text"] == test_query
            assert call_kwargs["query_embedding"] == mock_embedding
            assert call_kwargs["limit"] == test_limit
            assert call_kwargs["dataset_tags"] == test_tags
            assert call_kwargs["semantic_similarity_threshold"] == test_threshold


class TestEmbeddingServiceChunkSearchImport:
    """Test that hybrid_search_with_chunks is properly imported."""

    def test_hybrid_search_with_chunks_is_imported(self):
        """Test that hybrid_search_with_chunks is imported in embedding_service."""
        from src.fact_checking import embedding_service

        assert hasattr(embedding_service, "hybrid_search_with_chunks"), (
            "embedding_service should import hybrid_search_with_chunks from repository"
        )
