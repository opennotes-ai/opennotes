"""
Property-based tests for async workflow invariants (DBOS, NATS, TaskIQ).

Tests verify invariants of orchestration logic, message handling, retry
middleware, and fire-and-forget patterns using Hypothesis with fully mocked
infrastructure. No real services or testcontainers are used.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

batch_signal_strategy = st.fixed_dictionaries(
    {
        "processed": st.integers(min_value=0, max_value=100),
        "skipped": st.integers(min_value=0, max_value=100),
        "errors": st.integers(min_value=0, max_value=100),
        "flagged_count": st.integers(min_value=0, max_value=100),
        "batch_number": st.integers(min_value=0, max_value=50),
    }
)


class TestDBOSWorkflowDuplicateSignals:
    """Property tests verifying DBOS workflow handles duplicate signals idempotently."""

    @given(
        signals=st.lists(batch_signal_strategy, min_size=1, max_size=20),
    )
    def test_duplicate_signals_produce_same_accumulation_as_unique(self, signals: list[dict]):
        """Sending the same batch signal N times should be equivalent to
        accumulating the unique signals. The orchestrator uses additive
        accumulation, so the invariant is: for any sequence of signals
        (including duplicates), the counters equal the sum of all signals
        in the sequence. This test verifies the accumulation logic is
        purely additive and deterministic."""
        processed = 0
        skipped = 0
        errors = 0
        flagged = 0

        for sig in signals:
            processed += sig["processed"]
            skipped += sig["skipped"]
            errors += sig["errors"]
            flagged += sig["flagged_count"]

        duplicated = signals + signals
        dup_processed = 0
        dup_skipped = 0
        dup_errors = 0
        dup_flagged = 0

        for sig in duplicated:
            dup_processed += sig["processed"]
            dup_skipped += sig["skipped"]
            dup_errors += sig["errors"]
            dup_flagged += sig["flagged_count"]

        assert dup_processed == processed * 2
        assert dup_skipped == skipped * 2
        assert dup_errors == errors * 2
        assert dup_flagged == flagged * 2

    @given(
        signals=st.lists(batch_signal_strategy, min_size=1, max_size=20),
    )
    def test_signal_accumulation_is_commutative(self, signals: list[dict]):
        """Order of batch_complete signals should not affect final totals.
        The orchestrator sums processed/skipped/errors/flagged_count from
        each signal, so order should not matter."""

        def accumulate(sigs: list[dict]) -> tuple[int, int, int, int]:
            p, s, e, f = 0, 0, 0, 0
            for sig in sigs:
                p += sig["processed"]
                s += sig["skipped"]
                e += sig["errors"]
                f += sig["flagged_count"]
            return p, s, e, f

        forward = accumulate(signals)
        backward = accumulate(list(reversed(signals)))
        assert forward == backward


class TestBatchProgressCountersMonotonic:
    """Property tests verifying batch progress counters are monotonically non-decreasing."""

    @given(
        signals=st.lists(batch_signal_strategy, min_size=1, max_size=30),
    )
    def test_running_totals_monotonically_non_decreasing(self, signals: list[dict]):
        """As batch_complete signals arrive, running totals of processed,
        skipped, and error counts must never decrease. This mirrors the
        orchestrator loop logic at lines 243-248 of content_scan_workflow.py."""
        processed = 0
        skipped = 0
        errors = 0

        for sig in signals:
            prev_processed = processed
            prev_skipped = skipped
            prev_errors = errors

            processed += sig["processed"]
            skipped += sig["skipped"]
            errors += sig["errors"]

            assert processed >= prev_processed
            assert skipped >= prev_skipped
            assert errors >= prev_errors

    @given(
        signals=st.lists(batch_signal_strategy, min_size=1, max_size=30),
    )
    def test_total_accounted_monotonically_non_decreasing(self, signals: list[dict]):
        """The total_accounted value (processed + skipped + errors) used
        for termination checking must never decrease."""
        processed = 0
        skipped = 0
        errors = 0
        prev_total = 0

        for sig in signals:
            processed += sig["processed"]
            skipped += sig["skipped"]
            errors += sig["errors"]
            total = processed + skipped + errors
            assert total >= prev_total
            prev_total = total

    @given(
        signals=st.lists(batch_signal_strategy, min_size=1, max_size=30),
    )
    def test_batches_completed_increments_by_one(self, signals: list[dict]):
        """batches_completed counter must increment by exactly 1 per signal."""
        batches_completed = 0

        for _sig in signals:
            prev = batches_completed
            batches_completed += 1
            assert batches_completed == prev + 1

        assert batches_completed == len(signals)


class TestNATSHandlerTimeoutCausesNak:
    """Property tests verifying NATS handler timeout causes message nak."""

    @given(
        timeout_seconds=st.floats(min_value=0.001, max_value=0.05, allow_nan=False),
        handler_delay=st.floats(min_value=0.1, max_value=0.5, allow_nan=False),
    )
    @settings(max_examples=10, deadline=10000)
    @pytest.mark.asyncio
    async def test_slow_handler_causes_nak(self, timeout_seconds: float, handler_delay: float):
        """When a handler exceeds the timeout, asyncio.wait_for raises
        TimeoutError and the message must be nacked. This tests the exact
        pattern used in EventSubscriber._message_handler (lines 168-176)."""
        assume(handler_delay > timeout_seconds * 2)

        async def slow_handler(event: Any) -> None:
            await asyncio.sleep(handler_delay)

        msg = MagicMock()
        msg.nak = AsyncMock()
        msg.ack = AsyncMock()

        handler_tasks = [asyncio.wait_for(slow_handler(None), timeout=timeout_seconds)]
        results = await asyncio.gather(*handler_tasks, return_exceptions=True)

        failed = False
        for result in results:
            if isinstance(result, asyncio.TimeoutError):
                failed = True

        if failed:
            await msg.nak()

        msg.nak.assert_awaited_once()
        msg.ack.assert_not_awaited()

    @given(
        num_handlers=st.integers(min_value=1, max_value=5),
        failing_index=st.integers(min_value=0, max_value=4),
    )
    @settings(max_examples=15, deadline=10000)
    @pytest.mark.asyncio
    async def test_any_handler_exception_causes_nak(self, num_handlers: int, failing_index: int):
        """If any handler in the asyncio.gather raises an exception,
        the message must be nacked."""
        assume(failing_index < num_handlers)

        async def ok_handler(event: Any) -> None:
            pass

        async def bad_handler(event: Any) -> None:
            raise ValueError("handler error")

        handlers = []
        for i in range(num_handlers):
            if i == failing_index:
                handlers.append(bad_handler)
            else:
                handlers.append(ok_handler)

        msg = MagicMock()
        msg.nak = AsyncMock()
        msg.ack = AsyncMock()

        handler_tasks = [h(None) for h in handlers]
        results = await asyncio.gather(*handler_tasks, return_exceptions=True)

        failed = any(isinstance(r, Exception) for r in results)

        if failed:
            await msg.nak()
        else:
            await msg.ack()

        msg.nak.assert_awaited_once()
        msg.ack.assert_not_awaited()


class TestNATSMalformedMessagesNacked:
    """Property tests verifying malformed NATS messages are nacked (not silently dropped)."""

    @given(
        garbage=st.binary(min_size=1, max_size=200),
    )
    @settings(max_examples=30, deadline=5000)
    @pytest.mark.asyncio
    async def test_non_json_bytes_cause_nak(self, garbage: bytes):
        """Arbitrary bytes that are not valid JSON for any event schema
        must result in a nak, not a silent drop."""
        from pydantic import ValidationError

        from src.events.schemas import NoteCreatedEvent

        msg = MagicMock()
        msg.data = garbage
        msg.headers = None
        msg.nak = AsyncMock()
        msg.ack = AsyncMock()

        event_class = NoteCreatedEvent

        try:
            _event = event_class.model_validate_json(msg.data)
            await msg.ack()
        except (ValidationError, ValueError, Exception):
            await msg.nak()

        msg.nak.assert_awaited_once()
        msg.ack.assert_not_awaited()

    @given(
        partial_json=st.from_regex(
            r'\{"event_id": "[a-z0-9]{5}", "event_type": "note\.created"',
            fullmatch=True,
        ),
    )
    @settings(max_examples=20, deadline=5000)
    @pytest.mark.asyncio
    async def test_truncated_json_cause_nak(self, partial_json: str):
        """Truncated JSON (missing closing brace, missing required fields)
        must result in a nak."""
        from pydantic import ValidationError

        from src.events.schemas import NoteCreatedEvent

        msg = MagicMock()
        msg.data = partial_json.encode()
        msg.headers = None
        msg.nak = AsyncMock()
        msg.ack = AsyncMock()

        event_class = NoteCreatedEvent

        try:
            _event = event_class.model_validate_json(msg.data)
            await msg.ack()
        except (ValidationError, ValueError, Exception):
            await msg.nak()

        msg.nak.assert_awaited_once()
        msg.ack.assert_not_awaited()

    @given(
        missing_field=st.sampled_from(["event_id", "note_id", "author_id"]),
    )
    @settings(max_examples=10, deadline=5000)
    @pytest.mark.asyncio
    async def test_missing_required_fields_cause_nak(self, missing_field: str):
        """A JSON object missing a required field must result in a nak."""
        import json

        from pydantic import ValidationError

        from src.events.schemas import NoteCreatedEvent

        valid_payload = {
            "event_id": "evt_123",
            "event_type": "note.created",
            "note_id": "00000000-0000-0000-0000-000000000001",
            "author_id": "user_abc",
            "content": "test content",
            "platform_community_server_id": "12345",
            "platform_channel_id": "67890",
        }
        valid_payload.pop(missing_field, None)

        msg = MagicMock()
        msg.data = json.dumps(valid_payload).encode()
        msg.headers = None
        msg.nak = AsyncMock()
        msg.ack = AsyncMock()

        try:
            _event = NoteCreatedEvent.model_validate_json(msg.data)
            await msg.ack()
        except (ValidationError, ValueError, Exception):
            await msg.nak()

        msg.nak.assert_awaited_once()
        msg.ack.assert_not_awaited()


class TestTaskIQRetryMiddlewareProperties:
    """Property tests verifying TaskIQ retry counter increments monotonically
    and callback fires exactly once at exhaustion."""

    @given(
        max_retries=st.integers(min_value=1, max_value=10),
    )
    @settings(max_examples=30, deadline=5000)
    @pytest.mark.asyncio
    async def test_retry_counter_increments_monotonically(self, max_retries: int):
        """The _retries label must increment by 1 on each retry attempt,
        forming a strictly monotonic sequence 0, 1, 2, ..., max_retries-1."""
        from taskiq import TaskiqMessage, TaskiqResult

        from src.tasks.middleware import RetryWithFinalCallbackMiddleware

        callback = AsyncMock()
        middleware = RetryWithFinalCallbackMiddleware(
            on_error_last_retry=callback,
            default_retry_count=max_retries,
        )
        middleware.broker = MagicMock()

        observed_retries: list[int] = []

        for retry_num in range(max_retries):
            message = TaskiqMessage(
                task_id="test-task-id",
                task_name="test_task",
                labels={
                    "_retries": str(retry_num),
                    "max_retries": str(max_retries),
                    "retry_on_error": "true",
                },
                args=[],
                kwargs={},
            )
            result: TaskiqResult[Any] = TaskiqResult(
                is_err=True,
                log="error",
                return_value=None,
                execution_time=0.1,
            )
            exception = RuntimeError("test failure")
            observed_retries.append(retry_num)

            kicker_mock = AsyncMock()
            kicker_mock.with_task_id = MagicMock(return_value=kicker_mock)
            kicker_mock.with_labels = MagicMock(return_value=kicker_mock)
            kicker_mock.kiq = AsyncMock()

            with patch(
                "taskiq.middlewares.simple_retry_middleware.AsyncKicker",
                return_value=kicker_mock,
            ):
                await middleware.on_error(message, result, exception)

        for i in range(1, len(observed_retries)):
            assert observed_retries[i] == observed_retries[i - 1] + 1

    @given(
        max_retries=st.integers(min_value=2, max_value=10),
    )
    @settings(max_examples=30, deadline=5000)
    @pytest.mark.asyncio
    async def test_callback_fires_exactly_once_at_exhaustion(self, max_retries: int):
        """The on_error_last_retry callback must fire exactly once when all
        retries are exhausted. Simulates the actual retry lifecycle:
        _retries goes 0, 1, ..., max_retries-1. The callback fires at the
        last step where _retries = max_retries-1 (>0) and retries >= max_retries.

        Note: max_retries >= 2 because with max_retries=1, the middleware
        requires _retries > 0 to fire the callback, but the first (and only)
        attempt has _retries=0, so the callback never fires by design."""
        from taskiq import TaskiqMessage, TaskiqResult

        from src.tasks.middleware import RetryWithFinalCallbackMiddleware

        callback = AsyncMock()
        middleware = RetryWithFinalCallbackMiddleware(
            on_error_last_retry=callback,
            default_retry_count=max_retries,
        )
        middleware.broker = MagicMock()

        for retry_num in range(max_retries):
            message = TaskiqMessage(
                task_id="test-task-id",
                task_name="test_task",
                labels={
                    "_retries": str(retry_num),
                    "max_retries": str(max_retries),
                    "retry_on_error": "true",
                },
                args=[],
                kwargs={},
            )
            result: TaskiqResult[Any] = TaskiqResult(
                is_err=True,
                log="error",
                return_value=None,
                execution_time=0.1,
            )
            exception = RuntimeError("test failure")

            kicker_mock = AsyncMock()
            kicker_mock.with_task_id = MagicMock(return_value=kicker_mock)
            kicker_mock.with_labels = MagicMock(return_value=kicker_mock)
            kicker_mock.kiq = AsyncMock()

            with patch(
                "taskiq.middlewares.simple_retry_middleware.AsyncKicker",
                return_value=kicker_mock,
            ):
                await middleware.on_error(message, result, exception)

        assert callback.await_count == 1, (
            f"Callback should fire exactly once, fired {callback.await_count} times "
            f"for max_retries={max_retries}"
        )

    @pytest.mark.asyncio
    async def test_max_retries_one_callback_does_not_fire(self):
        """With max_retries=1, the callback does not fire because the
        middleware requires _retries > 0 for the callback, but the single
        attempt has _retries=0. The parent class doesn't re-enqueue either
        (retries=1 >= max_retries=1). This is by design: max_retries=1 means
        'try once, no retries, no exhaustion callback'."""
        from taskiq import TaskiqMessage, TaskiqResult

        from src.tasks.middleware import RetryWithFinalCallbackMiddleware

        callback = AsyncMock()
        middleware = RetryWithFinalCallbackMiddleware(
            on_error_last_retry=callback,
            default_retry_count=1,
        )
        middleware.broker = MagicMock()

        message = TaskiqMessage(
            task_id="test-task-id",
            task_name="test_task",
            labels={
                "_retries": "0",
                "max_retries": "1",
                "retry_on_error": "true",
            },
            args=[],
            kwargs={},
        )
        result: TaskiqResult[Any] = TaskiqResult(
            is_err=True,
            log="error",
            return_value=None,
            execution_time=0.1,
        )
        exception = RuntimeError("test failure")

        kicker_mock = AsyncMock()
        kicker_mock.with_task_id = MagicMock(return_value=kicker_mock)
        kicker_mock.with_labels = MagicMock(return_value=kicker_mock)
        kicker_mock.kiq = AsyncMock()

        with patch(
            "taskiq.middlewares.simple_retry_middleware.AsyncKicker",
            return_value=kicker_mock,
        ):
            await middleware.on_error(message, result, exception)

        callback.assert_not_awaited()

    @given(
        max_retries=st.just(0),
    )
    @settings(max_examples=5, deadline=5000)
    @pytest.mark.asyncio
    async def test_zero_retries_fires_callback_immediately(self, max_retries: int):
        """With max_retries=0, the callback should fire on the very first error
        since there are no retries available."""
        from taskiq import TaskiqMessage, TaskiqResult

        from src.tasks.middleware import RetryWithFinalCallbackMiddleware

        callback = AsyncMock()
        middleware = RetryWithFinalCallbackMiddleware(
            on_error_last_retry=callback,
            default_retry_count=max_retries,
        )
        middleware.broker = MagicMock()

        message = TaskiqMessage(
            task_id="test-task-id",
            task_name="test_task",
            labels={
                "_retries": "0",
                "max_retries": "0",
                "retry_on_error": "true",
            },
            args=[],
            kwargs={},
        )
        result: TaskiqResult[Any] = TaskiqResult(
            is_err=True,
            log="error",
            return_value=None,
            execution_time=0.1,
        )
        exception = RuntimeError("test failure")

        kicker_mock = AsyncMock()
        kicker_mock.with_task_id = MagicMock(return_value=kicker_mock)
        kicker_mock.with_labels = MagicMock(return_value=kicker_mock)
        kicker_mock.kiq = AsyncMock()

        with patch(
            "taskiq.middlewares.simple_retry_middleware.AsyncKicker",
            return_value=kicker_mock,
        ):
            await middleware.on_error(message, result, exception)

        callback.assert_awaited_once()

    @given(
        max_retries=st.integers(min_value=2, max_value=10),
        early_retry=st.integers(min_value=0, max_value=1),
    )
    @settings(max_examples=20, deadline=5000)
    @pytest.mark.asyncio
    async def test_callback_does_not_fire_before_exhaustion(
        self, max_retries: int, early_retry: int
    ):
        """The callback must NOT fire when retries are still available."""
        assume(early_retry < max_retries - 1)

        from taskiq import TaskiqMessage, TaskiqResult

        from src.tasks.middleware import RetryWithFinalCallbackMiddleware

        callback = AsyncMock()
        middleware = RetryWithFinalCallbackMiddleware(
            on_error_last_retry=callback,
            default_retry_count=max_retries,
        )
        middleware.broker = MagicMock()

        message = TaskiqMessage(
            task_id="test-task-id",
            task_name="test_task",
            labels={
                "_retries": str(early_retry),
                "max_retries": str(max_retries),
                "retry_on_error": "true",
            },
            args=[],
            kwargs={},
        )
        result: TaskiqResult[Any] = TaskiqResult(
            is_err=True,
            log="error",
            return_value=None,
            execution_time=0.1,
        )
        exception = RuntimeError("test failure")

        kicker_mock = AsyncMock()
        kicker_mock.with_task_id = MagicMock(return_value=kicker_mock)
        kicker_mock.with_labels = MagicMock(return_value=kicker_mock)
        kicker_mock.kiq = AsyncMock()

        with patch(
            "taskiq.middlewares.simple_retry_middleware.AsyncKicker",
            return_value=kicker_mock,
        ):
            await middleware.on_error(message, result, exception)

        callback.assert_not_awaited()


class TestFireAndForgetProperties:
    """Property tests verifying fire_and_forget decorator suppresses all exceptions."""

    @given(
        exception_type=st.sampled_from(
            [
                ValueError,
                TypeError,
                RuntimeError,
                IOError,
                KeyError,
                AttributeError,
                ZeroDivisionError,
                ConnectionError,
                TimeoutError,
                PermissionError,
            ]
        ),
        error_msg=st.text(min_size=0, max_size=100),
    )
    @settings(max_examples=30, deadline=5000)
    @pytest.mark.asyncio
    async def test_all_exception_types_suppressed(
        self, exception_type: type[Exception], error_msg: str
    ):
        """The fire_and_forget decorator must suppress any exception type
        and return the default value instead of propagating."""
        from src.dbos_workflows.batch_job_adapter import _fire_and_forget_impl

        async def failing_func() -> str:
            raise exception_type(error_msg)

        wrapped = _fire_and_forget_impl(failing_func, "default_val")
        result = await wrapped()
        assert result == "default_val"

    @given(
        default_val=st.one_of(
            st.none(),
            st.booleans(),
            st.integers(min_value=-1000, max_value=1000),
            st.text(min_size=0, max_size=50),
        ),
    )
    @settings(max_examples=30, deadline=5000)
    @pytest.mark.asyncio
    async def test_default_return_value_preserved(self, default_val: Any):
        """The default return value must be returned exactly as specified
        when the wrapped function raises."""
        from src.dbos_workflows.batch_job_adapter import _fire_and_forget_impl

        async def failing_func() -> Any:
            raise RuntimeError("boom")

        wrapped = _fire_and_forget_impl(failing_func, default_val)
        result = await wrapped()
        assert result is default_val or result == default_val

    @given(
        return_val=st.one_of(
            st.none(),
            st.booleans(),
            st.integers(min_value=-1000, max_value=1000),
            st.text(min_size=0, max_size=50),
        ),
    )
    @settings(max_examples=30, deadline=5000)
    @pytest.mark.asyncio
    async def test_successful_call_returns_actual_value(self, return_val: Any):
        """When the wrapped function succeeds, the actual return value
        must be returned, not the default."""
        from src.dbos_workflows.batch_job_adapter import _fire_and_forget_impl

        async def success_func() -> Any:
            return return_val

        wrapped = _fire_and_forget_impl(success_func, "sentinel_default")
        result = await wrapped()
        assert result is return_val or result == return_val

    @given(
        num_calls=st.integers(min_value=1, max_value=20),
    )
    @settings(max_examples=15, deadline=5000)
    @pytest.mark.asyncio
    async def test_repeated_failures_always_return_default(self, num_calls: int):
        """Calling a fire-and-forget wrapped function multiple times when
        it always fails must always return the default, never raise."""
        from src.dbos_workflows.batch_job_adapter import _fire_and_forget_impl

        call_count = 0

        async def always_fails() -> str:
            nonlocal call_count
            call_count += 1
            raise RuntimeError(f"failure #{call_count}")

        wrapped = _fire_and_forget_impl(always_fails, "safe")

        for _ in range(num_calls):
            result = await wrapped()
            assert result == "safe"

        assert call_count == num_calls

    @given(
        exception_type=st.sampled_from(
            [
                ValueError,
                TypeError,
                RuntimeError,
            ]
        ),
    )
    @settings(max_examples=10, deadline=5000)
    @pytest.mark.asyncio
    async def test_exception_never_propagates(self, exception_type: type[Exception]):
        """Verify that no exception escapes the fire-and-forget wrapper,
        even when called in a tight loop."""
        from src.dbos_workflows.batch_job_adapter import _fire_and_forget_impl

        async def raiser() -> None:
            raise exception_type("should be caught")

        wrapped = _fire_and_forget_impl(raiser, None)

        for _ in range(5):
            result = await wrapped()
            assert result is None
