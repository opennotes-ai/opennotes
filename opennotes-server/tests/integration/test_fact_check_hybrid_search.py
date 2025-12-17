"""Integration tests for fact check hybrid search functionality.

Tests the RRF (Reciprocal Rank Fusion) hybrid search that combines:
- Full-text search (FTS) using PostgreSQL tsvector/ts_rank_cd
- Semantic search using pgvector embeddings

The hybrid search uses RRF formula: 1/(k + rank) to combine rankings from
both search methods, where k=60 is the standard RRF constant.
"""

import pytest
from sqlalchemy import select

from src.database import get_session_maker
from src.fact_checking.models import FactCheckItem

pytestmark = pytest.mark.asyncio


def generate_test_embedding(seed: int = 0) -> list[float]:
    """Generate a deterministic test embedding vector (1536 dimensions).

    Uses a simple pattern to create embeddings that have predictable
    similarity relationships for testing.
    """
    import math

    base = [math.sin(i * 0.01 + seed * 0.1) for i in range(1536)]
    norm = math.sqrt(sum(x * x for x in base))
    return [x / norm for x in base]


@pytest.fixture
async def hybrid_search_test_items():
    """Create test FactCheckItem records with both text and embeddings.

    Creates items with specific characteristics:
    - Items with keyword matches in title (weight A)
    - Items with keyword matches in content only (weight B)
    - Items with semantic similarity but no keyword match
    - Items with both keyword and semantic match
    """
    item_ids = []

    async with get_session_maker()() as session:
        item1 = FactCheckItem(
            dataset_name="test",
            dataset_tags=["test", "hybrid-search"],
            title="Did the moon landing really happen?",
            content="NASA landed astronauts on the moon in 1969. This is a verified historical fact.",
            summary="Moon landing verification",
            rating="True",
            embedding=generate_test_embedding(seed=1),
        )
        session.add(item1)

        item2 = FactCheckItem(
            dataset_name="test",
            dataset_tags=["test", "hybrid-search"],
            title="Vaccine efficacy study results",
            content="The moon landing conspiracy theory has been debunked by scientists.",
            summary="Vaccine study fact check",
            rating="Mostly True",
            embedding=generate_test_embedding(seed=2),
        )
        session.add(item2)

        item3 = FactCheckItem(
            dataset_name="test",
            dataset_tags=["test", "hybrid-search"],
            title="Climate change evidence analysis",
            content="Scientific consensus on global warming and environmental impact.",
            summary="Climate fact check",
            rating="True",
            embedding=generate_test_embedding(seed=1),
        )
        session.add(item3)

        item4 = FactCheckItem(
            dataset_name="test",
            dataset_tags=["test", "hybrid-search"],
            title="Unrelated political claim",
            content="This content has nothing to do with space or moon.",
            summary="Political fact check",
            rating="False",
            embedding=generate_test_embedding(seed=10),
        )
        session.add(item4)

        item5 = FactCheckItem(
            dataset_name="test",
            dataset_tags=["test", "hybrid-search"],
            title="Apollo program historical analysis",
            content="The Apollo missions were a series of spaceflight programs conducted by NASA.",
            summary="Apollo program review",
            rating="True",
            embedding=generate_test_embedding(seed=1),
        )
        session.add(item5)

        await session.commit()

        await session.refresh(item1)
        await session.refresh(item2)
        await session.refresh(item3)
        await session.refresh(item4)
        await session.refresh(item5)

        item_ids = [item1.id, item2.id, item3.id, item4.id, item5.id]

        yield {
            "moon_title": item1,
            "moon_content": item2,
            "climate": item3,
            "unrelated": item4,
            "apollo": item5,
        }

    async with get_session_maker()() as session:
        for item_id in item_ids:
            result = await session.execute(select(FactCheckItem).where(FactCheckItem.id == item_id))
            item = result.scalar_one_or_none()
            if item:
                await session.delete(item)
        await session.commit()


class TestHybridSearchRepository:
    """Tests for the hybrid_search repository method."""

    async def test_hybrid_search_returns_keyword_matches(self, hybrid_search_test_items):
        """Test that keyword-only queries return text matches.

        When searching for 'moon landing', items with this phrase in title
        or content should be returned, ranked by text relevance.
        """
        from src.fact_checking.repository import hybrid_search

        query_text = "moon landing"
        query_embedding = generate_test_embedding(seed=99)

        async with get_session_maker()() as session:
            results = await hybrid_search(
                session=session,
                query_text=query_text,
                query_embedding=query_embedding,
                limit=10,
            )

        assert len(results) >= 1, "Should find at least one keyword match"

        result_titles = [r.item.title for r in results]
        assert any("moon" in title.lower() for title in result_titles), (
            "Results should include items with 'moon' in title or content"
        )

    async def test_hybrid_search_returns_semantic_matches(self, hybrid_search_test_items):
        """Test that semantic queries return vector-similar results.

        When searching with an embedding similar to certain items but with
        non-matching keywords, semantic matches should still be returned.
        """
        from src.fact_checking.repository import hybrid_search

        query_text = "completely different unrelated terms xyz123"
        query_embedding = generate_test_embedding(seed=1)

        async with get_session_maker()() as session:
            results = await hybrid_search(
                session=session,
                query_text=query_text,
                query_embedding=query_embedding,
                limit=10,
            )

        assert len(results) >= 1, "Should find semantic matches even without keyword matches"

    async def test_hybrid_search_combines_rankings_with_rrf(self, hybrid_search_test_items):
        """Test that RRF correctly combines keyword and semantic rankings.

        Items that match both keyword and semantic criteria should rank
        higher than items that only match one criterion.
        """
        from src.fact_checking.repository import hybrid_search

        query_text = "moon landing"
        query_embedding = generate_test_embedding(seed=1)

        async with get_session_maker()() as session:
            results = await hybrid_search(
                session=session,
                query_text=query_text,
                query_embedding=query_embedding,
                limit=10,
            )

        assert len(results) >= 1, "Should return combined results"

        top_result = results[0]
        assert (
            "moon" in top_result.item.title.lower() or "moon" in top_result.item.content.lower()
        ), "Top result should have strong keyword relevance"

    async def test_hybrid_search_title_ranks_higher_than_content(self, hybrid_search_test_items):
        """Test title matches (weight A) rank higher than content matches (weight B).

        When the same keyword appears in title vs content, the title match
        should receive higher ranking due to tsvector weight configuration.
        """
        from src.fact_checking.repository import hybrid_search

        query_text = "moon"
        query_embedding = generate_test_embedding(seed=99)

        async with get_session_maker()() as session:
            results = await hybrid_search(
                session=session,
                query_text=query_text,
                query_embedding=query_embedding,
                limit=10,
            )

        if len(results) >= 2:
            title_match_indices = [
                i for i, r in enumerate(results) if "moon" in r.item.title.lower()
            ]
            content_only_match_indices = [
                i
                for i, r in enumerate(results)
                if "moon" not in r.item.title.lower() and "moon" in r.item.content.lower()
            ]

            if title_match_indices and content_only_match_indices:
                assert min(title_match_indices) < max(content_only_match_indices), (
                    "Title matches should generally rank higher than content-only matches"
                )

    async def test_hybrid_search_empty_results(self):
        """Test empty results when no matches found."""
        from src.fact_checking.repository import hybrid_search

        query_text = "xyznonexistentterm123456"
        query_embedding = generate_test_embedding(seed=999)

        async with get_session_maker()() as session:
            results = await hybrid_search(
                session=session,
                query_text=query_text,
                query_embedding=query_embedding,
                limit=10,
            )

        assert len(results) == 0, "Should return empty list when no matches"

    async def test_hybrid_search_respects_limit(self, hybrid_search_test_items):
        """Test limit parameter is respected."""
        from src.fact_checking.repository import hybrid_search

        query_text = "fact check"
        query_embedding = generate_test_embedding(seed=1)

        async with get_session_maker()() as session:
            results = await hybrid_search(
                session=session,
                query_text=query_text,
                query_embedding=query_embedding,
                limit=2,
            )

        assert len(results) <= 2, "Should respect the limit parameter"

    async def test_hybrid_search_returns_fact_check_items(self, hybrid_search_test_items):
        """Test that results are proper HybridSearchResult objects containing FactCheckItem."""
        from src.fact_checking.repository import hybrid_search

        query_text = "moon"
        query_embedding = generate_test_embedding(seed=1)

        async with get_session_maker()() as session:
            results = await hybrid_search(
                session=session,
                query_text=query_text,
                query_embedding=query_embedding,
                limit=5,
            )

        if len(results) > 0:
            result = results[0]
            assert hasattr(result, "item"), "Result should have item (FactCheckItem)"
            assert hasattr(result, "rrf_score"), "Result should have rrf_score"
            assert hasattr(result.item, "id"), "FactCheckItem should have id"
            assert hasattr(result.item, "title"), "FactCheckItem should have title"
            assert hasattr(result.item, "content"), "FactCheckItem should have content"
            assert hasattr(result.item, "dataset_name"), "FactCheckItem should have dataset_name"
            assert hasattr(result.item, "rating"), "FactCheckItem should have rating"
            assert float(result.rrf_score) >= 0.0, "rrf_score should be non-negative"

    async def test_hybrid_search_with_default_limit(self, hybrid_search_test_items):
        """Test that default limit of 10 is applied when not specified."""
        from src.fact_checking.repository import hybrid_search

        query_text = "fact"
        query_embedding = generate_test_embedding(seed=1)

        async with get_session_maker()() as session:
            results = await hybrid_search(
                session=session,
                query_text=query_text,
                query_embedding=query_embedding,
            )

        assert len(results) <= 10, "Default limit should be 10"


@pytest.fixture
async def dataset_tags_test_items():
    """Create test FactCheckItem records with different dataset_tags.

    Creates items with specific tags for testing SQL-level filtering:
    - Items with 'snopes' tag
    - Items with 'politifact' tag
    - Items with 'reuters' tag
    - Items with multiple tags
    """
    item_ids = []

    async with get_session_maker()() as session:
        item_snopes = FactCheckItem(
            dataset_name="snopes",
            dataset_tags=["snopes", "health"],
            title="COVID vaccine safety fact check",
            content="Fact checking claims about COVID vaccine safety and efficacy.",
            summary="Vaccine safety verification",
            rating="True",
            embedding=generate_test_embedding(seed=1),
        )
        session.add(item_snopes)

        item_politifact = FactCheckItem(
            dataset_name="politifact",
            dataset_tags=["politifact", "politics"],
            title="Political claim about vaccines",
            content="Fact checking political statements about vaccine mandates.",
            summary="Political vaccine claim check",
            rating="Mostly True",
            embedding=generate_test_embedding(seed=2),
        )
        session.add(item_politifact)

        item_reuters = FactCheckItem(
            dataset_name="reuters",
            dataset_tags=["reuters", "health"],
            title="Reuters health vaccine report",
            content="Reuters fact check on vaccine distribution claims.",
            summary="Reuters vaccine report",
            rating="True",
            embedding=generate_test_embedding(seed=3),
        )
        session.add(item_reuters)

        item_multi_tags = FactCheckItem(
            dataset_name="combined",
            dataset_tags=["snopes", "politifact", "health"],
            title="Combined source vaccine analysis",
            content="Cross-referenced vaccine fact check from multiple sources.",
            summary="Multi-source vaccine check",
            rating="True",
            embedding=generate_test_embedding(seed=1),
        )
        session.add(item_multi_tags)

        item_other = FactCheckItem(
            dataset_name="other",
            dataset_tags=["other", "climate"],
            title="Climate change fact check",
            content="Unrelated content about climate change for negative test.",
            summary="Climate check",
            rating="True",
            embedding=generate_test_embedding(seed=10),
        )
        session.add(item_other)

        await session.commit()

        await session.refresh(item_snopes)
        await session.refresh(item_politifact)
        await session.refresh(item_reuters)
        await session.refresh(item_multi_tags)
        await session.refresh(item_other)

        item_ids = [
            item_snopes.id,
            item_politifact.id,
            item_reuters.id,
            item_multi_tags.id,
            item_other.id,
        ]

        yield {
            "snopes": item_snopes,
            "politifact": item_politifact,
            "reuters": item_reuters,
            "multi_tags": item_multi_tags,
            "other": item_other,
        }

    async with get_session_maker()() as session:
        for item_id in item_ids:
            result = await session.execute(select(FactCheckItem).where(FactCheckItem.id == item_id))
            item = result.scalar_one_or_none()
            if item:
                await session.delete(item)
        await session.commit()


class TestHybridSearchDatasetTagsFiltering:
    """Tests for dataset_tags filtering in hybrid_search at the SQL level."""

    async def test_hybrid_search_filters_by_single_dataset_tag(self, dataset_tags_test_items):
        """Test that hybrid_search filters results by a single dataset_tag at the SQL level.

        When searching with dataset_tags=['snopes'], only items that have 'snopes'
        in their dataset_tags array should be returned.
        """
        from src.fact_checking.repository import hybrid_search

        query_text = "vaccine"
        query_embedding = generate_test_embedding(seed=1)

        async with get_session_maker()() as session:
            results = await hybrid_search(
                session=session,
                query_text=query_text,
                query_embedding=query_embedding,
                dataset_tags=["snopes"],
                limit=10,
            )

        assert len(results) >= 1, "Should find at least one result with 'snopes' tag"

        for result in results:
            assert "snopes" in result.item.dataset_tags, (
                f"All results should have 'snopes' tag, but got: {result.item.dataset_tags}"
            )

    async def test_hybrid_search_filters_by_multiple_dataset_tags(self, dataset_tags_test_items):
        """Test that hybrid_search returns items matching ANY of the provided tags.

        When searching with dataset_tags=['snopes', 'politifact'], items with either
        tag should be returned (array overlap behavior).
        """
        from src.fact_checking.repository import hybrid_search

        query_text = "vaccine"
        query_embedding = generate_test_embedding(seed=1)

        async with get_session_maker()() as session:
            results = await hybrid_search(
                session=session,
                query_text=query_text,
                query_embedding=query_embedding,
                dataset_tags=["snopes", "politifact"],
                limit=10,
            )

        assert len(results) >= 2, "Should find results from both snopes and politifact"

        for result in results:
            has_snopes = "snopes" in result.item.dataset_tags
            has_politifact = "politifact" in result.item.dataset_tags
            assert has_snopes or has_politifact, (
                f"All results should have 'snopes' or 'politifact' tag, but got: {result.item.dataset_tags}"
            )

    async def test_hybrid_search_excludes_non_matching_tags(self, dataset_tags_test_items):
        """Test that items with non-matching tags are excluded.

        When searching with dataset_tags=['snopes'], items with only 'reuters'
        or 'other' tags should NOT be returned.
        """
        from src.fact_checking.repository import hybrid_search

        query_text = "fact check"
        query_embedding = generate_test_embedding(seed=1)

        async with get_session_maker()() as session:
            results = await hybrid_search(
                session=session,
                query_text=query_text,
                query_embedding=query_embedding,
                dataset_tags=["snopes"],
                limit=10,
            )

        result_dataset_names = [r.item.dataset_name for r in results]

        assert "reuters" not in result_dataset_names or any(
            "snopes" in r.item.dataset_tags for r in results if r.item.dataset_name == "reuters"
        ), "Reuters-only items should be excluded"

        assert "other" not in result_dataset_names, "Items with only 'other' tag should be excluded"

    async def test_hybrid_search_without_dataset_tags_returns_all(self, dataset_tags_test_items):
        """Test backward compatibility - no dataset_tags returns all results.

        When dataset_tags is None or not provided, all items should be considered
        (no filtering applied).
        """
        from src.fact_checking.repository import hybrid_search

        query_text = "vaccine"
        query_embedding = generate_test_embedding(seed=1)

        async with get_session_maker()() as session:
            results = await hybrid_search(
                session=session,
                query_text=query_text,
                query_embedding=query_embedding,
                limit=10,
            )

        result_dataset_names = {r.item.dataset_name for r in results}
        assert len(result_dataset_names) >= 2, (
            "Without dataset_tags filter, should return items from multiple datasets"
        )

    async def test_hybrid_search_empty_dataset_tags_returns_all(self, dataset_tags_test_items):
        """Test that empty dataset_tags list returns all results (no filtering)."""
        from src.fact_checking.repository import hybrid_search

        query_text = "vaccine"
        query_embedding = generate_test_embedding(seed=1)

        async with get_session_maker()() as session:
            results_empty = await hybrid_search(
                session=session,
                query_text=query_text,
                query_embedding=query_embedding,
                dataset_tags=[],
                limit=10,
            )

            results_none = await hybrid_search(
                session=session,
                query_text=query_text,
                query_embedding=query_embedding,
                dataset_tags=None,
                limit=10,
            )

        assert len(results_empty) == len(results_none), (
            "Empty list and None should behave the same (no filtering)"
        )


class TestHybridSearchPreFilterConstant:
    """Tests for the RRF CTE pre-filter limit constant."""

    def test_rrf_cte_prelimit_constant_exists(self):
        """Test that RRF_CTE_PRELIMIT constant is defined and exported."""
        from src.fact_checking.repository import RRF_CTE_PRELIMIT

        assert RRF_CTE_PRELIMIT == 20, (
            "RRF_CTE_PRELIMIT should be 20 (each CTE fetches 20 candidates)"
        )

    def test_rrf_cte_prelimit_is_positive_integer(self):
        """Test that RRF_CTE_PRELIMIT is a valid positive integer."""
        from src.fact_checking.repository import RRF_CTE_PRELIMIT

        assert isinstance(RRF_CTE_PRELIMIT, int), "RRF_CTE_PRELIMIT should be an integer"
        assert RRF_CTE_PRELIMIT > 0, "RRF_CTE_PRELIMIT should be positive"

    async def test_hybrid_search_max_results_bounded_by_prelimit(self, hybrid_search_test_items):
        """Test that hybrid search is bounded by CTE pre-filter limit.

        Each CTE (semantic and keyword) fetches RRF_CTE_PRELIMIT results.
        After RRF fusion, maximum unique results = 2 * RRF_CTE_PRELIMIT.
        When limit exceeds this, we still only get fused candidates.
        """
        from src.fact_checking.repository import RRF_CTE_PRELIMIT, hybrid_search

        query_text = "fact check"
        query_embedding = generate_test_embedding(seed=1)

        async with get_session_maker()() as session:
            results = await hybrid_search(
                session=session,
                query_text=query_text,
                query_embedding=query_embedding,
                limit=100,
            )

        max_possible = 2 * RRF_CTE_PRELIMIT
        assert len(results) <= max_possible, (
            f"Results should be bounded by 2 * RRF_CTE_PRELIMIT ({max_possible}), "
            f"but got {len(results)}"
        )


class TestHybridSearchPerformanceMetrics:
    """Tests for performance monitoring metrics in hybrid search."""

    async def test_hybrid_search_logs_query_duration(self, hybrid_search_test_items, caplog):
        """Test that hybrid_search logs query_duration_ms for performance monitoring.

        The log output should include timing information to help identify
        slow queries in production.
        """
        import logging

        from src.fact_checking.repository import hybrid_search

        query_text = "moon landing"
        query_embedding = generate_test_embedding(seed=1)

        with caplog.at_level(logging.INFO, logger="src.fact_checking.repository"):
            async with get_session_maker()() as session:
                await hybrid_search(
                    session=session,
                    query_text=query_text,
                    query_embedding=query_embedding,
                    limit=10,
                )

        log_messages = [record.message for record in caplog.records]

        assert any("Hybrid search completed" in msg for msg in log_messages), (
            "Should log 'Hybrid search completed' message"
        )

        found_duration = False
        for record in caplog.records:
            if hasattr(record, "query_duration_ms"):
                found_duration = True
                duration = record.query_duration_ms
                assert isinstance(duration, (int, float)), "query_duration_ms should be numeric"
                assert duration >= 0, "query_duration_ms should be non-negative"
                break

        assert found_duration, "Hybrid search should log query_duration_ms in extra data"

    async def test_hybrid_search_query_duration_is_reasonable(
        self, hybrid_search_test_items, caplog
    ):
        """Test that query duration is within reasonable bounds.

        Query duration should be positive and less than 30 seconds
        (our timeout threshold) for normal operations.
        """
        import logging

        from src.fact_checking.repository import hybrid_search

        query_text = "vaccine"
        query_embedding = generate_test_embedding(seed=1)

        with caplog.at_level(logging.INFO, logger="src.fact_checking.repository"):
            async with get_session_maker()() as session:
                await hybrid_search(
                    session=session,
                    query_text=query_text,
                    query_embedding=query_embedding,
                    limit=5,
                )

        for record in caplog.records:
            if hasattr(record, "query_duration_ms"):
                duration = record.query_duration_ms
                assert 0 < duration < 30000, (
                    f"Query duration should be positive and < 30s, got {duration}ms"
                )
