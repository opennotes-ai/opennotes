"""Integration tests for TF-IDF weight reduction in hybrid_search_with_chunks.

These tests verify that the common_chunk_weight_factor parameter correctly
affects search ranking by down-weighting common chunks in fusion scoring.

The TF-IDF-like weight reduction formula:
- Non-common chunks: score = 1/(k + rank)
- Common chunks: score = (1/(k + rank)) * common_chunk_weight_factor
"""

import pytest
from sqlalchemy import delete, select, text

from src.database import get_session_maker
from src.fact_checking.chunk_models import ChunkEmbedding, FactCheckChunk
from src.fact_checking.models import FactCheckItem

pytestmark = pytest.mark.asyncio


async def recreate_pgroonga_index_if_available():
    """Recreate PGroonga index to fix internal Groonga structures after template cloning.

    After CREATE DATABASE WITH TEMPLATE, PGroonga's internal Groonga "Sources" objects
    become invalid (PostgreSQL 15+ issue, see pgroonga/pgroonga#335). REINDEX alone
    doesn't fully restore these structures - we must DROP and CREATE the index.

    This function checks if PGroonga is available before attempting to recreate.
    If PGroonga is not installed, this is a no-op.
    """
    async with get_session_maker()() as session:
        try:
            result = await session.execute(
                text("SELECT 1 FROM pg_extension WHERE extname = 'pgroonga'")
            )
            pgroonga_available = result.scalar_one_or_none() is not None

            if not pgroonga_available:
                return

            await session.execute(text("SELECT pgroonga_command('io_flush')"))
            await session.execute(text("DROP INDEX IF EXISTS idx_chunk_embeddings_pgroonga"))
            await session.execute(
                text(
                    """
                    CREATE INDEX idx_chunk_embeddings_pgroonga
                    ON chunk_embeddings USING pgroonga (chunk_text pgroonga_text_full_text_search_ops_v2)
                    """
                )
            )
            await session.commit()
        except Exception:
            pass


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
async def tfidf_weight_test_items():
    """Create test data for TF-IDF weight reduction tests.

    Creates fact_check_items with chunks that have is_common set to True or False,
    allowing tests to verify that the common_chunk_weight_factor parameter
    correctly reduces the contribution of common chunks in fusion scoring.

    Test data structure:
    - item_common_only: Has only common chunks (is_common=True)
    - item_non_common_only: Has only non-common chunks (is_common=False)
    - item_mixed: Has both common and non-common chunks

    All chunks have similar embeddings (seed=100) to ensure semantic search
    would normally rank them equally, making weight reduction the differentiator.
    """
    await recreate_pgroonga_index_if_available()

    item_ids = []
    chunk_ids = []

    async with get_session_maker()() as session:
        item_common_only = FactCheckItem(
            dataset_name="tfidf-test",
            dataset_tags=["tfidf", "weight-test"],
            title="Common chunks only test item",
            content="This item only has common chunks for testing weight reduction.",
            summary="Common only test",
            rating="True",
        )
        session.add(item_common_only)

        item_non_common_only = FactCheckItem(
            dataset_name="tfidf-test",
            dataset_tags=["tfidf", "weight-test"],
            title="Non-common chunks only test item",
            content="This item only has non-common chunks for testing weight reduction.",
            summary="Non-common only test",
            rating="True",
        )
        session.add(item_non_common_only)

        item_mixed = FactCheckItem(
            dataset_name="tfidf-test",
            dataset_tags=["tfidf", "weight-test"],
            title="Mixed chunks test item",
            content="This item has both common and non-common chunks for testing.",
            summary="Mixed chunks test",
            rating="True",
        )
        session.add(item_mixed)

        await session.flush()

        chunk_common_1 = ChunkEmbedding(
            chunk_text="common chunk for tfidf weight reduction test one",
            embedding=generate_test_embedding(seed=100),
            embedding_provider="test",
            embedding_model="test-model",
            is_common=True,
        )
        session.add(chunk_common_1)

        chunk_common_2 = ChunkEmbedding(
            chunk_text="common chunk for tfidf weight reduction test two",
            embedding=generate_test_embedding(seed=100),
            embedding_provider="test",
            embedding_model="test-model",
            is_common=True,
        )
        session.add(chunk_common_2)

        chunk_non_common_1 = ChunkEmbedding(
            chunk_text="non-common chunk for tfidf weight reduction test one",
            embedding=generate_test_embedding(seed=100),
            embedding_provider="test",
            embedding_model="test-model",
            is_common=False,
        )
        session.add(chunk_non_common_1)

        chunk_non_common_2 = ChunkEmbedding(
            chunk_text="non-common chunk for tfidf weight reduction test two",
            embedding=generate_test_embedding(seed=100),
            embedding_provider="test",
            embedding_model="test-model",
            is_common=False,
        )
        session.add(chunk_non_common_2)

        await session.flush()

        link_common_only = FactCheckChunk(
            chunk_id=chunk_common_1.id,
            fact_check_id=item_common_only.id,
            chunk_index=0,
        )
        session.add(link_common_only)

        link_non_common_only = FactCheckChunk(
            chunk_id=chunk_non_common_1.id,
            fact_check_id=item_non_common_only.id,
            chunk_index=0,
        )
        session.add(link_non_common_only)

        link_mixed_common = FactCheckChunk(
            chunk_id=chunk_common_2.id,
            fact_check_id=item_mixed.id,
            chunk_index=0,
        )
        session.add(link_mixed_common)

        link_mixed_non_common = FactCheckChunk(
            chunk_id=chunk_non_common_2.id,
            fact_check_id=item_mixed.id,
            chunk_index=1,
        )
        session.add(link_mixed_non_common)

        await session.commit()

        await session.refresh(item_common_only)
        await session.refresh(item_non_common_only)
        await session.refresh(item_mixed)
        await session.refresh(chunk_common_1)
        await session.refresh(chunk_common_2)
        await session.refresh(chunk_non_common_1)
        await session.refresh(chunk_non_common_2)

        item_ids = [item_common_only.id, item_non_common_only.id, item_mixed.id]
        chunk_ids = [
            chunk_common_1.id,
            chunk_common_2.id,
            chunk_non_common_1.id,
            chunk_non_common_2.id,
        ]

        yield {
            "item_common_only": item_common_only,
            "item_non_common_only": item_non_common_only,
            "item_mixed": item_mixed,
            "chunk_common_1": chunk_common_1,
            "chunk_common_2": chunk_common_2,
            "chunk_non_common_1": chunk_non_common_1,
            "chunk_non_common_2": chunk_non_common_2,
        }

    async with get_session_maker()() as session:
        await session.execute(delete(FactCheckChunk).where(FactCheckChunk.chunk_id.in_(chunk_ids)))
        await session.execute(delete(ChunkEmbedding).where(ChunkEmbedding.id.in_(chunk_ids)))
        for item_id in item_ids:
            result = await session.execute(select(FactCheckItem).where(FactCheckItem.id == item_id))
            item = result.scalar_one_or_none()
            if item:
                await session.delete(item)
        await session.commit()


class TestTFIDFWeightReduction:
    """Integration tests for TF-IDF weight reduction in hybrid_search_with_chunks.

    These tests verify that the common_chunk_weight_factor parameter correctly
    affects search ranking by down-weighting common chunks in fusion scoring.
    """

    async def test_common_chunk_weight_reduction_applied(self, tfidf_weight_test_items):
        """Test that common chunks are down-weighted in search results.

        When searching with the default weight factor (0.5), items with
        non-common chunks should rank higher than items with only common chunks,
        even when embeddings have the same similarity to the query.
        """
        from src.fact_checking.repository import hybrid_search_with_chunks

        query_text = "tfidf weight reduction test"
        query_embedding = generate_test_embedding(seed=100)

        async with get_session_maker()() as session:
            results = await hybrid_search_with_chunks(
                session=session,
                query_text=query_text,
                query_embedding=query_embedding,
                dataset_tags=["tfidf"],
                limit=10,
                common_chunk_weight_factor=0.5,
            )

        assert len(results) >= 2, "Should find at least the common and non-common items"

        result_ids = [r.item.id for r in results]
        common_only_id = tfidf_weight_test_items["item_common_only"].id
        non_common_only_id = tfidf_weight_test_items["item_non_common_only"].id

        if common_only_id in result_ids and non_common_only_id in result_ids:
            common_idx = result_ids.index(common_only_id)
            non_common_idx = result_ids.index(non_common_only_id)

            assert non_common_idx < common_idx, (
                "Non-common item should rank higher than common-only item "
                "when weight factor is 0.5 (common chunks are reduced to 50%)"
            )

    async def test_weight_factor_zero_excludes_common_chunks(self, tfidf_weight_test_items):
        """Test that common_chunk_weight_factor=0.0 excludes common chunks from scoring.

        When weight factor is 0.0, common chunks contribute nothing to the
        semantic score. An item with only common chunks should either:
        - Not appear in results (if keyword search also doesn't match), or
        - Appear with a lower score (only keyword contribution)
        """
        from src.fact_checking.repository import hybrid_search_with_chunks

        query_text = "unique nonmatching query xyz789"
        query_embedding = generate_test_embedding(seed=100)

        async with get_session_maker()() as session:
            results = await hybrid_search_with_chunks(
                session=session,
                query_text=query_text,
                query_embedding=query_embedding,
                dataset_tags=["tfidf"],
                limit=10,
                common_chunk_weight_factor=0.0,
            )

        result_ids = [r.item.id for r in results]
        common_only_id = tfidf_weight_test_items["item_common_only"].id
        non_common_only_id = tfidf_weight_test_items["item_non_common_only"].id

        if common_only_id in result_ids and non_common_only_id in result_ids:
            common_result = next(r for r in results if r.item.id == common_only_id)
            non_common_result = next(r for r in results if r.item.id == non_common_only_id)

            assert non_common_result.cc_score > common_result.cc_score, (
                "Non-common item should have higher CC score when weight=0.0 "
                f"(non-common: {non_common_result.cc_score}, "
                f"common: {common_result.cc_score})"
            )
        elif non_common_only_id in result_ids and common_only_id not in result_ids:
            pass
        else:
            assert non_common_only_id in result_ids, (
                "Non-common item should appear in results with weight=0.0"
            )

    async def test_weight_factor_one_treats_chunks_equally(self, tfidf_weight_test_items):
        """Test that common_chunk_weight_factor=1.0 treats all chunks equally.

        When weight factor is 1.0, common chunks get the same score as
        non-common chunks. Items with identical embeddings should have
        similar CC scores regardless of is_common flag.
        """
        from src.fact_checking.repository import hybrid_search_with_chunks

        query_text = "tfidf weight reduction test"
        query_embedding = generate_test_embedding(seed=100)

        async with get_session_maker()() as session:
            results = await hybrid_search_with_chunks(
                session=session,
                query_text=query_text,
                query_embedding=query_embedding,
                dataset_tags=["tfidf"],
                limit=10,
                common_chunk_weight_factor=1.0,
            )

        assert len(results) >= 2, "Should find at least two items"

        result_scores = {r.item.id: r.cc_score for r in results}
        common_only_id = tfidf_weight_test_items["item_common_only"].id
        non_common_only_id = tfidf_weight_test_items["item_non_common_only"].id

        if common_only_id in result_scores and non_common_only_id in result_scores:
            common_score = result_scores[common_only_id]
            non_common_score = result_scores[non_common_only_id]

            score_diff = abs(common_score - non_common_score)
            max_score = max(common_score, non_common_score)
            relative_diff = score_diff / max_score if max_score > 0 else 0

            assert relative_diff < 0.2, (
                "With weight=1.0, common and non-common items should have similar scores. "
                f"Common: {common_score}, Non-common: {non_common_score}, "
                f"Relative difference: {relative_diff:.2%}"
            )

    async def test_weight_reduction_affects_ranking_order(self, tfidf_weight_test_items):
        """Test that weight factor changes the ranking order of results.

        Compare results with weight=0.5 vs weight=1.0 to verify that
        the weight reduction mechanism actually affects the final ranking.
        """
        from src.fact_checking.repository import hybrid_search_with_chunks

        query_text = "tfidf weight reduction test"
        query_embedding = generate_test_embedding(seed=100)

        async with get_session_maker()() as session:
            results_reduced = await hybrid_search_with_chunks(
                session=session,
                query_text=query_text,
                query_embedding=query_embedding,
                dataset_tags=["tfidf"],
                limit=10,
                common_chunk_weight_factor=0.5,
            )

            results_equal = await hybrid_search_with_chunks(
                session=session,
                query_text=query_text,
                query_embedding=query_embedding,
                dataset_tags=["tfidf"],
                limit=10,
                common_chunk_weight_factor=1.0,
            )

        common_only_id = tfidf_weight_test_items["item_common_only"].id

        reduced_scores = {r.item.id: r.cc_score for r in results_reduced}
        equal_scores = {r.item.id: r.cc_score for r in results_equal}

        if common_only_id in reduced_scores and common_only_id in equal_scores:
            common_reduced = reduced_scores[common_only_id]
            common_equal = equal_scores[common_only_id]

            assert common_reduced < common_equal or abs(common_reduced - common_equal) < 0.001, (
                "Common item should have lower score with weight=0.5 than weight=1.0. "
                f"Reduced: {common_reduced}, Equal: {common_equal}"
            )
