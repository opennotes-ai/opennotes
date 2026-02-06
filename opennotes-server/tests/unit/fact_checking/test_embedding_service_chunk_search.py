"""Unit tests for EmbeddingService migration to chunk-based hybrid search.

Tests that EmbeddingService.similarity_search uses hybrid_search_with_chunks
instead of the legacy hybrid_search function.

This migration enables:
- Chunk-level search granularity
- TF-IDF-like weight reduction for common content
- Better semantic matching through content chunking
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.fact_checking.repository import HybridSearchResult


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


def _make_mock_fact_check_item():
    from src.fact_checking.models import FactCheckItem

    return FactCheckItem(
        id=uuid4(),
        dataset_name="snopes",
        dataset_tags=["snopes"],
        title="Test fact check",
        content="Test content",
        summary="Test summary",
        rating="False",
        source_url="https://example.com",
        published_date=datetime.now(UTC),
        author="Test Author",
        embedding=None,
        embedding_provider="openai",
        embedding_model="text-embedding-3-small",
        extra_metadata={},
        search_vector=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
class TestFactCheckMatchCosineSimilarity:
    """Test that FactCheckMatch includes both similarity_score (CC) and cosine_similarity."""

    async def test_fact_check_match_has_both_scores(self):
        """FactCheckMatch should have both similarity_score and cosine_similarity fields."""
        from src.fact_checking.embedding_service import CC_SCORE_SCALE_FACTOR, EmbeddingService

        mock_llm_service = MagicMock()
        service = EmbeddingService(mock_llm_service)
        mock_db = AsyncMock()
        mock_embedding = [0.1] * 1536

        item = _make_mock_fact_check_item()
        mock_result = HybridSearchResult(item=item, cc_score=0.35, semantic_score=0.82)

        with (
            patch.object(service, "generate_embedding", return_value=mock_embedding),
            patch(
                "src.fact_checking.embedding_service.hybrid_search_with_chunks",
                return_value=[mock_result],
            ),
        ):
            response = await service.similarity_search(
                db=mock_db,
                query_text="test query",
                community_server_id="123456789",
                dataset_tags=["snopes"],
                score_threshold=0.0,
            )

        assert len(response.matches) == 1
        match = response.matches[0]
        assert match.similarity_score == min(0.35 * CC_SCORE_SCALE_FACTOR, 1.0)
        assert match.cosine_similarity == 0.82

    async def test_cosine_similarity_higher_than_cc_score_for_low_keyword_scenario(self):
        """cosine_similarity should be >= similarity_score when keyword relevance is low."""
        from src.fact_checking.embedding_service import EmbeddingService

        mock_llm_service = MagicMock()
        service = EmbeddingService(mock_llm_service)
        mock_db = AsyncMock()
        mock_embedding = [0.1] * 1536

        item = _make_mock_fact_check_item()
        mock_result = HybridSearchResult(item=item, cc_score=0.24, semantic_score=0.65)

        with (
            patch.object(service, "generate_embedding", return_value=mock_embedding),
            patch(
                "src.fact_checking.embedding_service.hybrid_search_with_chunks",
                return_value=[mock_result],
            ),
        ):
            response = await service.similarity_search(
                db=mock_db,
                query_text="test query",
                community_server_id="123456789",
                dataset_tags=["snopes"],
                score_threshold=0.0,
            )

        assert len(response.matches) == 1
        match = response.matches[0]
        assert match.cosine_similarity >= match.similarity_score

    async def test_hybrid_search_result_default_semantic_score(self):
        """HybridSearchResult should default semantic_score to None."""
        item = _make_mock_fact_check_item()
        result = HybridSearchResult(item=item, cc_score=0.5)
        assert result.semantic_score is None
