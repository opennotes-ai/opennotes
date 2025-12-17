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
