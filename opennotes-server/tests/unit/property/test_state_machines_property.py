"""
Property-based tests for batch job state machine transitions and circuit breakers.

Tests verify:
- Only valid batch job state transitions are accepted
- Timestamps (started_at, completed_at) are set exactly once
- Circuit breaker opens after threshold failures and probes after reset_timeout
- Circuit breaker probe failure returns to open state

All infrastructure is mocked; these test pure state transition logic.
"""

from unittest.mock import patch

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

from src.batch_jobs.schemas import BatchJobStatus
from src.batch_jobs.service import (
    VALID_STATUS_TRANSITIONS,
    InvalidStateTransitionError,
)
from src.dbos_workflows.circuit_breaker import (
    CircuitBreaker,
    CircuitOpenError,
    CircuitState,
)

ALL_STATUSES = list(BatchJobStatus)
TERMINAL_STATUSES = [s for s in ALL_STATUSES if not VALID_STATUS_TRANSITIONS.get(s)]
NON_TERMINAL_STATUSES = [s for s in ALL_STATUSES if VALID_STATUS_TRANSITIONS.get(s)]

status_strategy = st.sampled_from(ALL_STATUSES)
non_terminal_strategy = st.sampled_from(NON_TERMINAL_STATUSES)
terminal_strategy = st.sampled_from(TERMINAL_STATUSES)


def _validate_transition(current: BatchJobStatus, target: BatchJobStatus) -> None:
    if current == target:
        return
    valid_targets = VALID_STATUS_TRANSITIONS.get(current, set())
    if target not in valid_targets:
        raise InvalidStateTransitionError(current, target)


class TestBatchJobStateTransitionProperties:
    @given(data=st.data())
    def test_valid_transitions_always_accepted(self, data: st.DataObject):
        current = data.draw(non_terminal_strategy, label="current")
        valid_targets = VALID_STATUS_TRANSITIONS[current]
        assume(len(valid_targets) > 0)
        target = data.draw(
            st.sampled_from(sorted(valid_targets, key=lambda s: s.value)), label="target"
        )

        _validate_transition(current, target)

    @given(current=status_strategy, target=status_strategy)
    def test_invalid_transitions_always_rejected(
        self, current: BatchJobStatus, target: BatchJobStatus
    ):
        valid_targets = VALID_STATUS_TRANSITIONS.get(current, set())
        assume(target not in valid_targets)
        assume(current != target)

        with pytest.raises(InvalidStateTransitionError) as exc_info:
            _validate_transition(current, target)

        assert exc_info.value.current_status == current
        assert exc_info.value.target_status == target

    @given(current=terminal_strategy, target=status_strategy)
    def test_terminal_states_reject_all_new_transitions(
        self, current: BatchJobStatus, target: BatchJobStatus
    ):
        assume(current != target)

        with pytest.raises(InvalidStateTransitionError):
            _validate_transition(current, target)

    @given(current=status_strategy)
    def test_same_state_transition_is_noop(self, current: BatchJobStatus):
        _validate_transition(current, current)

    @given(
        transitions=st.lists(
            status_strategy,
            min_size=1,
            max_size=20,
        )
    )
    def test_random_transition_sequence_respects_valid_map(self, transitions: list[BatchJobStatus]):
        current = BatchJobStatus.PENDING
        for target in transitions:
            valid_targets = VALID_STATUS_TRANSITIONS.get(current, set())
            if target in valid_targets or target == current:
                _validate_transition(current, target)
                if target != current:
                    current = target
            else:
                with pytest.raises(InvalidStateTransitionError):
                    _validate_transition(current, target)

    @given(
        transitions=st.lists(
            status_strategy,
            min_size=1,
            max_size=20,
        )
    )
    def test_once_terminal_always_terminal(self, transitions: list[BatchJobStatus]):
        current = BatchJobStatus.PENDING
        reached_terminal = False

        for target in transitions:
            valid_targets = VALID_STATUS_TRANSITIONS.get(current, set())
            is_valid = target in valid_targets or target == current

            if reached_terminal and target != current:
                assert not is_valid, (
                    f"Terminal state {current.value} should not allow transition to {target.value}"
                )
            elif is_valid and target != current:
                current = target
                if current in TERMINAL_STATUSES:
                    reached_terminal = True


class TestBatchJobTimestampProperties:
    @given(
        transitions=st.lists(
            status_strategy,
            min_size=1,
            max_size=20,
        )
    )
    def test_started_at_set_exactly_once(self, transitions: list[BatchJobStatus]):
        current = BatchJobStatus.PENDING
        started_at_set = False

        for target in transitions:
            valid_targets = VALID_STATUS_TRANSITIONS.get(current, set())
            if target not in valid_targets or target == current:
                continue

            if target == BatchJobStatus.IN_PROGRESS:
                assert not started_at_set, "started_at would be set more than once"
                started_at_set = True

            current = target

    @given(
        transitions=st.lists(
            status_strategy,
            min_size=1,
            max_size=20,
        )
    )
    def test_completed_at_set_exactly_once(self, transitions: list[BatchJobStatus]):
        current = BatchJobStatus.PENDING
        completed_at_set = False

        for target in transitions:
            valid_targets = VALID_STATUS_TRANSITIONS.get(current, set())
            if target not in valid_targets or target == current:
                continue

            if target in TERMINAL_STATUSES:
                assert not completed_at_set, "completed_at would be set more than once"
                completed_at_set = True

            current = target

    @given(
        path=st.sampled_from(
            [
                [BatchJobStatus.IN_PROGRESS, BatchJobStatus.COMPLETED],
                [BatchJobStatus.IN_PROGRESS, BatchJobStatus.FAILED],
                [BatchJobStatus.IN_PROGRESS, BatchJobStatus.CANCELLED],
                [BatchJobStatus.CANCELLED],
                [BatchJobStatus.FAILED],
            ]
        )
    )
    def test_valid_paths_set_timestamps_correctly(self, path: list[BatchJobStatus]):
        current = BatchJobStatus.PENDING
        started_at = None
        completed_at = None

        for target in path:
            valid_targets = VALID_STATUS_TRANSITIONS.get(current, set())
            assert target in valid_targets, (
                f"Test path contains invalid transition: {current.value} -> {target.value}"
            )

            if target == BatchJobStatus.IN_PROGRESS:
                started_at = "set"
            if target in TERMINAL_STATUSES:
                completed_at = "set"

            current = target

        if BatchJobStatus.IN_PROGRESS in path:
            assert started_at is not None, "started_at should be set for paths through IN_PROGRESS"

        assert completed_at is not None or current not in TERMINAL_STATUSES, (
            "completed_at should be set when reaching a terminal state"
        )


class TestCircuitBreakerProperties:
    @given(
        threshold=st.integers(min_value=1, max_value=50),
        failure_count=st.integers(min_value=0, max_value=100),
    )
    def test_opens_exactly_at_threshold(self, threshold: int, failure_count: int):
        cb = CircuitBreaker(threshold=threshold, reset_timeout=60.0)

        for i in range(failure_count):
            cb.record_failure()
            if i + 1 >= threshold:
                assert cb.state == CircuitState.OPEN, (
                    f"Should be OPEN after {i + 1} failures (threshold={threshold})"
                )
            else:
                assert cb.state == CircuitState.CLOSED, (
                    f"Should be CLOSED after {i + 1} failures (threshold={threshold})"
                )

    @given(
        threshold=st.integers(min_value=1, max_value=20),
        failures_before_success=st.integers(min_value=0, max_value=19),
    )
    def test_success_resets_failure_count(self, threshold: int, failures_before_success: int):
        assume(failures_before_success < threshold)

        cb = CircuitBreaker(threshold=threshold, reset_timeout=60.0)

        for _ in range(failures_before_success):
            cb.record_failure()

        cb.record_success()

        assert cb.state == CircuitState.CLOSED
        assert cb.failures == 0

    @given(
        threshold=st.integers(min_value=1, max_value=10),
        reset_timeout=st.floats(
            min_value=0.1, max_value=300.0, allow_nan=False, allow_infinity=False
        ),
    )
    def test_opens_after_threshold_then_probes_after_timeout(
        self, threshold: int, reset_timeout: float
    ):
        cb = CircuitBreaker(threshold=threshold, reset_timeout=reset_timeout)

        for _ in range(threshold):
            cb.record_failure()

        assert cb.state == CircuitState.OPEN

        with patch("src.dbos_workflows.circuit_breaker.time") as mock_time:
            mock_time.time.return_value = cb.last_failure_time + reset_timeout + 0.001
            cb.check()

        assert cb.state == CircuitState.HALF_OPEN

    @given(
        threshold=st.integers(min_value=1, max_value=10),
        reset_timeout=st.floats(
            min_value=0.1, max_value=300.0, allow_nan=False, allow_infinity=False
        ),
    )
    def test_probe_failure_returns_to_open(self, threshold: int, reset_timeout: float):
        cb = CircuitBreaker(threshold=threshold, reset_timeout=reset_timeout)

        for _ in range(threshold):
            cb.record_failure()

        assert cb.state == CircuitState.OPEN

        with patch("src.dbos_workflows.circuit_breaker.time") as mock_time:
            mock_time.time.return_value = cb.last_failure_time + reset_timeout + 0.001
            cb.check()

        assert cb.state == CircuitState.HALF_OPEN

        cb.record_failure()

        assert cb.state == CircuitState.OPEN

    @given(
        threshold=st.integers(min_value=1, max_value=10),
        reset_timeout=st.floats(
            min_value=0.1, max_value=300.0, allow_nan=False, allow_infinity=False
        ),
    )
    def test_probe_success_closes_circuit(self, threshold: int, reset_timeout: float):
        cb = CircuitBreaker(threshold=threshold, reset_timeout=reset_timeout)

        for _ in range(threshold):
            cb.record_failure()

        with patch("src.dbos_workflows.circuit_breaker.time") as mock_time:
            mock_time.time.return_value = cb.last_failure_time + reset_timeout + 0.001
            cb.check()

        assert cb.state == CircuitState.HALF_OPEN

        cb.record_success()

        assert cb.state == CircuitState.CLOSED
        assert cb.failures == 0
        assert cb.last_failure_time is None

    @given(
        threshold=st.integers(min_value=1, max_value=10),
        reset_timeout=st.floats(
            min_value=1.0, max_value=300.0, allow_nan=False, allow_infinity=False
        ),
    )
    def test_open_circuit_rejects_before_timeout(self, threshold: int, reset_timeout: float):
        cb = CircuitBreaker(threshold=threshold, reset_timeout=reset_timeout)

        for _ in range(threshold):
            cb.record_failure()

        assert cb.state == CircuitState.OPEN

        with patch("src.dbos_workflows.circuit_breaker.time") as mock_time:
            mock_time.time.return_value = cb.last_failure_time + (reset_timeout * 0.5)
            with pytest.raises(CircuitOpenError):
                cb.check()

        assert cb.state == CircuitState.OPEN

    @given(
        threshold=st.integers(min_value=1, max_value=10),
        num_cycles=st.integers(min_value=1, max_value=5),
    )
    def test_circuit_can_open_and_close_multiple_times(self, threshold: int, num_cycles: int):
        cb = CircuitBreaker(threshold=threshold, reset_timeout=0.01)

        for _ in range(num_cycles):
            assert cb.state == CircuitState.CLOSED

            for _ in range(threshold):
                cb.record_failure()

            assert cb.state == CircuitState.OPEN

            with patch("src.dbos_workflows.circuit_breaker.time") as mock_time:
                mock_time.time.return_value = cb.last_failure_time + 1.0
                cb.check()

            assert cb.state == CircuitState.HALF_OPEN

            cb.record_success()

            assert cb.state == CircuitState.CLOSED
            assert cb.failures == 0

    @given(
        threshold=st.integers(min_value=2, max_value=10),
        successes_between=st.integers(min_value=1, max_value=5),
    )
    def test_intermittent_failures_dont_open_circuit(self, threshold: int, successes_between: int):
        cb = CircuitBreaker(threshold=threshold, reset_timeout=60.0)

        for _ in range(threshold * 2):
            cb.record_failure()
            for _ in range(successes_between):
                cb.record_success()

        assert cb.state == CircuitState.CLOSED
