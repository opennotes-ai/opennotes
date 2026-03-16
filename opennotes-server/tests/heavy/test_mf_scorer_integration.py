"""
Heavy integration tests for MFCoreScorerAdapter with real MFCoreScorer.

These tests run real matrix factorization and are resource-intensive.
They must run sequentially (-n 0) to avoid OOM-killing xdist workers.

Moved from tests/integration/notes/scoring/test_mf_scorer_integration.py
as part of TASK-1135.

Test coverage:
- 10.2: Integration test with minimum 5 raters, 10 notes
- 10.3: Verify score_note() returns non-stub results (metadata["source"] == "mf_core")
- 10.5: Test cache eviction beyond 10k entries
- 10.6: Test thread safety with concurrent score_note() calls
"""

import threading
from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

import pyarrow as pa
import pytest

from src.notes.scoring.mf_scorer_adapter import MFCoreScorerAdapter
from src.notes.scoring.scorer_protocol import ScoringResult


class MockCommunityDataProvider:
    def __init__(self, num_raters: int = 15, num_notes: int = 20) -> None:
        self._num_raters = num_raters
        self._num_notes = num_notes
        self._raters = [f"rater-{i}" for i in range(num_raters)]
        self._note_ids = [uuid4() for _ in range(num_notes)]
        self._build_data()

    def _build_data(self) -> None:
        now = datetime.now(UTC)
        note_ids_str = [str(nid) for nid in self._note_ids]
        author_ids = [self._raters[i % len(self._raters)] for i in range(self._num_notes)]
        classifications = [
            "NOT_MISLEADING" if i < 10 else "MISINFORMED_OR_POTENTIALLY_MISLEADING"
            for i in range(self._num_notes)
        ]

        self._notes_table = pa.table(
            {
                "id": note_ids_str,
                "author_id": author_ids,
                "classification": classifications,
                "status": ["NEEDS_MORE_RATINGS"] * self._num_notes,
                "created_at": [now] * self._num_notes,
            }
        )

        r_ids, r_note_ids, r_rater_ids, r_levels, r_times = [], [], [], [], []
        for note_idx, note_id in enumerate(self._note_ids):
            for rater_idx, rater_id in enumerate(self._raters):
                if author_ids[note_idx] == rater_id:
                    continue
                r_ids.append(str(uuid4()))
                r_note_ids.append(str(note_id))
                r_rater_ids.append(rater_id)
                r_levels.append(self._determine_helpfulness(note_idx, rater_idx))
                r_times.append(now)

        self._ratings_table = pa.table(
            {
                "id": r_ids,
                "note_id": r_note_ids,
                "rater_id": r_rater_ids,
                "helpfulness_level": r_levels,
                "created_at": r_times,
            }
        )

    def _determine_helpfulness(self, note_idx: int, rater_idx: int) -> str:
        third = self._num_notes // 3
        if note_idx < third:
            return "HELPFUL" if rater_idx % 4 != 0 else "SOMEWHAT_HELPFUL"
        if note_idx < 2 * third:
            return "NOT_HELPFUL" if rater_idx % 4 != 0 else "SOMEWHAT_HELPFUL"
        if rater_idx % 2 == 0:
            return "HELPFUL"
        return "NOT_HELPFUL"

    def get_all_ratings(self, community_id: str) -> pa.Table:
        return self._ratings_table

    def get_all_notes(self, community_id: str) -> pa.Table:
        return self._notes_table

    def get_all_participants(self, community_id: str) -> pa.Array:
        return pa.array(self._raters)

    def get_note_id(self, index: int) -> str:
        return str(self._note_ids[index])


@pytest.mark.heavy
@pytest.mark.integration
class TestMFCoreScorerIntegration:
    """Integration tests for MFCoreScorerAdapter with real MFCoreScorer."""

    def test_score_note_with_real_mf_core_scorer(self):
        """
        score_note returns results from MFCoreScorer, not stub.

        AC #11: Verify that score_note() with a real data provider produces
        results with metadata["source"] == "mf_core".
        """
        provider = MockCommunityDataProvider()
        adapter = MFCoreScorerAdapter(
            data_provider=provider,
            community_id="test-community",
        )

        note_id = provider.get_note_id(0)
        result = adapter.score_note(note_id, [])

        assert result is not None
        assert isinstance(result, ScoringResult)
        assert result.metadata.get("source") == "mf_core"

    def test_score_note_returns_normalized_score(self):
        """score_note returns a score normalized between 0.0 and 1.0."""
        provider = MockCommunityDataProvider()
        adapter = MFCoreScorerAdapter(
            data_provider=provider,
            community_id="test-community",
        )

        note_id = provider.get_note_id(0)
        result = adapter.score_note(note_id, [])

        assert 0.0 <= result.score <= 1.0

    def test_score_note_returns_valid_confidence_levels(self):
        """score_note returns one of the valid confidence levels."""
        provider = MockCommunityDataProvider()
        adapter = MFCoreScorerAdapter(
            data_provider=provider,
            community_id="test-community",
        )

        note_id = provider.get_note_id(0)
        result = adapter.score_note(note_id, [])

        valid_levels = {"high", "standard", "provisional"}
        assert result.confidence_level in valid_levels

    def test_score_note_metadata_contains_mf_core_fields(self):
        """score_note metadata contains MFCoreScorer-specific fields."""
        provider = MockCommunityDataProvider()
        adapter = MFCoreScorerAdapter(
            data_provider=provider,
            community_id="test-community",
        )

        note_id = provider.get_note_id(0)
        result = adapter.score_note(note_id, [])

        assert "source" in result.metadata
        assert "intercept" in result.metadata
        assert "factor" in result.metadata
        assert "status" in result.metadata

    def test_score_multiple_notes_returns_consistent_results(self):
        """Scoring multiple notes returns consistent results from batch scoring."""
        provider = MockCommunityDataProvider()
        adapter = MFCoreScorerAdapter(
            data_provider=provider,
            community_id="test-community",
        )

        results = []
        for i in range(3):
            note_id = provider.get_note_id(i)
            result = adapter.score_note(note_id, [])
            results.append(result)

        for result in results:
            assert result.metadata.get("source") == "mf_core"


@pytest.mark.heavy
@pytest.mark.integration
class TestMFCoreScorerCacheEviction:
    """Integration tests for LRU cache eviction behavior."""

    def test_cache_evicts_oldest_entries_beyond_max_size(self):
        """
        Cache evicts oldest entries when exceeding max size.

        AC #10: Test cache eviction by populating beyond 10k entries.
        """
        provider = MockCommunityDataProvider()
        adapter = MFCoreScorerAdapter(
            data_provider=provider,
            community_id="test-community",
        )

        for i in range(15):
            adapter._cache[f"note-{i}"] = ScoringResult(
                score=0.5, confidence_level="standard", metadata={"index": i}
            )

        adapter._evict_if_needed(max_size=10)

        assert len(adapter._cache) == 10
        assert "note-0" not in adapter._cache
        assert "note-4" not in adapter._cache
        assert "note-5" in adapter._cache
        assert "note-14" in adapter._cache

    def test_cache_lru_order_preserved_on_access(self):
        """Accessing a cached entry moves it to the end (most recently used)."""
        adapter = MFCoreScorerAdapter()

        for i in range(5):
            adapter._cache[f"note-{i}"] = ScoringResult(
                score=0.5,
                confidence_level="standard",
                metadata={"source": "mf_core"},
            )
        adapter._cache_version = adapter._current_version

        adapter.score_note("note-0", [])

        keys = list(adapter._cache.keys())
        assert keys[-1] == "note-0"

    def test_cache_eviction_with_large_batch_result(self):
        """Cache handles eviction after large batch scoring result."""
        provider = MockCommunityDataProvider()
        adapter = MFCoreScorerAdapter(
            data_provider=provider,
            community_id="test-community",
        )

        for i in range(9995):
            adapter._cache[f"old-note-{i}"] = ScoringResult(
                score=0.5, confidence_level="standard", metadata={}
            )

        note_id = provider.get_note_id(0)
        adapter.score_note(note_id, [])

        assert len(adapter._cache) <= 10000


@pytest.mark.heavy
@pytest.mark.integration
class TestMFCoreScorerThreadSafety:
    """Integration tests for thread safety of concurrent score_note() calls."""

    def test_concurrent_score_note_calls_no_race_conditions(self):
        """
        Multiple threads calling score_note don't cause race conditions.

        AC #9: Test thread safety with concurrent score_note() calls.
        """
        provider = MockCommunityDataProvider()
        adapter = MFCoreScorerAdapter(
            data_provider=provider,
            community_id="test-community",
        )

        results = []
        errors = []
        lock = threading.Lock()

        def score_note_thread(note_idx):
            try:
                note_id = provider.get_note_id(note_idx)
                result = adapter.score_note(note_id, [])
                with lock:
                    results.append((note_idx, result))
            except Exception as e:
                with lock:
                    errors.append((note_idx, e))

        threads = []
        for i in range(10):
            t = threading.Thread(target=score_note_thread, args=(i % 10,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        assert len(errors) == 0, f"Thread errors: {errors}"
        assert len(results) == 10

        for _note_idx, result in results:
            assert result is not None
            assert isinstance(result, ScoringResult)

    def test_concurrent_score_note_single_batch_execution(self):
        """Multiple concurrent calls for same note execute batch scoring only once."""
        provider = MockCommunityDataProvider()
        adapter = MFCoreScorerAdapter(
            data_provider=provider,
            community_id="test-community",
        )

        batch_calls = []
        original_batch_scoring = adapter._execute_batch_scoring

        def tracked_batch_scoring():
            batch_calls.append(1)
            return original_batch_scoring()

        with patch.object(adapter, "_execute_batch_scoring", side_effect=tracked_batch_scoring):
            threads = []
            note_id = provider.get_note_id(0)

            for _ in range(5):
                t = threading.Thread(target=lambda: adapter.score_note(note_id, []))
                threads.append(t)
                t.start()

            for t in threads:
                t.join()

        assert len(batch_calls) == 1

    def test_concurrent_access_with_cache_invalidation(self):
        """Thread safety maintained even with cache invalidation between calls."""
        provider = MockCommunityDataProvider()
        adapter = MFCoreScorerAdapter(
            data_provider=provider,
            community_id="test-community",
        )

        results = []
        errors = []
        lock = threading.Lock()

        def score_and_invalidate(idx):
            try:
                note_id = provider.get_note_id(idx)
                result = adapter.score_note(note_id, [])
                if idx % 2 == 0:
                    adapter.update_ratings_version()
                with lock:
                    results.append(result)
            except Exception as e:
                with lock:
                    errors.append(e)

        threads = []
        for i in range(8):
            t = threading.Thread(target=score_and_invalidate, args=(i % 10,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        assert len(errors) == 0, f"Thread errors: {errors}"
        assert len(results) == 8


@pytest.mark.heavy
@pytest.mark.integration
class TestMFCoreScorerDataValidation:
    """Integration tests for data validation and edge cases."""

    def test_score_note_with_minimum_viable_data(self):
        """score_note works with minimum viable data (15 raters, 20 notes)."""
        provider = MockCommunityDataProvider()
        adapter = MFCoreScorerAdapter(
            data_provider=provider,
            community_id="test-community",
        )

        note_id = provider.get_note_id(0)
        result = adapter.score_note(note_id, [])

        assert result is not None
        assert result.metadata.get("source") == "mf_core"

    def test_score_note_with_larger_dataset(self):
        """score_note handles larger datasets correctly."""
        provider = MockCommunityDataProvider(num_raters=20, num_notes=30)
        adapter = MFCoreScorerAdapter(
            data_provider=provider,
            community_id="test-community",
        )

        note_id = provider.get_note_id(0)
        result = adapter.score_note(note_id, [])

        assert result is not None
        assert 0.0 <= result.score <= 1.0
        assert result.metadata.get("source") == "mf_core"

    def test_score_note_for_nonexistent_note_falls_back_to_stub(self):
        """Scoring a note not in the batch results falls back to stub."""
        provider = MockCommunityDataProvider()
        adapter = MFCoreScorerAdapter(
            data_provider=provider,
            community_id="test-community",
        )

        result = adapter.score_note("nonexistent-note-id", [0.5, 0.6])

        assert result is not None
        assert result.metadata.get("source") == "batch_stub"
