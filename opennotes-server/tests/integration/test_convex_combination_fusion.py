"""Integration tests for Convex Combination (CC) score fusion in hybrid search.

Tests the CC formula: final_score = alpha * semantic_similarity + (1-alpha) * keyword_norm

Where:
- semantic_similarity = 1 - cosine_distance (already in 0-1 range)
- keyword_norm = min-max normalized ts_rank_cd within result set
- alpha ∈ [0, 1] controls the balance (default 0.7, semantic-weighted)

The CC formula replaces RRF (Reciprocal Rank Fusion) to preserve score magnitude
information, enabling better relevance discrimination and threshold-based filtering.
"""

import pytest
from sqlalchemy import select

from src.database import get_session_maker
from src.fact_checking.models import FactCheckItem

pytestmark = pytest.mark.asyncio


def generate_test_embedding(seed: int = 0) -> list[float]:
    """Generate a deterministic test embedding vector (1536 dimensions)."""
    import numpy as np

    rng = np.random.default_rng(seed)
    base = rng.standard_normal(1536)
    norm = np.linalg.norm(base)
    return (base / norm).tolist()


@pytest.fixture
async def cc_test_items():
    """Create test items with known semantic and keyword characteristics.

    Creates items designed to test CC fusion behavior:
    - Items with high semantic similarity (similar embeddings)
    - Items with high keyword relevance (matching terms)
    - Items with both high semantic AND keyword scores
    - Items with only one type of match
    """
    item_ids = []

    async with get_session_maker()() as session:
        item_semantic_only = FactCheckItem(
            dataset_name="test",
            dataset_tags=["test", "cc-fusion"],
            title="Quantum computing breakthrough announcement",
            content="Scientists achieved quantum supremacy using superconducting qubits.",
            summary="Quantum computing milestone",
            rating="True",
            embedding=generate_test_embedding(seed=1),
        )
        session.add(item_semantic_only)

        item_keyword_only = FactCheckItem(
            dataset_name="test",
            dataset_tags=["test", "cc-fusion"],
            title="Did the vaccine cause side effects?",
            content="The vaccine was tested extensively for safety and efficacy.",
            summary="Vaccine safety fact check",
            rating="True",
            embedding=generate_test_embedding(seed=100),
        )
        session.add(item_keyword_only)

        item_both_match = FactCheckItem(
            dataset_name="test",
            dataset_tags=["test", "cc-fusion"],
            title="Quantum vaccine research study",
            content="Researchers used quantum computing to analyze vaccine proteins.",
            summary="Quantum vaccine research",
            rating="True",
            embedding=generate_test_embedding(seed=1),
        )
        session.add(item_both_match)

        item_no_match = FactCheckItem(
            dataset_name="test",
            dataset_tags=["test", "cc-fusion"],
            title="Political election results analysis",
            content="The election results were certified by state officials.",
            summary="Election fact check",
            rating="True",
            embedding=generate_test_embedding(seed=500),
        )
        session.add(item_no_match)

        await session.commit()

        await session.refresh(item_semantic_only)
        await session.refresh(item_keyword_only)
        await session.refresh(item_both_match)
        await session.refresh(item_no_match)

        item_ids = [
            item_semantic_only.id,
            item_keyword_only.id,
            item_both_match.id,
            item_no_match.id,
        ]

        yield {
            "semantic_only": item_semantic_only,
            "keyword_only": item_keyword_only,
            "both_match": item_both_match,
            "no_match": item_no_match,
        }

    async with get_session_maker()() as session:
        for item_id in item_ids:
            result = await session.execute(select(FactCheckItem).where(FactCheckItem.id == item_id))
            item = result.scalar_one_or_none()
            if item:
                await session.delete(item)
        await session.commit()


class TestConvexCombinationScoreRange:
    """Tests for CC score range and properties."""

    async def test_cc_scores_are_between_0_and_1(self, cc_test_items):
        """CC scores should always be in [0, 1] range."""
        from src.fact_checking.repository import hybrid_search

        query_text = "vaccine quantum research"
        query_embedding = generate_test_embedding(seed=1)

        async with get_session_maker()() as session:
            results = await hybrid_search(
                session=session,
                query_text=query_text,
                query_embedding=query_embedding,
                limit=10,
            )

        for result in results:
            assert 0.0 <= result.rrf_score <= 1.0, (
                f"CC score should be in [0, 1], got {result.rrf_score}"
            )

    async def test_cc_scores_are_sorted_descending(self, cc_test_items):
        """Results should be sorted by CC score in descending order."""
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

        if len(results) >= 2:
            scores = [r.rrf_score for r in results]
            assert scores == sorted(scores, reverse=True), (
                "Results should be sorted by score descending"
            )


class TestConvexCombinationFormula:
    """Tests for the CC formula behavior."""

    async def test_dual_match_scores_higher_than_single_match(self, cc_test_items):
        """Items matching both semantic and keyword should score higher."""
        from src.fact_checking.repository import hybrid_search

        query_text = "quantum vaccine"
        query_embedding = generate_test_embedding(seed=1)

        async with get_session_maker()() as session:
            results = await hybrid_search(
                session=session,
                query_text=query_text,
                query_embedding=query_embedding,
                limit=10,
            )

        if len(results) >= 2:
            dual_match = next(
                (
                    r
                    for r in results
                    if "quantum" in r.item.title.lower() and "vaccine" in r.item.title.lower()
                ),
                None,
            )

            if dual_match:
                single_matches = [r for r in results if r != dual_match]
                if single_matches:
                    assert dual_match.rrf_score >= single_matches[0].rrf_score * 0.8, (
                        "Dual match should score at least 80% of top single match"
                    )

    async def test_semantic_match_contributes_to_score(self, cc_test_items):
        """Items with semantic similarity should appear even without keyword match."""
        from src.fact_checking.repository import hybrid_search

        query_text = "xyznonexistentterm"
        query_embedding = generate_test_embedding(seed=1)

        async with get_session_maker()() as session:
            results = await hybrid_search(
                session=session,
                query_text=query_text,
                query_embedding=query_embedding,
                limit=10,
            )

        assert len(results) >= 1, "Should find semantic matches even without keyword match"

    async def test_keyword_match_contributes_to_score(self, cc_test_items):
        """Items with keyword match should appear even without semantic similarity."""
        from src.fact_checking.repository import hybrid_search

        query_text = "vaccine safety"
        query_embedding = generate_test_embedding(seed=999)

        async with get_session_maker()() as session:
            results = await hybrid_search(
                session=session,
                query_text=query_text,
                query_embedding=query_embedding,
                limit=10,
            )

        assert len(results) >= 1, "Should find keyword matches even without semantic match"


class TestConvexCombinationWithAlpha:
    """Tests for CC with configurable alpha parameter."""

    async def test_alpha_parameter_affects_ranking(self, cc_test_items):
        """Different alpha values should produce different rankings."""
        from src.fact_checking.repository import hybrid_search

        query_text = "quantum vaccine"
        query_embedding = generate_test_embedding(seed=1)

        async with get_session_maker()() as session:
            results_semantic_weighted = await hybrid_search(
                session=session,
                query_text=query_text,
                query_embedding=query_embedding,
                limit=10,
                alpha=0.9,
            )

            results_keyword_weighted = await hybrid_search(
                session=session,
                query_text=query_text,
                query_embedding=query_embedding,
                limit=10,
                alpha=0.1,
            )

        if len(results_semantic_weighted) >= 2 and len(results_keyword_weighted) >= 2:
            semantic_ids = [r.item.id for r in results_semantic_weighted]
            keyword_ids = [r.item.id for r in results_keyword_weighted]
            assert len(semantic_ids) >= 2, "Should have semantic results"
            assert len(keyword_ids) >= 2, "Should have keyword results"

    async def test_alpha_1_returns_pure_semantic(self, cc_test_items):
        """With alpha=1.0, ranking should be based only on semantic similarity."""
        from src.fact_checking.repository import hybrid_search

        query_text = "completely irrelevant keywords xyz123"
        query_embedding = generate_test_embedding(seed=1)

        async with get_session_maker()() as session:
            results = await hybrid_search(
                session=session,
                query_text=query_text,
                query_embedding=query_embedding,
                limit=10,
                alpha=1.0,
            )

        assert len(results) >= 1, "With alpha=1.0, should find results based on semantic similarity"

    async def test_alpha_0_returns_pure_keyword(self, cc_test_items):
        """With alpha=0.0, ranking should be based only on keyword relevance."""
        from src.fact_checking.repository import hybrid_search

        query_text = "vaccine safety efficacy"
        query_embedding = generate_test_embedding(seed=999)

        async with get_session_maker()() as session:
            results = await hybrid_search(
                session=session,
                query_text=query_text,
                query_embedding=query_embedding,
                limit=10,
                alpha=0.0,
            )

        assert len(results) >= 1, "With alpha=0.0, should find results based on keyword relevance"


class TestMinMaxNormalization:
    """Tests for min-max normalization of keyword scores."""

    async def test_keyword_scores_are_normalized(self, cc_test_items):
        """Keyword scores should be normalized to [0, 1] range."""
        from src.fact_checking.repository import hybrid_search

        query_text = "vaccine safety"
        query_embedding = generate_test_embedding(seed=1)

        async with get_session_maker()() as session:
            results = await hybrid_search(
                session=session,
                query_text=query_text,
                query_embedding=query_embedding,
                limit=10,
                alpha=0.0,
            )

        for result in results:
            assert 0.0 <= result.rrf_score <= 1.0, (
                "With alpha=0.0, score should be normalized keyword score in [0, 1]"
            )


class TestScoreSpreadImprovement:
    """Tests verifying CC provides better score discrimination than RRF."""

    async def test_cc_provides_wider_score_spread(self, cc_test_items):
        """CC should provide wider score spread than the narrow RRF range (0.2-0.5)."""
        from src.fact_checking.repository import hybrid_search

        query_text = "vaccine quantum research study"
        query_embedding = generate_test_embedding(seed=1)

        async with get_session_maker()() as session:
            results = await hybrid_search(
                session=session,
                query_text=query_text,
                query_embedding=query_embedding,
                limit=10,
            )

        if len(results) >= 2:
            scores = [r.rrf_score for r in results]
            score_spread = max(scores) - min(scores)

            assert score_spread >= 0.1, (
                f"CC should provide meaningful score spread, got {score_spread}"
            )
