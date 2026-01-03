"""
Unit tests for EmbeddingService OpenTelemetry tracing.

Task: task-908 - Improve EmbeddingService tracing and test coverage (PR #48 follow-up)
AC#3: Add unit tests verifying OpenTelemetry spans are created with correct attributes
AC#4: Add test case with mock results to verify FactCheckMatch construction
AC#5: Add test for empty results handling through tracing spans
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.fact_checking.embedding_schemas import FactCheckMatch


class TestEmbeddingServiceSpanAttributes:
    """Test OpenTelemetry span attributes in EmbeddingService."""

    @pytest.mark.asyncio
    async def test_generate_embedding_creates_span_with_correct_attributes(self):
        """Verify generate_embedding creates span with text_length and community_server_id."""
        mock_span = MagicMock()
        mock_span.__enter__ = MagicMock(return_value=mock_span)
        mock_span.__exit__ = MagicMock(return_value=None)

        mock_tracer = MagicMock()
        mock_tracer.start_as_current_span.return_value = mock_span

        with patch("src.fact_checking.embedding_service._tracer", mock_tracer):
            from src.fact_checking.embedding_service import EmbeddingService

            mock_llm_service = MagicMock()
            mock_llm_service.generate_embedding = AsyncMock(
                return_value=([0.1] * 1536, "openai", "text-embedding-3-small")
            )
            service = EmbeddingService(mock_llm_service)

            mock_db = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = uuid4()
            mock_db.execute = AsyncMock(return_value=mock_result)

            await service.generate_embedding(mock_db, "test text", "123456789")

            mock_tracer.start_as_current_span.assert_called_once_with("embedding.generate")

            set_attribute_calls = {
                call[0][0]: call[0][1] for call in mock_span.set_attribute.call_args_list
            }
            assert set_attribute_calls["embedding.text_length"] == 9
            assert set_attribute_calls["embedding.community_server_id"] == "123456789"
            assert "embedding.cache_hit" in set_attribute_calls

    @pytest.mark.asyncio
    async def test_generate_embedding_records_exception_on_error(self):
        """Verify generate_embedding records exception on span when error occurs."""
        from opentelemetry.trace import StatusCode

        mock_span = MagicMock()
        mock_span.__enter__ = MagicMock(return_value=mock_span)
        mock_span.__exit__ = MagicMock(return_value=None)

        mock_tracer = MagicMock()
        mock_tracer.start_as_current_span.return_value = mock_span

        with patch("src.fact_checking.embedding_service._tracer", mock_tracer):
            from src.fact_checking.embedding_service import EmbeddingService

            mock_llm_service = MagicMock()
            service = EmbeddingService(mock_llm_service)

            mock_db = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_db.execute = AsyncMock(return_value=mock_result)

            with pytest.raises(ValueError, match="Community server not found"):
                await service.generate_embedding(mock_db, "test text", "invalid_id")

            mock_span.record_exception.assert_called_once()
            mock_span.set_status.assert_called_once()
            status_call = mock_span.set_status.call_args
            assert status_call[0][0] == StatusCode.ERROR

    @pytest.mark.asyncio
    async def test_similarity_search_creates_span_with_correct_attributes(self):
        """Verify similarity_search creates span with search-related attributes."""
        mock_span = MagicMock()
        mock_span.__enter__ = MagicMock(return_value=mock_span)
        mock_span.__exit__ = MagicMock(return_value=None)

        mock_tracer = MagicMock()
        mock_tracer.start_as_current_span.return_value = mock_span

        with (
            patch("src.fact_checking.embedding_service._tracer", mock_tracer),
            patch(
                "src.fact_checking.embedding_service.hybrid_search_with_chunks",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            from src.fact_checking.embedding_service import EmbeddingService

            mock_llm_service = MagicMock()
            mock_llm_service.generate_embedding = AsyncMock(
                return_value=([0.1] * 1536, "openai", "text-embedding-3-small")
            )
            service = EmbeddingService(mock_llm_service)

            mock_db = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = uuid4()
            mock_db.execute = AsyncMock(return_value=mock_result)

            await service.similarity_search(
                mock_db,
                query_text="test query",
                community_server_id="123456789",
                dataset_tags=["snopes", "politifact"],
                similarity_threshold=0.7,
                score_threshold=0.15,
                limit=10,
            )

            span_calls = mock_tracer.start_as_current_span.call_args_list
            span_names = [call[0][0] for call in span_calls]
            assert "embedding.similarity_search" in span_names

            set_attribute_calls = {
                call[0][0]: call[0][1] for call in mock_span.set_attribute.call_args_list
            }
            assert set_attribute_calls["search.query_text_length"] == 10
            assert set_attribute_calls["search.community_server_id"] == "123456789"
            assert set_attribute_calls["search.dataset_tags"] == "snopes,politifact"
            assert set_attribute_calls["search.similarity_threshold"] == 0.7
            assert set_attribute_calls["search.score_threshold"] == 0.15
            assert set_attribute_calls["search.limit"] == 10

    @pytest.mark.asyncio
    async def test_similarity_search_records_result_count_on_span(self):
        """Verify similarity_search records result count and top score on span."""
        mock_span = MagicMock()
        mock_span.__enter__ = MagicMock(return_value=mock_span)
        mock_span.__exit__ = MagicMock(return_value=None)

        mock_tracer = MagicMock()
        mock_tracer.start_as_current_span.return_value = mock_span

        mock_item = MagicMock()
        mock_item.id = uuid4()
        mock_item.dataset_name = "snopes"
        mock_item.dataset_tags = ["snopes"]
        mock_item.title = "Test Fact Check"
        mock_item.content = "Test content"
        mock_item.summary = "Test summary"
        mock_item.rating = "false"
        mock_item.source_url = "https://example.com"
        mock_item.published_date = None
        mock_item.author = "Author"
        mock_item.embedding_provider = "openai"
        mock_item.embedding_model = "text-embedding-3-small"

        mock_hybrid_result = MagicMock()
        mock_hybrid_result.item = mock_item
        mock_hybrid_result.cc_score = 0.5

        with (
            patch("src.fact_checking.embedding_service._tracer", mock_tracer),
            patch(
                "src.fact_checking.embedding_service.hybrid_search_with_chunks",
                new_callable=AsyncMock,
                return_value=[mock_hybrid_result],
            ),
        ):
            from src.fact_checking.embedding_service import EmbeddingService

            mock_llm_service = MagicMock()
            mock_llm_service.generate_embedding = AsyncMock(
                return_value=([0.1] * 1536, "openai", "text-embedding-3-small")
            )
            service = EmbeddingService(mock_llm_service)

            mock_db = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = uuid4()
            mock_db.execute = AsyncMock(return_value=mock_result)

            await service.similarity_search(
                mock_db,
                query_text="test query",
                community_server_id="123456789",
                dataset_tags=["snopes"],
            )

            set_attribute_calls = {
                call[0][0]: call[0][1] for call in mock_span.set_attribute.call_args_list
            }
            assert set_attribute_calls["search.result_count"] == 1
            assert set_attribute_calls["search.hybrid_search_count"] == 1
            assert "search.top_score" in set_attribute_calls


class TestFactCheckMatchConstruction:
    """Test FactCheckMatch construction from HybridSearchResult (AC#4)."""

    def test_fact_check_match_construction_with_all_fields(self):
        """Verify FactCheckMatch is correctly constructed with all fields."""
        match = FactCheckMatch(
            id=uuid4(),
            dataset_name="snopes",
            dataset_tags=["snopes", "health"],
            title="Test Claim",
            content="This is the full content of the fact check.",
            summary="Brief summary",
            rating="false",
            source_url="https://snopes.com/test",
            published_date="2024-01-15",
            author="Test Author",
            embedding_provider="openai",
            embedding_model="text-embedding-3-small",
            similarity_score=0.85,
        )

        assert match.dataset_name == "snopes"
        assert match.title == "Test Claim"
        assert match.rating == "false"
        assert match.similarity_score == 0.85
        assert "health" in match.dataset_tags

    def test_fact_check_match_construction_with_minimal_fields(self):
        """Verify FactCheckMatch handles None optional fields."""
        match = FactCheckMatch(
            id=uuid4(),
            dataset_name="politifact",
            dataset_tags=[],
            title="Minimal Claim",
            content="Content only",
            summary=None,
            rating="mostly-true",
            source_url=None,
            published_date=None,
            author=None,
            embedding_provider="openai",
            embedding_model="text-embedding-3-small",
            similarity_score=0.65,
        )

        assert match.summary is None
        assert match.source_url is None
        assert match.author is None

    def test_fact_check_match_similarity_score_scaling(self):
        """Verify similarity score is properly bounded (0.0-1.0)."""
        match_high = FactCheckMatch(
            id=uuid4(),
            dataset_name="test",
            dataset_tags=[],
            title="Test",
            content="Content",
            summary=None,
            rating="true",
            source_url=None,
            published_date=None,
            author=None,
            embedding_provider="openai",
            embedding_model="text-embedding-3-small",
            similarity_score=1.0,
        )
        assert match_high.similarity_score == 1.0

        match_low = FactCheckMatch(
            id=uuid4(),
            dataset_name="test",
            dataset_tags=[],
            title="Test",
            content="Content",
            summary=None,
            rating="true",
            source_url=None,
            published_date=None,
            author=None,
            embedding_provider="openai",
            embedding_model="text-embedding-3-small",
            similarity_score=0.0,
        )
        assert match_low.similarity_score == 0.0


class TestEmptyResultsHandling:
    """Test empty results handling through tracing spans (AC#5)."""

    @pytest.mark.asyncio
    async def test_similarity_search_empty_results_records_zero_count(self):
        """Verify empty results are properly recorded on span."""
        mock_span = MagicMock()
        mock_span.__enter__ = MagicMock(return_value=mock_span)
        mock_span.__exit__ = MagicMock(return_value=None)

        mock_tracer = MagicMock()
        mock_tracer.start_as_current_span.return_value = mock_span

        with (
            patch("src.fact_checking.embedding_service._tracer", mock_tracer),
            patch(
                "src.fact_checking.embedding_service.hybrid_search_with_chunks",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            from src.fact_checking.embedding_service import EmbeddingService

            mock_llm_service = MagicMock()
            mock_llm_service.generate_embedding = AsyncMock(
                return_value=([0.1] * 1536, "openai", "text-embedding-3-small")
            )
            service = EmbeddingService(mock_llm_service)

            mock_db = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = uuid4()
            mock_db.execute = AsyncMock(return_value=mock_result)

            result = await service.similarity_search(
                mock_db,
                query_text="no matches expected",
                community_server_id="123456789",
                dataset_tags=["nonexistent"],
            )

            assert result.total_matches == 0
            assert len(result.matches) == 0

            set_attribute_calls = {
                call[0][0]: call[0][1] for call in mock_span.set_attribute.call_args_list
            }
            assert set_attribute_calls["search.result_count"] == 0
            assert set_attribute_calls["search.hybrid_search_count"] == 0
            assert "search.top_score" not in set_attribute_calls

    @pytest.mark.asyncio
    async def test_similarity_search_results_filtered_by_score_threshold(self):
        """Verify results below score_threshold are filtered out."""
        mock_span = MagicMock()
        mock_span.__enter__ = MagicMock(return_value=mock_span)
        mock_span.__exit__ = MagicMock(return_value=None)

        mock_tracer = MagicMock()
        mock_tracer.start_as_current_span.return_value = mock_span

        mock_item = MagicMock()
        mock_item.id = uuid4()
        mock_item.dataset_name = "snopes"
        mock_item.dataset_tags = []
        mock_item.title = "Low Score Match"
        mock_item.content = "Content"
        mock_item.summary = None
        mock_item.rating = "true"
        mock_item.source_url = None
        mock_item.published_date = None
        mock_item.author = None
        mock_item.embedding_provider = "openai"
        mock_item.embedding_model = "text-embedding-3-small"

        mock_hybrid_result = MagicMock()
        mock_hybrid_result.item = mock_item
        mock_hybrid_result.cc_score = 0.001

        with (
            patch("src.fact_checking.embedding_service._tracer", mock_tracer),
            patch(
                "src.fact_checking.embedding_service.hybrid_search_with_chunks",
                new_callable=AsyncMock,
                return_value=[mock_hybrid_result],
            ),
        ):
            from src.fact_checking.embedding_service import EmbeddingService

            mock_llm_service = MagicMock()
            mock_llm_service.generate_embedding = AsyncMock(
                return_value=([0.1] * 1536, "openai", "text-embedding-3-small")
            )
            service = EmbeddingService(mock_llm_service)

            mock_db = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = uuid4()
            mock_db.execute = AsyncMock(return_value=mock_result)

            result = await service.similarity_search(
                mock_db,
                query_text="test query",
                community_server_id="123456789",
                dataset_tags=["snopes"],
                score_threshold=0.1,
            )

            assert result.total_matches == 0
            assert len(result.matches) == 0

            set_attribute_calls = {
                call[0][0]: call[0][1] for call in mock_span.set_attribute.call_args_list
            }
            assert set_attribute_calls["search.hybrid_search_count"] == 1
            assert set_attribute_calls["search.result_count"] == 0

    @pytest.mark.asyncio
    async def test_similarity_search_records_exception_on_error(self):
        """Verify similarity_search records exception on span when error occurs."""
        from opentelemetry.trace import StatusCode

        mock_span = MagicMock()
        mock_span.__enter__ = MagicMock(return_value=mock_span)
        mock_span.__exit__ = MagicMock(return_value=None)

        mock_tracer = MagicMock()
        mock_tracer.start_as_current_span.return_value = mock_span

        with patch("src.fact_checking.embedding_service._tracer", mock_tracer):
            from src.fact_checking.embedding_service import EmbeddingService

            mock_llm_service = MagicMock()
            service = EmbeddingService(mock_llm_service)

            mock_db = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_db.execute = AsyncMock(return_value=mock_result)

            with pytest.raises(ValueError, match="Community server not found"):
                await service.similarity_search(
                    mock_db,
                    query_text="test",
                    community_server_id="invalid",
                    dataset_tags=[],
                )

            mock_span.record_exception.assert_called()
            status_calls = [
                call
                for call in mock_span.set_status.call_args_list
                if call[0][0] == StatusCode.ERROR
            ]
            assert len(status_calls) > 0
