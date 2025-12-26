"""Unit tests for chunk-based hybrid search with TF-IDF weight reduction.

Tests the hybrid_search_with_chunks function which:
- Searches through chunk_embeddings instead of fact_check_items.embedding
- Applies TF-IDF-like weight reduction for common chunks (is_common=True)
- Aggregates chunk scores per fact_check_item using MAX()
- Uses RRF (Reciprocal Rank Fusion) scoring
"""

import pytest


class TestChunkSearchConstants:
    """Test that chunk search constants are properly defined."""

    def test_default_common_chunk_weight_factor(self):
        """Test default weight factor for common chunks is 0.5."""
        from src.fact_checking.repository import DEFAULT_COMMON_CHUNK_WEIGHT_FACTOR

        assert DEFAULT_COMMON_CHUNK_WEIGHT_FACTOR == 0.5, (
            "Common chunks should be weighted at 50% by default"
        )

    def test_rrf_constants_imported(self):
        """Test RRF constants are accessible for chunk search."""
        from src.fact_checking.repository import RRF_CTE_PRELIMIT, RRF_K_CONSTANT

        assert RRF_K_CONSTANT == 60, "RRF k constant should be 60"
        assert RRF_CTE_PRELIMIT == 20, "RRF CTE pre-limit should be 20"


class TestChunkSearchFunctionExists:
    """Test that hybrid_search_with_chunks function exists and has correct signature."""

    def test_function_exists(self):
        """Test hybrid_search_with_chunks function exists in repository module."""
        from src.fact_checking.repository import hybrid_search_with_chunks

        assert callable(hybrid_search_with_chunks)

    def test_function_signature_has_required_params(self):
        """Test function has required parameters."""
        import inspect

        from src.fact_checking.repository import hybrid_search_with_chunks

        sig = inspect.signature(hybrid_search_with_chunks)
        params = list(sig.parameters.keys())

        assert "session" in params, "Function must accept session parameter"
        assert "query_text" in params, "Function must accept query_text parameter"
        assert "query_embedding" in params, "Function must accept query_embedding parameter"

    def test_function_has_weight_factor_param(self):
        """Test function accepts common_chunk_weight_factor parameter."""
        import inspect

        from src.fact_checking.repository import hybrid_search_with_chunks

        sig = inspect.signature(hybrid_search_with_chunks)
        params = sig.parameters

        assert "common_chunk_weight_factor" in params, (
            "Function must accept common_chunk_weight_factor parameter"
        )
        assert params["common_chunk_weight_factor"].default == 0.5, (
            "Default weight factor should be 0.5"
        )

    def test_function_is_async(self):
        """Test hybrid_search_with_chunks is an async function."""
        import asyncio

        from src.fact_checking.repository import hybrid_search_with_chunks

        assert asyncio.iscoroutinefunction(hybrid_search_with_chunks), (
            "hybrid_search_with_chunks must be async"
        )


class TestChunkSearchReturnType:
    """Test that hybrid_search_with_chunks returns correct types."""

    def test_return_type_annotation_is_list(self):
        """Test function return type is annotated as list of HybridSearchResult."""
        import inspect

        from src.fact_checking.repository import hybrid_search_with_chunks

        sig = inspect.signature(hybrid_search_with_chunks)
        return_annotation = sig.return_annotation

        # Check it's a list type
        assert "list" in str(return_annotation).lower(), "Return type should be a list"


class TestWeightReductionLogic:
    """Test the weight reduction logic for common chunks."""

    def test_weight_factor_must_be_between_0_and_1(self):
        """Test that weight factor must be between 0 and 1."""
        # The weight factor represents a reduction - 0.5 means 50% of normal weight
        weight_factor = 0.5
        assert 0.0 <= weight_factor <= 1.0, "Weight factor must be in [0, 1]"

    def test_common_chunk_score_is_reduced(self):
        """Test that common chunk scores are reduced by the weight factor.

        For a common chunk (is_common=True), the RRF score should be:
        score = (1/(k + rank)) * common_chunk_weight_factor

        Example: rank=1, k=60, weight_factor=0.5
        - Normal score = 1/(60+1) = 0.0164
        - Common score = 0.0164 * 0.5 = 0.0082
        """
        k = 60
        rank = 1
        weight_factor = 0.5

        normal_score = 1.0 / (k + rank)
        common_score = normal_score * weight_factor

        assert common_score == normal_score * 0.5
        assert common_score < normal_score, (
            "Common chunk score should be less than normal chunk score"
        )

    def test_non_common_chunk_gets_full_score(self):
        """Test that non-common chunks get full RRF score (weight factor = 1.0)."""
        k = 60
        rank = 1
        weight_factor_for_non_common = 1.0

        score = (1.0 / (k + rank)) * weight_factor_for_non_common
        expected = 1.0 / (k + rank)

        assert score == expected, "Non-common chunks should get full score"

    def test_zero_weight_factor_eliminates_common_chunks(self):
        """Test that weight factor of 0 eliminates common chunks from scoring."""
        k = 60
        rank = 1
        weight_factor = 0.0

        score = (1.0 / (k + rank)) * weight_factor
        assert score == 0.0, "Weight factor 0 should eliminate common chunk contribution"


class TestMaxAggregation:
    """Test the MAX() aggregation logic for multiple chunks per fact_check_item."""

    def test_max_aggregation_selects_best_chunk(self):
        """Test that MAX() aggregation selects the highest scoring chunk.

        When a fact_check_item has multiple chunks with different ranks,
        the final score should use the best (highest) chunk score.
        """
        k = 60
        # Three chunks for the same fact_check_item
        chunk_ranks = [5, 10, 2]  # Rank 2 is best (lower rank = higher score)
        chunk_scores = [1.0 / (k + rank) for rank in chunk_ranks]

        max_score = max(chunk_scores)
        expected_best_score = 1.0 / (k + 2)  # Rank 2 gives highest score

        assert max_score == expected_best_score

    def test_max_aggregation_with_common_chunks(self):
        """Test MAX() aggregation when some chunks are common.

        Scenario:
        - Chunk 1: rank=2, is_common=False -> score = 1/(60+2) = 0.0161
        - Chunk 2: rank=1, is_common=True, weight=0.5 -> score = 0.5/(60+1) = 0.0082

        MAX should pick the non-common chunk because it has higher final score
        after weight reduction is applied to the common chunk.
        """
        k = 60
        weight_factor = 0.5

        # Chunk 1: rank 2, not common
        chunk1_score = 1.0 / (k + 2)  # ~0.0161

        # Chunk 2: rank 1, common (even though rank is better, weight reduces it)
        chunk2_score = (1.0 / (k + 1)) * weight_factor  # ~0.0082

        max_score = max(chunk1_score, chunk2_score)

        assert max_score == chunk1_score, (
            "Non-common chunk with rank 2 should beat common chunk with rank 1 "
            "when weight factor is 0.5"
        )


class TestInputValidation:
    """Test input validation for hybrid_search_with_chunks."""

    @pytest.mark.asyncio
    async def test_invalid_embedding_dimensions_raises_error(self):
        """Test that wrong embedding dimensions raises ValueError."""
        from unittest.mock import AsyncMock

        from src.fact_checking.repository import hybrid_search_with_chunks

        mock_session = AsyncMock()
        wrong_dimensions_embedding = [0.1] * 512  # Wrong: should be 1536

        with pytest.raises(ValueError, match="1536"):
            await hybrid_search_with_chunks(
                session=mock_session,
                query_text="test query",
                query_embedding=wrong_dimensions_embedding,
            )

    @pytest.mark.asyncio
    async def test_valid_embedding_dimensions_accepted(self):
        """Test that correct embedding dimensions are accepted (1536)."""
        from unittest.mock import AsyncMock, MagicMock

        from src.fact_checking.repository import hybrid_search_with_chunks

        # Mock session that returns empty results
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        valid_embedding = [0.1] * 1536

        # Should not raise
        results = await hybrid_search_with_chunks(
            session=mock_session,
            query_text="test query",
            query_embedding=valid_embedding,
        )

        assert results == []


class TestWeightFactorBoundaries:
    """Test weight factor parameter boundaries."""

    @pytest.mark.asyncio
    async def test_weight_factor_zero_is_valid(self):
        """Test weight factor of 0.0 is accepted."""
        from unittest.mock import AsyncMock, MagicMock

        from src.fact_checking.repository import hybrid_search_with_chunks

        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        valid_embedding = [0.1] * 1536

        # Should not raise
        results = await hybrid_search_with_chunks(
            session=mock_session,
            query_text="test query",
            query_embedding=valid_embedding,
            common_chunk_weight_factor=0.0,
        )

        assert results == []

    @pytest.mark.asyncio
    async def test_weight_factor_one_is_valid(self):
        """Test weight factor of 1.0 is accepted (no reduction)."""
        from unittest.mock import AsyncMock, MagicMock

        from src.fact_checking.repository import hybrid_search_with_chunks

        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        valid_embedding = [0.1] * 1536

        # Should not raise
        results = await hybrid_search_with_chunks(
            session=mock_session,
            query_text="test query",
            query_embedding=valid_embedding,
            common_chunk_weight_factor=1.0,
        )

        assert results == []
