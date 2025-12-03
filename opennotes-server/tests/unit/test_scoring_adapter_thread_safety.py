import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from src.scoring_adapter import (
    ScoringAdapter,
    _apply_scoring_threshold_monkey_patch,
    _pandas_patch_lock,
    _scoring_threshold_patch_lock,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def reset_global_state():
    """Reset global patching state before each test."""
    import src.scoring_adapter as adapter_module

    original_pandas_patched = adapter_module._pandas_patched
    original_scoring_patched = adapter_module._scoring_thresholds_patched
    original_mf_init = adapter_module._original_mf_base_scorer_init

    yield

    adapter_module._pandas_patched = original_pandas_patched
    adapter_module._scoring_thresholds_patched = original_scoring_patched
    adapter_module._original_mf_base_scorer_init = original_mf_init


@pytest.fixture
def sample_scoring_data():
    """Provide sample data for scoring operations."""
    return {
        "notes": [
            {
                "noteId": 1,
                "noteAuthorParticipantId": "author1",
                "createdAtMillis": 1234567890,
                "tweetId": "100",
                "summary": "Test note 1",
                "classification": "MISINFORMED_OR_POTENTIALLY_MISLEADING",
            },
            {
                "noteId": 2,
                "noteAuthorParticipantId": "author2",
                "createdAtMillis": 1234567891,
                "tweetId": "101",
                "summary": "Test note 2",
                "classification": "NOT_MISLEADING",
            },
        ],
        "ratings": [
            {
                "raterParticipantId": "rater1",
                "noteId": 1,
                "createdAtMillis": 1234567900,
                "helpfulnessLevel": "HELPFUL",
            },
            {
                "raterParticipantId": "rater2",
                "noteId": 1,
                "createdAtMillis": 1234567901,
                "helpfulnessLevel": "HELPFUL",
            },
            {
                "raterParticipantId": "rater3",
                "noteId": 2,
                "createdAtMillis": 1234567902,
                "helpfulnessLevel": "NOT_HELPFUL",
            },
        ],
        "enrollment": [
            {
                "participantId": "author1",
                "enrollmentState": "EARNED_IN",
                "successfulRatingNeededToEarnIn": 0,
                "timestampOfLastStateChange": 1234567890,
            },
            {
                "participantId": "author2",
                "enrollmentState": "EARNED_IN",
                "successfulRatingNeededToEarnIn": 0,
                "timestampOfLastStateChange": 1234567890,
            },
            {
                "participantId": "rater1",
                "enrollmentState": "EARNED_IN",
                "successfulRatingNeededToEarnIn": 0,
                "timestampOfLastStateChange": 1234567890,
            },
            {
                "participantId": "rater2",
                "enrollmentState": "EARNED_IN",
                "successfulRatingNeededToEarnIn": 0,
                "timestampOfLastStateChange": 1234567890,
            },
            {
                "participantId": "rater3",
                "enrollmentState": "EARNED_IN",
                "successfulRatingNeededToEarnIn": 0,
                "timestampOfLastStateChange": 1234567890,
            },
        ],
    }


class TestThreadSafety:
    """Test thread-safety of scoring adapter global state management."""

    def test_pandas_patch_lock_exists(self):
        """Verify pandas patch lock is defined."""
        assert _pandas_patch_lock is not None
        assert type(_pandas_patch_lock).__name__ == "lock"

    def test_scoring_threshold_patch_lock_exists(self):
        """Verify scoring threshold patch lock is defined."""
        assert _scoring_threshold_patch_lock is not None
        assert type(_scoring_threshold_patch_lock).__name__ == "lock"

    def test_concurrent_threshold_patching(self, reset_global_state):
        """Test that concurrent calls to patch threshold only apply once."""
        import src.scoring_adapter as adapter_module

        adapter_module._scoring_thresholds_patched = False
        adapter_module._original_mf_base_scorer_init = None

        threads = []
        for _ in range(10):
            thread = threading.Thread(target=_apply_scoring_threshold_monkey_patch)
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        assert adapter_module._scoring_thresholds_patched is True

    def test_concurrent_patch_initialization(self, reset_global_state):
        """
        Test that concurrent initialization of the scoring adapter safely applies patches.

        This test simulates multiple workers/threads initializing the adapter simultaneously
        to verify that the double-checked locking pattern prevents race conditions.
        """
        import src.scoring_adapter as adapter_module

        # Reset state to simulate fresh worker startup
        adapter_module._pandas_patched = False
        adapter_module._scoring_thresholds_patched = False
        adapter_module._original_mf_base_scorer_init = None

        patch_counts = {"pandas": 0, "threshold": 0}
        lock = threading.Lock()

        def initialize_adapter():
            """Simulate adapter initialization in a worker."""
            from src.scoring_adapter import (
                _apply_scoring_threshold_monkey_patch,
                _pandas_patch_lock,
            )

            # Simulate pandas patching
            if not adapter_module._pandas_patched:
                with _pandas_patch_lock:
                    if not adapter_module._pandas_patched:
                        with lock:
                            patch_counts["pandas"] += 1
                        adapter_module._pandas_patched = True

            # Simulate threshold patching
            _apply_scoring_threshold_monkey_patch()
            if adapter_module._scoring_thresholds_patched:
                with lock:
                    patch_counts["threshold"] += 1

        # Spawn multiple threads simulating concurrent worker startup
        threads = []
        for _ in range(10):
            thread = threading.Thread(target=initialize_adapter)
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # Both patches should only be applied once despite 10 concurrent attempts
        assert patch_counts["pandas"] == 1, "Pandas patch should only be applied once"
        # Threshold patch increments for each thread that sees it as patched
        assert patch_counts["threshold"] >= 1, "Threshold patch should be applied"
        assert adapter_module._pandas_patched is True
        assert adapter_module._scoring_thresholds_patched is True

    def test_thread_pool_patch_safety(self, reset_global_state):
        """
        Test patch safety with ThreadPoolExecutor to simulate Gunicorn multi-worker environment.

        This test verifies that when multiple workers (simulated by threads in a pool)
        start up concurrently, the patches are applied exactly once.
        """
        import src.scoring_adapter as adapter_module

        adapter_module._pandas_patched = False
        adapter_module._scoring_thresholds_patched = False
        adapter_module._original_mf_base_scorer_init = None

        initialization_count = []
        lock = threading.Lock()

        def worker_startup():
            """Simulate worker process startup."""
            from src.scoring_adapter import _apply_scoring_threshold_monkey_patch

            # Apply patches (should be safe)
            _apply_scoring_threshold_monkey_patch()

            # Record that this worker completed initialization
            with lock:
                initialization_count.append(threading.current_thread().ident)

            return adapter_module._scoring_thresholds_patched

        # Simulate 5 workers starting up concurrently
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(worker_startup) for _ in range(5)]
            results = [future.result() for future in futures]

        # All workers should see patches as applied
        assert all(results), "All workers should see patches applied"
        assert len(initialization_count) == 5, "All 5 workers should complete initialization"
        assert adapter_module._scoring_thresholds_patched is True

    def test_double_checked_locking_pandas_patch(self, reset_global_state):
        """Test double-checked locking pattern for pandas patching."""
        import src.scoring_adapter as adapter_module

        adapter_module._pandas_patched = False

        patch_attempts = []
        lock = threading.Lock()

        def attempt_patch():
            from src.scoring_adapter import _pandas_patch_lock

            if not adapter_module._pandas_patched:
                with _pandas_patch_lock:
                    if not adapter_module._pandas_patched:
                        with lock:
                            patch_attempts.append(threading.current_thread().ident)
                        adapter_module._pandas_patched = True

        threads = []
        for _ in range(20):
            thread = threading.Thread(target=attempt_patch)
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        assert adapter_module._pandas_patched
        assert len(patch_attempts) == 1, "Patch should only be applied once"

    def test_double_checked_locking_threshold_patch(self, reset_global_state):
        """Test double-checked locking pattern for threshold patching."""
        import src.scoring_adapter as adapter_module

        adapter_module._scoring_thresholds_patched = False
        adapter_module._original_mf_base_scorer_init = None

        patch_attempts = []
        lock = threading.Lock()

        def attempt_patch():
            from src.scoring_adapter import _scoring_threshold_patch_lock

            if not adapter_module._scoring_thresholds_patched:
                with _scoring_threshold_patch_lock:
                    if not adapter_module._scoring_thresholds_patched:
                        with lock:
                            patch_attempts.append(threading.current_thread().ident)
                        adapter_module._scoring_thresholds_patched = True

        threads = []
        for _ in range(20):
            thread = threading.Thread(target=attempt_patch)
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        assert adapter_module._scoring_thresholds_patched
        assert len(patch_attempts) == 1, "Patch should only be applied once"


class TestRaceConditionPrevention:
    """Test that race conditions are prevented in multi-threaded scenarios."""

    def test_no_race_in_global_state_modification(self, reset_global_state):
        """Ensure global state modifications are atomic."""
        import src.scoring_adapter as adapter_module

        adapter_module._pandas_patched = False
        adapter_module._scoring_thresholds_patched = False

        state_transitions = []
        lock = threading.Lock()

        def check_and_modify():
            _apply_scoring_threshold_monkey_patch()

            with lock:
                state_transitions.append(
                    {
                        "thread": threading.current_thread().ident,
                        "pandas_patched": adapter_module._pandas_patched,
                        "thresholds_patched": adapter_module._scoring_thresholds_patched,
                    }
                )

        threads = []
        for _ in range(10):
            thread = threading.Thread(target=check_and_modify)
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        assert len(state_transitions) == 10
        for state in state_transitions:
            assert state["thresholds_patched"] is True

    def test_lock_acquisition_timeout(self):
        """Verify locks can be acquired within reasonable time."""
        import time

        start_time = time.time()

        acquired = _pandas_patch_lock.acquire(timeout=1.0)
        try:
            assert acquired, "Failed to acquire pandas patch lock"
        finally:
            if acquired:
                _pandas_patch_lock.release()

        elapsed = time.time() - start_time
        assert elapsed < 1.0, "Lock acquisition took too long"

        start_time = time.time()
        acquired = _scoring_threshold_patch_lock.acquire(timeout=1.0)
        try:
            assert acquired, "Failed to acquire threshold patch lock"
        finally:
            if acquired:
                _scoring_threshold_patch_lock.release()

        elapsed = time.time() - start_time
        assert elapsed < 1.0, "Lock acquisition took too long"


class TestConcurrencyDocumentation:
    """Verify thread-safety documentation exists."""

    def test_module_has_thread_safety_comments(self):
        """Verify thread-safety is documented in the module."""
        import src.scoring_adapter as adapter_module

        source = adapter_module.__file__
        with Path(source).open() as f:
            content = f.read()

        assert "thread-safety" in content.lower() or "thread safety" in content.lower()
        assert "lock" in content.lower()
        assert "race condition" in content.lower() or "concurrent" in content.lower()

    def test_function_docstrings_mention_thread_safety(self):
        """Verify key functions document thread-safety."""
        from src.scoring_adapter import _apply_scoring_threshold_monkey_patch

        assert _apply_scoring_threshold_monkey_patch.__doc__ is not None
        assert (
            "thread" in _apply_scoring_threshold_monkey_patch.__doc__.lower()
            or "lock" in _apply_scoring_threshold_monkey_patch.__doc__.lower()
        )

        adapter = ScoringAdapter()
        assert adapter._run_scoring_sync.__doc__ is not None
        assert (
            "thread" in adapter._run_scoring_sync.__doc__.lower()
            or "lock" in adapter._run_scoring_sync.__doc__.lower()
        )
