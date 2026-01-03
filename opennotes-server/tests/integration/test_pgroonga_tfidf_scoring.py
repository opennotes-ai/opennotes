"""Integration tests for PGroonga TF-IDF scoring with BM25-style length normalization.

These tests verify that the hybrid_search_with_chunks function correctly applies
BM25-style length normalization to PGroonga TF-IDF scores:

    normalized_score = raw_score / (1 - b + b * (doc_len / avgdl))

Where:
- b = 0.75 (standard BM25 length normalization parameter, see BM25_LENGTH_NORMALIZATION_B)
- doc_len = word_count of the chunk
- avgdl = average chunk length from chunk_stats materialized view

The effect of this normalization:
- Short chunks (word_count < avgdl) get boosted scores
- Long chunks (word_count > avgdl) get reduced scores
- This prevents long documents from dominating results just by having more terms

TEST ISOLATION:
These tests are marked with pytest.mark.serial to ensure they run sequentially
rather than in parallel with pytest-xdist. This is required because:
1. Tests modify the chunk_stats materialized view (shared state)
2. Multiple workers refreshing chunk_stats simultaneously could cause race conditions
3. The fixture cleanup relies on predictable view state between setup and teardown

INFRASTRUCTURE REQUIREMENT:
These tests require a PostgreSQL image with PGroonga installed.
The current test infrastructure uses pgvector/pgvector:pg18 which does not include PGroonga.

To run these tests:
1. Update docker-compose.yml to use a PostgreSQL image with PGroonga (e.g., groonga/pgroonga:latest-alpine-18)
2. Or use a custom image that includes both pgvector and pgroonga

Tests will be skipped (or fail at migration) if PGroonga is not available.
"""

import pytest
from sqlalchemy import delete, select, text

from src.database import get_session_maker
from src.fact_checking.chunk_models import ChunkEmbedding, FactCheckChunk
from src.fact_checking.models import FactCheckItem

pytestmark = [pytest.mark.asyncio, pytest.mark.pgroonga, pytest.mark.serial]


async def check_pgroonga_available() -> bool:
    """Check if PGroonga extension is available in the database."""
    try:
        async with get_session_maker()() as session:
            result = await session.execute(
                text("SELECT 1 FROM pg_extension WHERE extname = 'pgroonga'")
            )
            return result.scalar_one_or_none() is not None
    except Exception:
        return False


async def check_chunk_stats_view_exists() -> bool:
    """Check if chunk_stats materialized view exists."""
    try:
        async with get_session_maker()() as session:
            result = await session.execute(
                text("SELECT 1 FROM pg_matviews WHERE matviewname = 'chunk_stats'")
            )
            return result.scalar_one_or_none() is not None
    except Exception:
        return False


@pytest.fixture
async def require_pgroonga():
    """Skip tests if PGroonga extension is not available.

    This fixture checks for PGroonga availability and skips tests if
    PGroonga is not installed.
    """
    pgroonga_available = await check_pgroonga_available()
    if not pgroonga_available:
        pytest.skip(
            "PGroonga extension not available in test database. "
            "These tests require a PostgreSQL image with PGroonga installed."
        )

    chunk_stats_exists = await check_chunk_stats_view_exists()
    if not chunk_stats_exists:
        pytest.skip(
            "chunk_stats materialized view not found. "
            "Run migrations to create the PGroonga infrastructure."
        )


def generate_test_embedding(seed: int = 0) -> list[float]:
    """Generate a deterministic test embedding vector (1536 dimensions).

    Uses a simple pattern to create embeddings that have predictable
    similarity relationships for testing.
    """
    import math

    base = [math.sin(i * 0.01 + seed * 0.1) for i in range(1536)]
    norm = math.sqrt(sum(x * x for x in base))
    return [x / norm for x in base]


def count_words(text: str) -> int:
    """Count words in text using whitespace splitting.

    Matches the PostgreSQL word counting logic:
    array_length(regexp_split_to_array(chunk_text, E'\\s+'), 1)

    Note on tokenization strategy:
    This uses simple whitespace splitting rather than language-aware tokenization
    (like tsvector/english). This is intentional for BM25 length normalization:
    - BM25 needs a rough document length measure, not linguistic precision
    - Whitespace splitting counts all tokens including stop words
    - tsvector would stem words and remove stop words (changing counts)
    - The relative ratio (doc_len / avgdl) is what matters, not absolute counts
    """
    return len(text.split())


@pytest.fixture
async def pgroonga_tfidf_test_items(require_pgroonga):
    """Create test data for PGroonga TF-IDF length normalization tests.

    Creates chunks with varying lengths containing the same search terms.
    The word_count column is populated to match actual text length.

    Test data structure:
    - item_short: Has a short chunk (~4 words) containing "quick brown fox"
    - item_long: Has a long chunk (~30+ words) containing "quick brown fox"
    - item_medium: Has a medium chunk (~15 words) containing "quick brown fox"

    All chunks contain the same search terms but with different lengths,
    allowing tests to verify length normalization affects ranking.

    Note on REFRESH MATERIALIZED VIEW:
    Tests use non-concurrent refresh (REFRESH MATERIALIZED VIEW chunk_stats)
    rather than CONCURRENTLY because:
    1. Tests run serially within this module (see pytestmark)
    2. Non-concurrent is faster for small test datasets
    3. No other queries run during test setup/teardown
    Production should use CONCURRENTLY - see docs/chunk-stats-refresh.md
    """
    item_ids = []
    chunk_ids = []

    short_text = "The quick brown fox"
    long_text = (
        "The quick brown fox jumps over the lazy dog. "
        "This is additional content that makes the document much longer "
        "with more words that dilute the keyword density and demonstrate "
        "how length normalization reduces scores for verbose documents."
    )
    medium_text = "The quick brown fox jumps over the lazy dog. Some additional context here."

    async with get_session_maker()() as session:
        item_short = FactCheckItem(
            dataset_name="pgroonga-tfidf-test",
            dataset_tags=["pgroonga", "tfidf-test"],
            title="Short chunk test item",
            content="Short content for testing length normalization.",
            summary="Short test",
            rating="True",
        )
        session.add(item_short)

        item_long = FactCheckItem(
            dataset_name="pgroonga-tfidf-test",
            dataset_tags=["pgroonga", "tfidf-test"],
            title="Long chunk test item",
            content="Long content for testing length normalization with more words.",
            summary="Long test",
            rating="True",
        )
        session.add(item_long)

        item_medium = FactCheckItem(
            dataset_name="pgroonga-tfidf-test",
            dataset_tags=["pgroonga", "tfidf-test"],
            title="Medium chunk test item",
            content="Medium length content for testing.",
            summary="Medium test",
            rating="True",
        )
        session.add(item_medium)

        await session.flush()

        chunk_short = ChunkEmbedding(
            chunk_text=short_text,
            embedding=generate_test_embedding(seed=100),
            embedding_provider="test",
            embedding_model="test-model",
            is_common=False,
        )
        session.add(chunk_short)

        chunk_long = ChunkEmbedding(
            chunk_text=long_text,
            embedding=generate_test_embedding(seed=100),
            embedding_provider="test",
            embedding_model="test-model",
            is_common=False,
        )
        session.add(chunk_long)

        chunk_medium = ChunkEmbedding(
            chunk_text=medium_text,
            embedding=generate_test_embedding(seed=100),
            embedding_provider="test",
            embedding_model="test-model",
            is_common=False,
        )
        session.add(chunk_medium)

        await session.flush()

        await session.execute(
            text(
                """
                UPDATE chunk_embeddings
                SET word_count = array_length(regexp_split_to_array(chunk_text, E'\\s+'), 1)
                WHERE id IN (:id1, :id2, :id3)
                """
            ),
            {"id1": str(chunk_short.id), "id2": str(chunk_long.id), "id3": str(chunk_medium.id)},
        )

        link_short = FactCheckChunk(
            chunk_id=chunk_short.id,
            fact_check_id=item_short.id,
            chunk_index=0,
        )
        session.add(link_short)

        link_long = FactCheckChunk(
            chunk_id=chunk_long.id,
            fact_check_id=item_long.id,
            chunk_index=0,
        )
        session.add(link_long)

        link_medium = FactCheckChunk(
            chunk_id=chunk_medium.id,
            fact_check_id=item_medium.id,
            chunk_index=0,
        )
        session.add(link_medium)

        await session.commit()

        await session.execute(text("REFRESH MATERIALIZED VIEW chunk_stats"))
        await session.commit()

        await session.refresh(item_short)
        await session.refresh(item_long)
        await session.refresh(item_medium)
        await session.refresh(chunk_short)
        await session.refresh(chunk_long)
        await session.refresh(chunk_medium)

        item_ids = [item_short.id, item_long.id, item_medium.id]
        chunk_ids = [chunk_short.id, chunk_long.id, chunk_medium.id]

        yield {
            "item_short": item_short,
            "item_long": item_long,
            "item_medium": item_medium,
            "chunk_short": chunk_short,
            "chunk_long": chunk_long,
            "chunk_medium": chunk_medium,
            "short_text": short_text,
            "long_text": long_text,
            "medium_text": medium_text,
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

        await session.execute(text("REFRESH MATERIALIZED VIEW chunk_stats"))
        await session.commit()


class TestPGroongaTFIDFLengthNormalization:
    """Integration tests for PGroonga TF-IDF scoring with BM25-style length normalization."""

    async def test_long_chunk_scores_lower_than_short_chunk_for_same_query(
        self, pgroonga_tfidf_test_items
    ):
        """Test that long chunks score lower than short chunks for the same query.

        BM25-style length normalization should reduce scores for longer documents:
        - Short chunk (~4 words) with "quick brown fox" should rank higher
        - Long chunk (~30+ words) with "quick brown fox" should rank lower

        We use alpha=0.0 (pure keyword search) to isolate the length normalization
        effect from semantic similarity.
        """
        from src.fact_checking.repository import hybrid_search_with_chunks

        query_text = "quick brown fox"
        query_embedding = generate_test_embedding(seed=999)

        async with get_session_maker()() as session:
            results = await hybrid_search_with_chunks(
                session=session,
                query_text=query_text,
                query_embedding=query_embedding,
                dataset_tags=["pgroonga"],
                limit=10,
                alpha=0.0,
            )

        assert len(results) >= 2, "Should find at least two matching items"

        result_ids = [r.item.id for r in results]
        short_id = pgroonga_tfidf_test_items["item_short"].id
        long_id = pgroonga_tfidf_test_items["item_long"].id

        assert short_id in result_ids, "Short chunk item should be in results"
        assert long_id in result_ids, "Long chunk item should be in results"

        short_idx = result_ids.index(short_id)
        long_idx = result_ids.index(long_id)

        short_result = results[short_idx]
        long_result = results[long_idx]

        assert short_result.cc_score > long_result.cc_score, (
            f"Short chunk should have higher score than long chunk due to length normalization. "
            f"Short: {short_result.cc_score:.4f}, Long: {long_result.cc_score:.4f}"
        )

        assert short_idx < long_idx, (
            f"Short chunk should rank higher (lower index) than long chunk. "
            f"Short index: {short_idx}, Long index: {long_idx}"
        )

    async def test_exact_match_in_short_document_ranks_highest(self, pgroonga_tfidf_test_items):
        """Test that the shortest chunk with a term match ranks highest.

        When multiple chunks contain the same search term, the shortest one
        should have the highest score due to BM25-style length normalization.

        Ranking expectation: short > medium > long
        """
        from src.fact_checking.repository import hybrid_search_with_chunks

        query_text = "quick brown fox"
        query_embedding = generate_test_embedding(seed=999)

        async with get_session_maker()() as session:
            results = await hybrid_search_with_chunks(
                session=session,
                query_text=query_text,
                query_embedding=query_embedding,
                dataset_tags=["pgroonga"],
                limit=10,
                alpha=0.0,
            )

        assert len(results) >= 3, "Should find all three test items"

        result_ids = [r.item.id for r in results]
        short_id = pgroonga_tfidf_test_items["item_short"].id
        medium_id = pgroonga_tfidf_test_items["item_medium"].id
        long_id = pgroonga_tfidf_test_items["item_long"].id

        assert short_id in result_ids, "Short chunk item should be in results"
        assert medium_id in result_ids, "Medium chunk item should be in results"
        assert long_id in result_ids, "Long chunk item should be in results"

        short_idx = result_ids.index(short_id)
        medium_idx = result_ids.index(medium_id)
        long_idx = result_ids.index(long_id)

        short_score = results[short_idx].cc_score
        medium_score = results[medium_idx].cc_score
        long_score = results[long_idx].cc_score

        assert short_score >= medium_score >= long_score, (
            f"Scores should decrease as chunk length increases. "
            f"Short: {short_score:.4f}, Medium: {medium_score:.4f}, Long: {long_score:.4f}"
        )

        assert short_idx <= medium_idx <= long_idx, (
            f"Rankings should reflect length normalization: short <= medium <= long. "
            f"Short: {short_idx}, Medium: {medium_idx}, Long: {long_idx}"
        )

    async def test_length_normalization_uses_avg_chunk_length(self, pgroonga_tfidf_test_items):
        """Test that length normalization uses the avg_chunk_length from chunk_stats.

        The BM25 formula uses avgdl (average document length) from the chunk_stats
        materialized view. This test verifies that:
        1. The chunk_stats view exists and has data
        2. Scores are affected by the average chunk length
        """
        async with get_session_maker()() as session:
            result = await session.execute(
                text("SELECT total_chunks, avg_chunk_length FROM chunk_stats")
            )
            stats = result.fetchone()

        assert stats is not None, "chunk_stats materialized view should have data"
        total_chunks, avg_chunk_length = stats

        assert total_chunks > 0, "total_chunks should be positive"
        assert avg_chunk_length is not None, "avg_chunk_length should not be None"
        assert avg_chunk_length > 0, "avg_chunk_length should be positive"

        short_word_count = count_words(pgroonga_tfidf_test_items["short_text"])
        long_word_count = count_words(pgroonga_tfidf_test_items["long_text"])

        b = 0.75
        short_normalization = 1.0 - b + b * (short_word_count / avg_chunk_length)
        long_normalization = 1.0 - b + b * (long_word_count / avg_chunk_length)

        assert short_normalization < long_normalization, (
            f"Short chunk normalization factor ({short_normalization:.4f}) should be less than "
            f"long chunk factor ({long_normalization:.4f}), meaning short chunk gets higher score"
        )

    async def test_word_count_column_populated_correctly(self, pgroonga_tfidf_test_items):
        """Test that the word_count column is populated correctly for test chunks.

        This validates that our test setup correctly populates word_count,
        which is essential for length normalization to work.
        """
        async with get_session_maker()() as session:
            short_chunk = await session.get(
                ChunkEmbedding, pgroonga_tfidf_test_items["chunk_short"].id
            )
            long_chunk = await session.get(
                ChunkEmbedding, pgroonga_tfidf_test_items["chunk_long"].id
            )
            medium_chunk = await session.get(
                ChunkEmbedding, pgroonga_tfidf_test_items["chunk_medium"].id
            )

        expected_short = count_words(pgroonga_tfidf_test_items["short_text"])
        expected_long = count_words(pgroonga_tfidf_test_items["long_text"])
        expected_medium = count_words(pgroonga_tfidf_test_items["medium_text"])

        assert short_chunk.word_count == expected_short, (
            f"Short chunk word_count should be {expected_short}, got {short_chunk.word_count}"
        )
        assert long_chunk.word_count == expected_long, (
            f"Long chunk word_count should be {expected_long}, got {long_chunk.word_count}"
        )
        assert medium_chunk.word_count == expected_medium, (
            f"Medium chunk word_count should be {expected_medium}, got {medium_chunk.word_count}"
        )

        assert short_chunk.word_count < medium_chunk.word_count < long_chunk.word_count, (
            f"Word counts should increase: short ({short_chunk.word_count}) < "
            f"medium ({medium_chunk.word_count}) < long ({long_chunk.word_count})"
        )


class TestPGroongaTFIDFEdgeCases:
    """Edge case tests for PGroonga TF-IDF length normalization."""

    async def test_empty_chunk_stats_handled_gracefully(self, require_pgroonga):
        """Test that hybrid search handles empty chunk_stats gracefully.

        When the chunk_stats view has no data (NULLIF prevents division by zero),
        the search should still work without errors.
        """
        from src.fact_checking.repository import hybrid_search_with_chunks

        query_text = "nonexistent query xyz123abc"
        query_embedding = generate_test_embedding(seed=999)

        async with get_session_maker()() as session:
            results = await hybrid_search_with_chunks(
                session=session,
                query_text=query_text,
                query_embedding=query_embedding,
                limit=10,
                alpha=0.0,
            )

        assert len(results) == 0, "Should return empty results for non-matching query"

    async def test_single_word_chunk_scores_correctly(self, pgroonga_tfidf_test_items):
        """Test that very short chunks (single word matches) score correctly.

        Single word matches in short chunks should get boosted scores
        compared to the same word in longer chunks.
        """
        from src.fact_checking.repository import hybrid_search_with_chunks

        query_text = "quick"
        query_embedding = generate_test_embedding(seed=999)

        async with get_session_maker()() as session:
            results = await hybrid_search_with_chunks(
                session=session,
                query_text=query_text,
                query_embedding=query_embedding,
                dataset_tags=["pgroonga"],
                limit=10,
                alpha=0.0,
            )

        if len(results) >= 2:
            result_ids = [r.item.id for r in results]
            short_id = pgroonga_tfidf_test_items["item_short"].id
            long_id = pgroonga_tfidf_test_items["item_long"].id

            if short_id in result_ids and long_id in result_ids:
                short_idx = result_ids.index(short_id)
                long_idx = result_ids.index(long_id)

                assert short_idx <= long_idx, (
                    "Short chunk should rank equal or higher than long chunk for single word query"
                )

    async def test_keyword_threshold_filters_low_scores(self, pgroonga_tfidf_test_items):
        """Test that keyword_relevance_threshold filters out low-scoring results.

        With a high threshold, only the best matches should remain.
        """
        from src.fact_checking.repository import hybrid_search_with_chunks

        query_text = "quick brown fox"
        query_embedding = generate_test_embedding(seed=999)

        async with get_session_maker()() as session:
            results_no_threshold = await hybrid_search_with_chunks(
                session=session,
                query_text=query_text,
                query_embedding=query_embedding,
                dataset_tags=["pgroonga"],
                limit=10,
                keyword_relevance_threshold=0.0,
                alpha=0.0,
            )

            results_high_threshold = await hybrid_search_with_chunks(
                session=session,
                query_text=query_text,
                query_embedding=query_embedding,
                dataset_tags=["pgroonga"],
                limit=10,
                keyword_relevance_threshold=100.0,
                alpha=0.0,
            )

        assert len(results_high_threshold) <= len(results_no_threshold), (
            "Higher threshold should return equal or fewer results"
        )


class TestWordCountTrigger:
    """Tests for the word_count auto-population trigger."""

    async def test_word_count_auto_populated_on_insert(self, require_pgroonga):
        """Test that word_count is automatically computed on INSERT via trigger.

        The trigger should compute word_count = number of whitespace-separated words.
        """
        test_text = "The quick brown fox jumps over lazy dog"
        expected_word_count = 8

        async with get_session_maker()() as session:
            chunk = ChunkEmbedding(
                chunk_text=test_text,
                embedding=generate_test_embedding(seed=200),
                embedding_provider="test",
                embedding_model="test-model",
                is_common=False,
            )
            session.add(chunk)
            await session.commit()

            await session.refresh(chunk)
            chunk_id = chunk.id

        try:
            async with get_session_maker()() as session:
                result = await session.execute(
                    text("SELECT word_count FROM chunk_embeddings WHERE id = :id"),
                    {"id": str(chunk_id)},
                )
                actual_word_count = result.scalar_one()

            assert actual_word_count == expected_word_count, (
                f"word_count should be {expected_word_count}, got {actual_word_count}"
            )
        finally:
            async with get_session_maker()() as session:
                await session.execute(delete(ChunkEmbedding).where(ChunkEmbedding.id == chunk_id))
                await session.commit()

    async def test_word_count_zero_for_empty_text(self, require_pgroonga):
        """Test that word_count is 0 for empty chunk_text.

        The trigger should handle empty strings gracefully using COALESCE.
        """
        async with get_session_maker()() as session:
            chunk = ChunkEmbedding(
                chunk_text="",
                embedding=generate_test_embedding(seed=201),
                embedding_provider="test",
                embedding_model="test-model",
                is_common=False,
            )
            session.add(chunk)
            await session.commit()

            await session.refresh(chunk)
            chunk_id = chunk.id

        try:
            async with get_session_maker()() as session:
                result = await session.execute(
                    text("SELECT word_count FROM chunk_embeddings WHERE id = :id"),
                    {"id": str(chunk_id)},
                )
                actual_word_count = result.scalar_one()

            assert actual_word_count == 0, (
                f"word_count should be 0 for empty text, got {actual_word_count}"
            )
        finally:
            async with get_session_maker()() as session:
                await session.execute(delete(ChunkEmbedding).where(ChunkEmbedding.id == chunk_id))
                await session.commit()

    async def test_word_count_zero_for_whitespace_only_text(self, require_pgroonga):
        """Test that word_count is 0 for whitespace-only chunk_text.

        The trigger should handle whitespace-only strings using NULLIF(TRIM(...), '').
        """
        async with get_session_maker()() as session:
            chunk = ChunkEmbedding(
                chunk_text="   \t\n   ",
                embedding=generate_test_embedding(seed=202),
                embedding_provider="test",
                embedding_model="test-model",
                is_common=False,
            )
            session.add(chunk)
            await session.commit()

            await session.refresh(chunk)
            chunk_id = chunk.id

        try:
            async with get_session_maker()() as session:
                result = await session.execute(
                    text("SELECT word_count FROM chunk_embeddings WHERE id = :id"),
                    {"id": str(chunk_id)},
                )
                actual_word_count = result.scalar_one()

            assert actual_word_count == 0, (
                f"word_count should be 0 for whitespace-only text, got {actual_word_count}"
            )
        finally:
            async with get_session_maker()() as session:
                await session.execute(delete(ChunkEmbedding).where(ChunkEmbedding.id == chunk_id))
                await session.commit()

    async def test_word_count_updated_on_chunk_text_change(self, require_pgroonga):
        """Test that word_count is recomputed when chunk_text is updated.

        The trigger fires on UPDATE OF chunk_text, so changing the text should
        update the word_count.
        """
        original_text = "hello world"
        updated_text = "one two three four five"
        expected_original_count = 2
        expected_updated_count = 5

        async with get_session_maker()() as session:
            chunk = ChunkEmbedding(
                chunk_text=original_text,
                embedding=generate_test_embedding(seed=203),
                embedding_provider="test",
                embedding_model="test-model",
                is_common=False,
            )
            session.add(chunk)
            await session.commit()
            await session.refresh(chunk)
            chunk_id = chunk.id

        try:
            async with get_session_maker()() as session:
                result = await session.execute(
                    text("SELECT word_count FROM chunk_embeddings WHERE id = :id"),
                    {"id": str(chunk_id)},
                )
                original_word_count = result.scalar_one()

            assert original_word_count == expected_original_count, (
                f"Original word_count should be {expected_original_count}, got {original_word_count}"
            )

            async with get_session_maker()() as session:
                from src.fact_checking.chunk_models import compute_chunk_text_hash

                await session.execute(
                    text(
                        "UPDATE chunk_embeddings SET chunk_text = :text, chunk_text_hash = :hash WHERE id = :id"
                    ),
                    {
                        "text": updated_text,
                        "hash": compute_chunk_text_hash(updated_text),
                        "id": str(chunk_id),
                    },
                )
                await session.commit()

            async with get_session_maker()() as session:
                result = await session.execute(
                    text("SELECT word_count FROM chunk_embeddings WHERE id = :id"),
                    {"id": str(chunk_id)},
                )
                updated_word_count = result.scalar_one()

            assert updated_word_count == expected_updated_count, (
                f"Updated word_count should be {expected_updated_count}, got {updated_word_count}"
            )
        finally:
            async with get_session_maker()() as session:
                await session.execute(delete(ChunkEmbedding).where(ChunkEmbedding.id == chunk_id))
                await session.commit()
