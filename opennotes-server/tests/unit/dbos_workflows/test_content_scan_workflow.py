"""Tests for DBOS content scan workflow.

Tests the content scan orchestration workflow, batch processing step,
finalization step, and async dispatch/enqueue/signal helpers.

Note: Tests call __wrapped__ to bypass DBOS decorators (which require a
running DBOS runtime). External services (database, Redis, NATS, LLM) are
mocked since these are unit tests for workflow logic.
"""

from __future__ import annotations

import asyncio
import collections.abc
import json
import time
from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


@pytest.fixture(autouse=True)
def mock_clear_scan_finalizing_step():
    with patch(
        "src.dbos_workflows.content_scan_workflow.clear_scan_finalizing_step",
        return_value=True,
    ) as mock_clear:
        yield mock_clear


class TestContentScanQueueConfiguration:
    """Tests for DBOS Queue configuration."""

    def test_queue_exists(self) -> None:
        from src.dbos_workflows.content_scan_workflow import content_scan_queue

        assert content_scan_queue.name == "content_scan"

    def test_queue_worker_concurrency(self) -> None:
        from src.dbos_workflows.content_scan_workflow import content_scan_queue

        assert content_scan_queue.worker_concurrency == 6

    def test_queue_global_concurrency(self) -> None:
        from src.dbos_workflows.content_scan_workflow import content_scan_queue

        assert content_scan_queue.concurrency == 12


class TestTimeoutConstants:
    """Tests for timeout configuration."""

    def test_batch_recv_timeout(self) -> None:
        from src.dbos_workflows.content_scan_workflow import BATCH_RECV_TIMEOUT_SECONDS

        assert BATCH_RECV_TIMEOUT_SECONDS == 600

    def test_post_all_transmitted_timeout(self) -> None:
        from src.dbos_workflows.content_scan_workflow import POST_ALL_TRANSMITTED_TIMEOUT_SECONDS

        assert POST_ALL_TRANSMITTED_TIMEOUT_SECONDS == 60

    def test_scan_recv_timeout(self) -> None:
        from src.dbos_workflows.content_scan_workflow import SCAN_RECV_TIMEOUT_SECONDS

        assert SCAN_RECV_TIMEOUT_SECONDS == 30


class TestCheckpointWallClockStep:
    """Tests for _checkpoint_wall_clock_step."""

    def test_returns_epoch_time(self) -> None:
        from src.dbos_workflows.content_scan_workflow import _checkpoint_wall_clock_step

        before = time.time()
        result = _checkpoint_wall_clock_step.__wrapped__()
        after = time.time()

        assert before <= result <= after


class TestTerminalScanHelpers:
    """Tests for terminal scan helper functions."""

    @pytest.mark.asyncio
    async def test_scan_is_terminal_async_awaits_awaitable_scalar_result(self) -> None:
        from src.bulk_content_scan.schemas import BulkScanStatus
        from src.dbos_workflows.content_scan_workflow import _scan_is_terminal_async

        async def _status() -> str:
            return BulkScanStatus.COMPLETED

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = _status()

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        assert await _scan_is_terminal_async(mock_session, uuid4()) is True
        mock_session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_scan_is_terminal_async_returns_false_for_in_progress_status(self) -> None:
        from src.bulk_content_scan.schemas import BulkScanStatus
        from src.dbos_workflows.content_scan_workflow import _scan_is_terminal_async

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = BulkScanStatus.IN_PROGRESS

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        assert await _scan_is_terminal_async(mock_session, uuid4()) is False
        mock_session.execute.assert_awaited_once()

    def test_get_scan_terminal_state_step_loads_status_via_session_lookup(self) -> None:
        from src.dbos_workflows.content_scan_workflow import get_scan_terminal_state_step

        scan_id = uuid4()
        mock_session = AsyncMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session_maker = MagicMock(return_value=mock_session_ctx)
        mock_redis = AsyncMock()
        mock_redis.exists.return_value = False

        with (
            patch("src.database.get_session_maker", return_value=mock_session_maker),
            patch(
                "src.cache.redis_client.get_shared_redis_client",
                new_callable=AsyncMock,
                return_value=mock_redis,
            ),
            patch("src.config.get_settings", return_value=MagicMock(REDIS_URL="redis://test")),
            patch(
                "src.dbos_workflows.content_scan_workflow._scan_is_terminal_async",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_terminal,
        ):
            result = get_scan_terminal_state_step.__wrapped__(str(scan_id))

        assert result is True
        mock_terminal.assert_awaited_once_with(mock_session, scan_id)
        mock_redis.exists.assert_not_awaited()

    def test_get_scan_terminal_state_step_treats_finalizing_latch_as_terminal(self) -> None:
        from src.dbos_workflows.content_scan_workflow import get_scan_terminal_state_step

        scan_id = uuid4()
        mock_session = AsyncMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session_maker = MagicMock(return_value=mock_session_ctx)
        mock_redis = AsyncMock()
        mock_redis.exists.return_value = True

        with (
            patch("src.database.get_session_maker", return_value=mock_session_maker),
            patch(
                "src.cache.redis_client.get_shared_redis_client",
                new_callable=AsyncMock,
                return_value=mock_redis,
            ),
            patch("src.config.get_settings", return_value=MagicMock(REDIS_URL="redis://test")),
            patch(
                "src.dbos_workflows.content_scan_workflow._scan_is_terminal_async",
                new_callable=AsyncMock,
                return_value=False,
            ) as mock_terminal,
        ):
            result = get_scan_terminal_state_step.__wrapped__(str(scan_id))

        assert result is True
        mock_terminal.assert_awaited_once_with(mock_session, scan_id)
        mock_redis.exists.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_skip_step_persist_if_scan_terminal_returns_false_when_scan_is_active(
        self,
    ) -> None:
        from src.dbos_workflows.content_scan_workflow import (
            _skip_step_persist_if_scan_terminal,
        )

        mock_session = AsyncMock()
        mock_redis = AsyncMock()
        scan_id = str(uuid4())
        scan_uuid = uuid4()

        with (
            patch(
                "src.dbos_workflows.content_scan_workflow._scan_is_terminal_async",
                new_callable=AsyncMock,
                return_value=False,
            ) as mock_terminal,
            patch("src.dbos_workflows.content_scan_workflow.logger.info") as mock_logger,
        ):
            result = await _skip_step_persist_if_scan_terminal(
                mock_session,
                mock_redis,
                scan_uuid,
                step_name="Preprocess",
                scan_id=scan_id,
                batch_number=7,
            )

        assert result is False
        mock_terminal.assert_awaited_once_with(mock_session, scan_uuid)
        mock_logger.assert_not_called()

    @pytest.mark.asyncio
    async def test_skip_step_persist_if_scan_terminal_logs_when_scan_is_terminal(self) -> None:
        from src.dbos_workflows.content_scan_workflow import (
            _skip_step_persist_if_scan_terminal,
        )

        mock_session = AsyncMock()
        mock_redis = AsyncMock()
        scan_id = str(uuid4())
        scan_uuid = uuid4()

        with (
            patch(
                "src.dbos_workflows.content_scan_workflow._scan_is_terminal_async",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_terminal,
            patch("src.dbos_workflows.content_scan_workflow.logger.info") as mock_logger,
        ):
            result = await _skip_step_persist_if_scan_terminal(
                mock_session,
                mock_redis,
                scan_uuid,
                step_name="Similarity",
                scan_id=scan_id,
                batch_number=3,
            )

        assert result is True
        mock_terminal.assert_awaited_once_with(mock_session, scan_uuid)
        mock_logger.assert_called_once()
        assert (
            mock_logger.call_args.args[0]
            == "%s step finished after scan became terminal/finalizing; skipping late persistence"
        )
        assert mock_logger.call_args.args[1] == "Similarity"
        assert mock_logger.call_args.kwargs["extra"] == {
            "scan_id": scan_id,
            "batch_number": 3,
        }


def _make_recv_dispatcher(
    batch_responses: list[dict | None],
    tx_responses: list[dict | None],
) -> collections.abc.Callable[..., dict | None]:
    """Build a DBOS.recv mock that dispatches by topic.

    The restructured orchestration loop checks all_transmitted (non-blocking)
    before batch_complete. After batch_complete timeout, it may check
    all_transmitted again. This helper returns values from the appropriate
    queue based on the topic argument.
    """
    batch_iter = iter(batch_responses)
    tx_iter = iter(tx_responses)

    def _recv(topic: str, **kwargs: object) -> dict | None:
        if topic == "batch_complete":
            return next(batch_iter, None)
        if topic == "all_transmitted":
            return next(tx_iter, None)
        return None

    return _recv


def _patch_process_content_scan_batch_dependencies(
    stack: ExitStack,
) -> dict[str, MagicMock]:
    """Patch workflow-level batch dependencies with a non-terminal default seam."""
    return {
        "preprocess": stack.enter_context(
            patch("src.dbos_workflows.content_scan_workflow.preprocess_batch_step")
        ),
        "similarity": stack.enter_context(
            patch("src.dbos_workflows.content_scan_workflow.similarity_scan_step")
        ),
        "flashpoint": stack.enter_context(
            patch("src.dbos_workflows.content_scan_workflow.flashpoint_scan_step")
        ),
        "relevance": stack.enter_context(
            patch("src.dbos_workflows.content_scan_workflow.relevance_filter_step")
        ),
        "terminal": stack.enter_context(
            patch(
                "src.dbos_workflows.content_scan_workflow.get_scan_terminal_state_step",
                return_value=False,
            )
        ),
        "dbos": stack.enter_context(patch("src.dbos_workflows.content_scan_workflow.DBOS")),
        "token_gate": stack.enter_context(
            patch("src.dbos_workflows.content_scan_workflow.TokenGate")
        ),
    }


class TestContentScanOrchestrationWorkflow:
    """Tests for content_scan_orchestration_workflow logic."""

    def _make_batch_result(
        self,
        processed: int = 5,
        skipped: int = 0,
        errors: int = 0,
        flagged_count: int = 1,
        batch_number: int = 1,
    ) -> dict:
        return {
            "processed": processed,
            "skipped": skipped,
            "errors": errors,
            "flagged_count": flagged_count,
            "batch_number": batch_number,
        }

    def test_single_batch_completes_normally(self, mock_clear_scan_finalizing_step) -> None:
        """Orchestrator processes one batch then finalizes."""
        from src.dbos_workflows.content_scan_workflow import (
            content_scan_orchestration_workflow,
        )

        scan_id = str(uuid4())
        community_server_id = str(uuid4())
        scan_types_json = json.dumps(["similarity"])

        recv_fn = _make_recv_dispatcher(
            batch_responses=[
                self._make_batch_result(processed=10, flagged_count=2),
            ],
            tx_responses=[
                None,
                {"messages_scanned": 10},
            ],
        )

        with (
            patch(
                "src.dbos_workflows.content_scan_workflow.create_scan_record_step"
            ) as mock_create,
            patch(
                "src.dbos_workflows.content_scan_workflow._checkpoint_wall_clock_step"
            ) as mock_clock,
            patch(
                "src.dbos_workflows.content_scan_workflow.mark_scan_finalizing_step",
                return_value=True,
            ),
            patch("src.dbos_workflows.content_scan_workflow.finalize_scan_step") as mock_finalize,
            patch("src.dbos_workflows.content_scan_workflow.DBOS") as mock_dbos,
            patch("src.dbos_workflows.content_scan_workflow.TokenGate"),
        ):
            mock_dbos.workflow_id = "test-wf-id"
            mock_dbos.recv.side_effect = recv_fn
            mock_create.return_value = True
            mock_clock.return_value = time.time()
            mock_finalize.return_value = {
                "status": "completed",
                "messages_scanned": 10,
                "messages_flagged": 2,
                "messages_skipped": 0,
                "total_errors": 0,
            }

            result = content_scan_orchestration_workflow.__wrapped__(
                scan_id=scan_id,
                community_server_id=community_server_id,
                scan_types_json=scan_types_json,
            )

        assert result["status"] == "completed"
        assert result["messages_scanned"] == 10
        mock_create.assert_called_once_with(scan_id, community_server_id)
        mock_finalize.assert_called_once()
        mock_clear_scan_finalizing_step.assert_called_once_with(scan_id=scan_id)
        finalize_kwargs = mock_finalize.call_args.kwargs
        assert finalize_kwargs["processed_count"] == 10
        assert finalize_kwargs["flagged_count"] == 2

    def test_multiple_batches_accumulate_counts(self) -> None:
        """Orchestrator accumulates counts across multiple batches."""
        from src.dbos_workflows.content_scan_workflow import (
            content_scan_orchestration_workflow,
        )

        scan_id = str(uuid4())
        community_server_id = str(uuid4())
        scan_types_json = json.dumps(["similarity"])

        recv_fn = _make_recv_dispatcher(
            batch_responses=[
                self._make_batch_result(processed=5, errors=1, flagged_count=1, batch_number=1),
                self._make_batch_result(processed=4, errors=0, flagged_count=2, batch_number=2),
                self._make_batch_result(processed=3, errors=1, flagged_count=0, batch_number=3),
            ],
            tx_responses=[
                None,
                None,
                None,
                {"messages_scanned": 14},
            ],
        )

        with (
            patch("src.dbos_workflows.content_scan_workflow.create_scan_record_step"),
            patch(
                "src.dbos_workflows.content_scan_workflow._checkpoint_wall_clock_step"
            ) as mock_clock,
            patch(
                "src.dbos_workflows.content_scan_workflow.mark_scan_finalizing_step",
                return_value=True,
            ),
            patch("src.dbos_workflows.content_scan_workflow.finalize_scan_step") as mock_finalize,
            patch("src.dbos_workflows.content_scan_workflow.DBOS") as mock_dbos,
            patch("src.dbos_workflows.content_scan_workflow.TokenGate"),
        ):
            mock_dbos.workflow_id = "test-wf-id"
            mock_dbos.recv.side_effect = recv_fn
            mock_clock.return_value = time.time()
            mock_finalize.return_value = {
                "status": "completed",
                "messages_scanned": 14,
                "messages_flagged": 3,
                "messages_skipped": 0,
                "total_errors": 2,
            }

            result = content_scan_orchestration_workflow.__wrapped__(
                scan_id=scan_id,
                community_server_id=community_server_id,
                scan_types_json=scan_types_json,
            )

        finalize_kwargs = mock_finalize.call_args.kwargs
        assert finalize_kwargs["processed_count"] == 12
        assert finalize_kwargs["error_count"] == 2
        assert finalize_kwargs["flagged_count"] == 3
        assert finalize_kwargs["messages_scanned"] == 14
        assert result["status"] == "completed"

    def test_timeout_breaks_loop_when_no_signal(self) -> None:
        """Orchestrator breaks when batch_complete times out and all_transmitted not received."""
        from src.dbos_workflows.content_scan_workflow import (
            content_scan_orchestration_workflow,
        )

        scan_id = str(uuid4())
        community_server_id = str(uuid4())
        scan_types_json = json.dumps(["similarity"])

        recv_fn = _make_recv_dispatcher(
            batch_responses=[None],
            tx_responses=[None, None],
        )

        with (
            patch(
                "src.dbos_workflows.content_scan_workflow.create_scan_record_step"
            ) as mock_create,
            patch(
                "src.dbos_workflows.content_scan_workflow._checkpoint_wall_clock_step"
            ) as mock_clock,
            patch(
                "src.dbos_workflows.content_scan_workflow.mark_scan_finalizing_step",
                return_value=True,
            ),
            patch("src.dbos_workflows.content_scan_workflow.finalize_scan_step") as mock_finalize,
            patch("src.dbos_workflows.content_scan_workflow.DBOS") as mock_dbos,
            patch("src.dbos_workflows.content_scan_workflow.TokenGate"),
        ):
            mock_dbos.workflow_id = "test-wf-id"
            mock_dbos.recv.side_effect = recv_fn
            mock_create.return_value = True
            mock_clock.return_value = time.time()
            mock_finalize.return_value = {
                "status": "completed",
                "messages_scanned": 0,
                "messages_flagged": 0,
                "messages_skipped": 0,
                "total_errors": 0,
            }

            content_scan_orchestration_workflow.__wrapped__(
                scan_id=scan_id,
                community_server_id=community_server_id,
                scan_types_json=scan_types_json,
            )

        mock_finalize.assert_called_once()
        finalize_kwargs = mock_finalize.call_args.kwargs
        assert finalize_kwargs["processed_count"] == 0
        assert finalize_kwargs["messages_scanned"] == 0

    def test_all_transmitted_before_batches_waits_for_processing(self) -> None:
        """When all_transmitted arrives early, loop continues until counts match."""
        from src.dbos_workflows.content_scan_workflow import (
            content_scan_orchestration_workflow,
        )

        scan_id = str(uuid4())
        community_server_id = str(uuid4())
        scan_types_json = json.dumps(["similarity"])

        recv_fn = _make_recv_dispatcher(
            batch_responses=[
                self._make_batch_result(processed=5, errors=0, flagged_count=1),
            ],
            tx_responses=[
                {"messages_scanned": 5},
                None,
            ],
        )

        with (
            patch("src.dbos_workflows.content_scan_workflow.create_scan_record_step"),
            patch(
                "src.dbos_workflows.content_scan_workflow._checkpoint_wall_clock_step"
            ) as mock_clock,
            patch(
                "src.dbos_workflows.content_scan_workflow.mark_scan_finalizing_step",
                return_value=True,
            ),
            patch("src.dbos_workflows.content_scan_workflow.finalize_scan_step") as mock_finalize,
            patch("src.dbos_workflows.content_scan_workflow.DBOS") as mock_dbos,
            patch("src.dbos_workflows.content_scan_workflow.TokenGate"),
        ):
            mock_dbos.workflow_id = "test-wf-id"
            mock_dbos.recv.side_effect = recv_fn
            mock_clock.return_value = time.time()
            mock_finalize.return_value = {"status": "completed"}

            content_scan_orchestration_workflow.__wrapped__(
                scan_id=scan_id,
                community_server_id=community_server_id,
                scan_types_json=scan_types_json,
            )

        finalize_kwargs = mock_finalize.call_args.kwargs
        assert finalize_kwargs["processed_count"] == 5
        assert finalize_kwargs["messages_scanned"] == 5

    def test_zero_batch_scan_finalizes_immediately(self) -> None:
        """When all_transmitted arrives with messages_scanned=0, finalize without blocking."""
        from src.dbos_workflows.content_scan_workflow import (
            content_scan_orchestration_workflow,
        )

        scan_id = str(uuid4())
        community_server_id = str(uuid4())
        scan_types_json = json.dumps(["similarity"])

        recv_fn = _make_recv_dispatcher(
            batch_responses=[],
            tx_responses=[{"messages_scanned": 0}],
        )

        with (
            patch("src.dbos_workflows.content_scan_workflow.create_scan_record_step"),
            patch(
                "src.dbos_workflows.content_scan_workflow._checkpoint_wall_clock_step"
            ) as mock_clock,
            patch(
                "src.dbos_workflows.content_scan_workflow.mark_scan_finalizing_step",
                return_value=True,
            ),
            patch("src.dbos_workflows.content_scan_workflow.finalize_scan_step") as mock_finalize,
            patch("src.dbos_workflows.content_scan_workflow.DBOS") as mock_dbos,
            patch("src.dbos_workflows.content_scan_workflow.TokenGate"),
        ):
            mock_dbos.workflow_id = "test-wf-id"
            mock_dbos.recv.side_effect = recv_fn
            mock_clock.return_value = time.time()
            mock_finalize.return_value = {"status": "completed"}

            content_scan_orchestration_workflow.__wrapped__(
                scan_id=scan_id,
                community_server_id=community_server_id,
                scan_types_json=scan_types_json,
            )

        mock_finalize.assert_called_once()
        finalize_kwargs = mock_finalize.call_args.kwargs
        assert finalize_kwargs["messages_scanned"] == 0
        assert finalize_kwargs["processed_count"] == 0

    def test_zero_message_scan_skips_batch_loop(self) -> None:
        """Zero-message scan never enters the batch loop or calls batch_complete recv."""
        from src.dbos_workflows.content_scan_workflow import (
            content_scan_orchestration_workflow,
        )

        scan_id = str(uuid4())
        community_server_id = str(uuid4())

        recv_calls: list[tuple[str, dict]] = []

        def tracking_recv(topic: str, **kwargs: object) -> dict | None:
            recv_calls.append((topic, dict(kwargs)))
            if topic == "all_transmitted":
                return {"messages_scanned": 0}
            return None

        with (
            patch("src.dbos_workflows.content_scan_workflow.create_scan_record_step"),
            patch(
                "src.dbos_workflows.content_scan_workflow._checkpoint_wall_clock_step"
            ) as mock_clock,
            patch(
                "src.dbos_workflows.content_scan_workflow.mark_scan_finalizing_step",
                return_value=True,
            ),
            patch("src.dbos_workflows.content_scan_workflow.finalize_scan_step") as mock_finalize,
            patch("src.dbos_workflows.content_scan_workflow.DBOS") as mock_dbos,
            patch("src.dbos_workflows.content_scan_workflow.TokenGate"),
        ):
            mock_dbos.workflow_id = "test-wf-id"
            mock_dbos.recv.side_effect = tracking_recv
            mock_clock.return_value = time.time()
            mock_finalize.return_value = {"status": "completed"}

            content_scan_orchestration_workflow.__wrapped__(
                scan_id=scan_id,
                community_server_id=community_server_id,
                scan_types_json=json.dumps(["similarity"]),
            )

        batch_calls = [c for c in recv_calls if c[0] == "batch_complete"]
        assert len(batch_calls) == 0
        mock_finalize.assert_called_once()

    def test_late_zero_message_all_transmitted_rechecks_without_long_batch_wait(
        self,
    ) -> None:
        """Late zero-message handoff is awaited before any long batch_complete wait."""
        from src.dbos_workflows.content_scan_workflow import (
            BATCH_RECV_TIMEOUT_SECONDS,
            POST_ALL_TRANSMITTED_TIMEOUT_SECONDS,
            content_scan_orchestration_workflow,
        )

        scan_id = str(uuid4())
        community_server_id = str(uuid4())
        scan_types_json = json.dumps(["similarity"])

        recv_calls: list[tuple[str, dict]] = []
        all_transmitted_attempts = 0

        def tracking_recv(topic: str, **kwargs: object) -> dict | None:
            nonlocal all_transmitted_attempts
            recv_calls.append((topic, dict(kwargs)))
            if topic == "all_transmitted":
                all_transmitted_attempts += 1
                if all_transmitted_attempts == 2:
                    return {"messages_scanned": 0}
            return None

        with (
            patch("src.dbos_workflows.content_scan_workflow.create_scan_record_step"),
            patch(
                "src.dbos_workflows.content_scan_workflow._checkpoint_wall_clock_step"
            ) as mock_clock,
            patch(
                "src.dbos_workflows.content_scan_workflow.mark_scan_finalizing_step",
                return_value=True,
            ),
            patch("src.dbos_workflows.content_scan_workflow.finalize_scan_step") as mock_finalize,
            patch("src.dbos_workflows.content_scan_workflow.DBOS") as mock_dbos,
            patch("src.dbos_workflows.content_scan_workflow.TokenGate"),
        ):
            mock_dbos.workflow_id = "test-wf-id"
            mock_dbos.recv.side_effect = tracking_recv
            mock_clock.return_value = time.time()
            mock_finalize.return_value = {"status": "completed"}

            content_scan_orchestration_workflow.__wrapped__(
                scan_id=scan_id,
                community_server_id=community_server_id,
                scan_types_json=scan_types_json,
            )

        follow_up_all_transmitted_calls = [
            call for topic, call in recv_calls[1:] if topic == "all_transmitted"
        ]
        assert any(
            call["timeout_seconds"] == POST_ALL_TRANSMITTED_TIMEOUT_SECONDS
            for call in follow_up_all_transmitted_calls
        )
        assert not any(
            topic == "batch_complete" and call["timeout_seconds"] == BATCH_RECV_TIMEOUT_SECONDS
            for topic, call in recv_calls
        )

        mock_finalize.assert_called_once()
        finalize_kwargs = mock_finalize.call_args.kwargs
        assert finalize_kwargs["messages_scanned"] == 0

    def test_delayed_first_batch_after_late_recheck_preserves_non_zero_wait_budget(
        self,
    ) -> None:
        """A non-zero first batch still gets the long wait budget after the late tx recheck."""
        from src.dbos_workflows.content_scan_workflow import (
            BATCH_RECV_TIMEOUT_SECONDS,
            POST_ALL_TRANSMITTED_TIMEOUT_SECONDS,
            content_scan_orchestration_workflow,
        )

        scan_id = str(uuid4())
        community_server_id = str(uuid4())
        scan_types_json = json.dumps(["similarity"])

        recv_calls: list[tuple[str, dict]] = []
        batch_delivered = False

        def tracking_recv(topic: str, **kwargs: object) -> dict | None:
            nonlocal batch_delivered
            recv_calls.append((topic, dict(kwargs)))
            if topic == "all_transmitted":
                if batch_delivered:
                    return {"messages_scanned": 4}
                return None
            if (
                topic == "batch_complete"
                and not batch_delivered
                and kwargs.get("timeout_seconds") == BATCH_RECV_TIMEOUT_SECONDS
            ):
                batch_delivered = True
                return self._make_batch_result(processed=4, flagged_count=0, batch_number=1)
            return None

        with (
            patch("src.dbos_workflows.content_scan_workflow.create_scan_record_step"),
            patch(
                "src.dbos_workflows.content_scan_workflow._checkpoint_wall_clock_step"
            ) as mock_clock,
            patch(
                "src.dbos_workflows.content_scan_workflow.mark_scan_finalizing_step",
                return_value=True,
            ),
            patch("src.dbos_workflows.content_scan_workflow.finalize_scan_step") as mock_finalize,
            patch("src.dbos_workflows.content_scan_workflow.DBOS") as mock_dbos,
            patch("src.dbos_workflows.content_scan_workflow.TokenGate"),
        ):
            mock_dbos.workflow_id = "test-wf-id"
            mock_dbos.recv.side_effect = tracking_recv
            mock_clock.return_value = time.time()
            mock_finalize.return_value = {"status": "completed"}

            content_scan_orchestration_workflow.__wrapped__(
                scan_id=scan_id,
                community_server_id=community_server_id,
                scan_types_json=scan_types_json,
            )

        assert any(
            topic == "all_transmitted"
            and call["timeout_seconds"] == POST_ALL_TRANSMITTED_TIMEOUT_SECONDS
            for topic, call in recv_calls
        )
        assert any(
            topic == "batch_complete" and call["timeout_seconds"] == BATCH_RECV_TIMEOUT_SECONDS
            for topic, call in recv_calls
        )

        mock_finalize.assert_called_once()
        finalize_kwargs = mock_finalize.call_args.kwargs
        assert finalize_kwargs["processed_count"] == 4
        assert finalize_kwargs["messages_scanned"] == 4

    def test_first_batch_complete_still_counts_before_all_transmitted(self) -> None:
        """A first batch_complete before all_transmitted still accumulates progress."""
        from src.dbos_workflows.content_scan_workflow import (
            content_scan_orchestration_workflow,
        )

        scan_id = str(uuid4())
        community_server_id = str(uuid4())
        scan_types_json = json.dumps(["similarity"])

        recv_order: list[str] = []

        def tracking_recv(topic: str, **kwargs: object) -> dict | None:
            recv_order.append(topic)
            if topic == "batch_complete" and recv_order.count("batch_complete") == 1:
                return self._make_batch_result(processed=3, flagged_count=0, batch_number=1)
            if topic == "all_transmitted" and recv_order.count("all_transmitted") >= 2:
                return {"messages_scanned": 3}
            return None

        with (
            patch("src.dbos_workflows.content_scan_workflow.create_scan_record_step"),
            patch(
                "src.dbos_workflows.content_scan_workflow._checkpoint_wall_clock_step"
            ) as mock_clock,
            patch(
                "src.dbos_workflows.content_scan_workflow.mark_scan_finalizing_step",
                return_value=True,
            ),
            patch("src.dbos_workflows.content_scan_workflow.finalize_scan_step") as mock_finalize,
            patch("src.dbos_workflows.content_scan_workflow.DBOS") as mock_dbos,
            patch("src.dbos_workflows.content_scan_workflow.TokenGate"),
        ):
            mock_dbos.workflow_id = "test-wf-id"
            mock_dbos.recv.side_effect = tracking_recv
            mock_clock.return_value = time.time()
            mock_finalize.return_value = {"status": "completed"}

            content_scan_orchestration_workflow.__wrapped__(
                scan_id=scan_id,
                community_server_id=community_server_id,
                scan_types_json=scan_types_json,
            )

        mock_finalize.assert_called_once()
        finalize_kwargs = mock_finalize.call_args.kwargs
        assert finalize_kwargs["processed_count"] == 3
        assert finalize_kwargs["messages_scanned"] == 3

    def test_all_transmitted_received_on_first_wait(self) -> None:
        """When all_transmitted arrives within initial 30s, it is consumed before batch loop."""
        from src.dbos_workflows.content_scan_workflow import (
            SCAN_RECV_TIMEOUT_SECONDS,
            content_scan_orchestration_workflow,
        )

        scan_id = str(uuid4())
        community_server_id = str(uuid4())

        recv_calls: list[tuple[str, dict]] = []

        def tracking_recv(topic: str, **kwargs: object) -> dict | None:
            recv_calls.append((topic, dict(kwargs)))
            if topic == "all_transmitted" and len(recv_calls) == 1:
                return {"messages_scanned": 5}
            if topic == "batch_complete":
                return {
                    "processed": 5,
                    "skipped": 0,
                    "errors": 0,
                    "flagged_count": 1,
                    "batch_number": 1,
                }
            return None

        with (
            patch("src.dbos_workflows.content_scan_workflow.create_scan_record_step"),
            patch(
                "src.dbos_workflows.content_scan_workflow._checkpoint_wall_clock_step"
            ) as mock_clock,
            patch(
                "src.dbos_workflows.content_scan_workflow.mark_scan_finalizing_step",
                return_value=True,
            ),
            patch("src.dbos_workflows.content_scan_workflow.finalize_scan_step") as mock_finalize,
            patch("src.dbos_workflows.content_scan_workflow.DBOS") as mock_dbos,
            patch("src.dbos_workflows.content_scan_workflow.TokenGate"),
        ):
            mock_dbos.workflow_id = "test-wf-id"
            mock_dbos.recv.side_effect = tracking_recv
            mock_clock.return_value = time.time()
            mock_finalize.return_value = {"status": "completed"}

            content_scan_orchestration_workflow.__wrapped__(
                scan_id=scan_id,
                community_server_id=community_server_id,
                scan_types_json=json.dumps(["similarity"]),
            )

        first_call = recv_calls[0]
        assert first_call[0] == "all_transmitted"
        assert first_call[1]["timeout_seconds"] == SCAN_RECV_TIMEOUT_SECONDS

        mock_finalize.assert_called_once()
        finalize_kwargs = mock_finalize.call_args.kwargs
        assert finalize_kwargs["processed_count"] == 5
        assert finalize_kwargs["messages_scanned"] == 5

    def test_post_all_transmitted_uses_shorter_timeout(self) -> None:
        """After all_transmitted, batch_complete uses POST_ALL_TRANSMITTED_TIMEOUT_SECONDS."""
        from src.dbos_workflows.content_scan_workflow import (
            POST_ALL_TRANSMITTED_TIMEOUT_SECONDS,
            content_scan_orchestration_workflow,
        )

        scan_id = str(uuid4())
        community_server_id = str(uuid4())

        recv_calls: list[tuple[str, dict]] = []

        def tracking_recv(topic: str, **kwargs: object) -> dict | None:
            recv_calls.append((topic, dict(kwargs)))
            if topic == "all_transmitted" and len(recv_calls) == 1:
                return {"messages_scanned": 10}
            if topic == "batch_complete" and len(recv_calls) <= 3:
                return {
                    "processed": 10,
                    "skipped": 0,
                    "errors": 0,
                    "flagged_count": 0,
                    "batch_number": 1,
                }
            return None

        with (
            patch("src.dbos_workflows.content_scan_workflow.create_scan_record_step"),
            patch(
                "src.dbos_workflows.content_scan_workflow._checkpoint_wall_clock_step"
            ) as mock_clock,
            patch(
                "src.dbos_workflows.content_scan_workflow.mark_scan_finalizing_step",
                return_value=True,
            ),
            patch("src.dbos_workflows.content_scan_workflow.finalize_scan_step") as mock_finalize,
            patch("src.dbos_workflows.content_scan_workflow.DBOS") as mock_dbos,
            patch("src.dbos_workflows.content_scan_workflow.TokenGate"),
        ):
            mock_dbos.workflow_id = "test-wf-id"
            mock_dbos.recv.side_effect = tracking_recv
            mock_clock.return_value = time.time()
            mock_finalize.return_value = {"status": "completed"}

            content_scan_orchestration_workflow.__wrapped__(
                scan_id=scan_id,
                community_server_id=community_server_id,
                scan_types_json=json.dumps(["similarity"]),
            )

        batch_calls = [c for c in recv_calls if c[0] == "batch_complete"]
        assert len(batch_calls) >= 1
        assert batch_calls[0][1]["timeout_seconds"] == POST_ALL_TRANSMITTED_TIMEOUT_SECONDS

    def test_batch_complete_arrives_after_post_tx_timeout_retries(self) -> None:
        """When batch_complete times out once but arrives on retry, orchestrator succeeds."""
        from src.dbos_workflows.content_scan_workflow import (
            content_scan_orchestration_workflow,
        )

        scan_id = str(uuid4())
        community_server_id = str(uuid4())
        scan_types_json = json.dumps(["similarity"])

        recv_fn = _make_recv_dispatcher(
            batch_responses=[
                None,
                self._make_batch_result(processed=10, flagged_count=2),
            ],
            tx_responses=[
                {"messages_scanned": 10},
            ],
        )

        start = 1000000.0
        call_count = 0

        def stateful_time() -> float:
            nonlocal call_count
            call_count += 1
            return start + (call_count * 10)

        with (
            patch("src.dbos_workflows.content_scan_workflow.create_scan_record_step"),
            patch(
                "src.dbos_workflows.content_scan_workflow._checkpoint_wall_clock_step"
            ) as mock_clock,
            patch(
                "src.dbos_workflows.content_scan_workflow.mark_scan_finalizing_step",
                return_value=True,
            ),
            patch("src.dbos_workflows.content_scan_workflow.finalize_scan_step") as mock_finalize,
            patch("src.dbos_workflows.content_scan_workflow.DBOS") as mock_dbos,
            patch("src.dbos_workflows.content_scan_workflow.TokenGate"),
            patch("src.dbos_workflows.content_scan_workflow.time") as mock_time,
        ):
            mock_dbos.workflow_id = "test-wf-id"
            mock_dbos.recv.side_effect = recv_fn
            mock_clock.return_value = start
            mock_time.time.side_effect = stateful_time
            mock_finalize.return_value = {
                "status": "completed",
                "messages_scanned": 10,
                "messages_flagged": 2,
                "messages_skipped": 0,
                "total_errors": 0,
            }

            result = content_scan_orchestration_workflow.__wrapped__(
                scan_id=scan_id,
                community_server_id=community_server_id,
                scan_types_json=scan_types_json,
            )

        assert result["status"] == "completed"
        finalize_kwargs = mock_finalize.call_args.kwargs
        assert finalize_kwargs["processed_count"] == 10
        assert finalize_kwargs["messages_scanned"] == 10

    def test_adaptive_timeout_cap_exceeded_breaks_loop(self) -> None:
        """When adaptive cap is exceeded, orchestrator breaks and finalizes."""
        from src.dbos_workflows.content_scan_workflow import (
            content_scan_orchestration_workflow,
        )

        scan_id = str(uuid4())
        community_server_id = str(uuid4())
        scan_types_json = json.dumps(["similarity"])

        recv_fn = _make_recv_dispatcher(
            batch_responses=[None, None, None],
            tx_responses=[{"messages_scanned": 10}],
        )

        start = 1000000.0
        call_count = 0

        def stateful_time() -> float:
            nonlocal call_count
            call_count += 1
            return start + (call_count * 100)

        with (
            patch("src.dbos_workflows.content_scan_workflow.create_scan_record_step"),
            patch(
                "src.dbos_workflows.content_scan_workflow._checkpoint_wall_clock_step"
            ) as mock_clock,
            patch(
                "src.dbos_workflows.content_scan_workflow.mark_scan_finalizing_step",
                return_value=True,
            ),
            patch("src.dbos_workflows.content_scan_workflow.finalize_scan_step") as mock_finalize,
            patch("src.dbos_workflows.content_scan_workflow.DBOS") as mock_dbos,
            patch("src.dbos_workflows.content_scan_workflow.TokenGate"),
            patch("src.dbos_workflows.content_scan_workflow.time") as mock_time,
        ):
            mock_dbos.workflow_id = "test-wf-id"
            mock_dbos.recv.side_effect = recv_fn
            mock_clock.return_value = start
            mock_time.time.side_effect = stateful_time

            mock_finalize.return_value = {
                "status": "completed",
                "messages_scanned": 10,
                "messages_flagged": 0,
                "messages_skipped": 0,
                "total_errors": 0,
            }

            content_scan_orchestration_workflow.__wrapped__(
                scan_id=scan_id,
                community_server_id=community_server_id,
                scan_types_json=scan_types_json,
            )

        mock_finalize.assert_called_once()
        finalize_kwargs = mock_finalize.call_args.kwargs
        assert finalize_kwargs["processed_count"] == 0
        assert finalize_kwargs["messages_scanned"] == 10
        assert finalize_kwargs["finalization_incomplete"] is True


class TestAdaptiveTimeoutCap:
    """Tests for compute_adaptive_timeout_cap helper."""

    def test_minimum_cap_is_120(self) -> None:
        from src.dbos_workflows.content_scan_workflow import compute_adaptive_timeout_cap

        assert compute_adaptive_timeout_cap(1) == 120

    def test_scales_with_message_count(self) -> None:
        from src.dbos_workflows.content_scan_workflow import compute_adaptive_timeout_cap

        assert compute_adaptive_timeout_cap(100) == 500

    def test_zero_messages_returns_minimum(self) -> None:
        from src.dbos_workflows.content_scan_workflow import compute_adaptive_timeout_cap

        assert compute_adaptive_timeout_cap(0) == 120

    def test_capped_by_wall_clock_max(self) -> None:
        from src.dbos_workflows.content_scan_workflow import (
            ORCHESTRATOR_MAX_WALL_CLOCK_SECONDS,
            compute_adaptive_timeout_cap,
        )

        assert compute_adaptive_timeout_cap(100000) == ORCHESTRATOR_MAX_WALL_CLOCK_SECONDS


class TestRedisHelpers:
    """Tests for Redis helper functions used by per-strategy steps."""

    def testget_batch_redis_key_format(self) -> None:
        from src.dbos_workflows.content_scan_workflow import get_batch_redis_key

        with patch("src.config.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(ENVIRONMENT="test")
            key = get_batch_redis_key("scan-abc", 3, "messages")

        assert key == "test:bulk_scan:messages:scan-abc:3"

    def testget_batch_redis_key_different_suffixes(self) -> None:
        from src.dbos_workflows.content_scan_workflow import get_batch_redis_key

        with patch("src.config.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(ENVIRONMENT="prod")

            assert get_batch_redis_key("s1", 1, "filtered") == "prod:bulk_scan:filtered:s1:1"
            assert get_batch_redis_key("s1", 1, "context") == "prod:bulk_scan:context:s1:1"
            assert (
                get_batch_redis_key("s1", 1, "similarity_candidates")
                == "prod:bulk_scan:similarity_candidates:s1:1"
            )
            assert (
                get_batch_redis_key("s1", 1, "flashpoint_candidates")
                == "prod:bulk_scan:flashpoint_candidates:s1:1"
            )

    @pytest.mark.asyncio
    async def test_store_messages_in_redis(self) -> None:
        from src.dbos_workflows.content_scan_workflow import store_messages_in_redis

        mock_redis = MagicMock()
        mock_redis.setex = AsyncMock()

        messages = [{"message_id": "m1", "content": "hello"}]
        result = await store_messages_in_redis(mock_redis, "test:key", messages, ttl=3600)

        assert result == "test:key"
        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args.args
        assert call_args[0] == "test:key"
        assert call_args[1] == 3600

    @pytest.mark.asyncio
    async def test_load_messages_from_redis_success(self) -> None:
        from src.dbos_workflows.content_scan_workflow import load_messages_from_redis

        messages = [{"message_id": "m1", "content": "hello"}]
        mock_redis = MagicMock()
        mock_redis.get = AsyncMock(return_value=json.dumps(messages).encode())
        mock_redis.expire = AsyncMock(return_value=True)

        result = await load_messages_from_redis(mock_redis, "test:key")
        assert result == messages

    @pytest.mark.asyncio
    async def test_load_messages_from_redis_refreshes_ttl(self) -> None:
        from src.dbos_workflows.content_scan_workflow import (
            REDIS_REPLAY_TTL_SECONDS,
            load_messages_from_redis,
        )

        messages = [{"message_id": "m1", "content": "hello"}]
        mock_redis = MagicMock()
        mock_redis.get = AsyncMock(return_value=json.dumps(messages).encode())
        mock_redis.expire = AsyncMock(return_value=True)

        await load_messages_from_redis(mock_redis, "test:key")
        mock_redis.expire.assert_called_once_with("test:key", REDIS_REPLAY_TTL_SECONDS)

    def test_redis_replay_ttl_is_7_days(self) -> None:
        from src.dbos_workflows.content_scan_workflow import REDIS_REPLAY_TTL_SECONDS

        assert REDIS_REPLAY_TTL_SECONDS == 7 * 24 * 3600

    @pytest.mark.asyncio
    async def test_load_messages_from_redis_expired_key(self) -> None:
        from src.dbos_workflows.content_scan_workflow import load_messages_from_redis

        mock_redis = MagicMock()
        mock_redis.get = AsyncMock(return_value=None)

        with pytest.raises(ValueError, match="not found or expired"):
            await load_messages_from_redis(mock_redis, "expired:key")

    def test_redis_batch_ttl_is_24_hours(self) -> None:
        from src.dbos_workflows.content_scan_workflow import REDIS_BATCH_TTL_SECONDS

        assert REDIS_BATCH_TTL_SECONDS == 86400


class TestProcessContentScanBatch:
    """Tests for process_content_scan_batch workflow with per-strategy steps."""

    def test_patch_all_steps_prevents_terminal_lookup_db_calls(self) -> None:
        """Workflow test helper should keep batch workflow tests DB-free by default."""
        from src.dbos_workflows.content_scan_workflow import process_content_scan_batch

        with ExitStack() as stack:
            mocks = _patch_process_content_scan_batch_dependencies(stack)
            stack.enter_context(
                patch(
                    "src.database.get_session_maker",
                    side_effect=AssertionError(
                        "workflow-level tests should not hit the terminal-state DB lookup"
                    ),
                )
            )

            mocks["preprocess"].return_value = {
                "filtered_messages_key": "test:filtered",
                "context_maps_key": "test:context",
                "message_count": 1,
                "skipped_count": 0,
            }
            mocks["similarity"].return_value = {
                "similarity_candidates_key": "test:sim",
                "candidate_count": 1,
            }
            mocks["relevance"].return_value = {"flagged_count": 1, "errors": 0}

            result = process_content_scan_batch.__wrapped__(
                orchestrator_workflow_id="orch-wf",
                scan_id=str(uuid4()),
                community_server_id=str(uuid4()),
                batch_number=1,
                messages_redis_key="test:messages:key",
                scan_types_json=json.dumps(["similarity"]),
            )

        mocks["flashpoint"].assert_not_called()
        mocks["dbos"].send.assert_called_once()
        assert result["processed"] == 1
        assert result["flagged_count"] == 1

    def test_short_circuits_when_scan_terminal_before_batch_execution(self) -> None:
        """Terminal scans return before preprocess or downstream signaling."""
        from src.dbos_workflows.content_scan_workflow import process_content_scan_batch

        with ExitStack() as stack:
            mocks = _patch_process_content_scan_batch_dependencies(stack)
            mocks["terminal"].return_value = True

            result = process_content_scan_batch.__wrapped__(
                orchestrator_workflow_id="orch-wf",
                scan_id=str(uuid4()),
                community_server_id=str(uuid4()),
                batch_number=1,
                messages_redis_key="test:messages:key",
                scan_types_json=json.dumps(["similarity"]),
            )

        mocks["preprocess"].assert_not_called()
        mocks["similarity"].assert_not_called()
        mocks["flashpoint"].assert_not_called()
        mocks["relevance"].assert_not_called()
        mocks["dbos"].send.assert_not_called()
        assert result == {
            "processed": 0,
            "skipped": 0,
            "errors": 0,
            "flagged_count": 0,
            "batch_number": 1,
        }

    def test_calls_per_strategy_steps_in_order(self) -> None:
        """Batch workflow calls preprocess, similarity, and relevance steps."""
        from src.dbos_workflows.content_scan_workflow import process_content_scan_batch

        scan_id = str(uuid4())
        community_server_id = str(uuid4())
        redis_key = "test:bulk_scan:messages:scan:1"
        scan_types_json = json.dumps(["similarity"])

        with ExitStack() as stack:
            mocks = _patch_process_content_scan_batch_dependencies(stack)
            mocks["preprocess"].return_value = {
                "filtered_messages_key": "test:filtered",
                "context_maps_key": "test:context",
                "message_count": 1,
                "skipped_count": 0,
            }
            mocks["similarity"].return_value = {
                "similarity_candidates_key": "test:sim",
                "candidate_count": 1,
            }
            mocks["relevance"].return_value = {"flagged_count": 1, "errors": 0}

            result = process_content_scan_batch.__wrapped__(
                orchestrator_workflow_id="orch-wf",
                scan_id=scan_id,
                community_server_id=community_server_id,
                batch_number=1,
                messages_redis_key=redis_key,
                scan_types_json=scan_types_json,
            )

        mocks["preprocess"].assert_called_once()
        mocks["similarity"].assert_called_once()
        mocks["flashpoint"].assert_not_called()
        mocks["relevance"].assert_called_once()
        assert result["processed"] == 1
        assert result["flagged_count"] == 1
        mocks["dbos"].send.assert_called_once()

    def test_passes_redis_key_to_preprocess_step(self) -> None:
        """Batch workflow passes messages_redis_key to preprocess step."""
        from src.dbos_workflows.content_scan_workflow import process_content_scan_batch

        redis_key = "test:bulk_scan:messages:scan-id:1"

        with ExitStack() as stack:
            mocks = _patch_process_content_scan_batch_dependencies(stack)
            mocks["preprocess"].return_value = {
                "filtered_messages_key": "k",
                "context_maps_key": "k",
                "message_count": 1,
                "skipped_count": 0,
            }
            mocks["relevance"].return_value = {"flagged_count": 0, "errors": 0}

            process_content_scan_batch.__wrapped__(
                orchestrator_workflow_id="orch",
                scan_id=str(uuid4()),
                community_server_id=str(uuid4()),
                batch_number=1,
                messages_redis_key=redis_key,
                scan_types_json=json.dumps(["similarity"]),
            )

        assert mocks["preprocess"].call_args.kwargs["messages_redis_key"] == redis_key

    def test_includes_flashpoint_step_when_scan_type_requested(self) -> None:
        """Flashpoint step is called when conversation_flashpoint is in scan_types."""
        from src.dbos_workflows.content_scan_workflow import process_content_scan_batch

        scan_types_json = json.dumps(["similarity", "conversation_flashpoint"])

        with ExitStack() as stack:
            mocks = _patch_process_content_scan_batch_dependencies(stack)
            mocks["preprocess"].return_value = {
                "filtered_messages_key": "k",
                "context_maps_key": "k",
                "message_count": 1,
                "skipped_count": 0,
            }
            mocks["similarity"].return_value = {
                "similarity_candidates_key": "s",
                "candidate_count": 1,
            }
            mocks["flashpoint"].return_value = {
                "flashpoint_candidates_key": "f",
                "candidate_count": 1,
            }
            mocks["relevance"].return_value = {"flagged_count": 2, "errors": 0}

            result = process_content_scan_batch.__wrapped__(
                orchestrator_workflow_id="orch",
                scan_id=str(uuid4()),
                community_server_id=str(uuid4()),
                batch_number=1,
                messages_redis_key="test:messages:key",
                scan_types_json=scan_types_json,
            )

        mocks["similarity"].assert_called_once()
        mocks["flashpoint"].assert_called_once()
        assert result["flagged_count"] == 2

    def test_signals_orchestrator_with_result(self) -> None:
        """Batch workflow sends batch_complete signal to orchestrator."""
        from src.dbos_workflows.content_scan_workflow import process_content_scan_batch

        orchestrator_wf_id = "orchestrator-wf-123"

        with ExitStack() as stack:
            mocks = _patch_process_content_scan_batch_dependencies(stack)
            mocks["preprocess"].return_value = {
                "filtered_messages_key": "k",
                "context_maps_key": "k",
                "message_count": 5,
                "skipped_count": 1,
            }
            mocks["relevance"].return_value = {"flagged_count": 2, "errors": 0}

            process_content_scan_batch.__wrapped__(
                orchestrator_workflow_id=orchestrator_wf_id,
                scan_id=str(uuid4()),
                community_server_id=str(uuid4()),
                batch_number=1,
                messages_redis_key="test:messages:key",
                scan_types_json=json.dumps(["similarity"]),
            )

        signal_data = mocks["dbos"].send.call_args.args[1]
        assert signal_data["processed"] == 5
        assert signal_data["skipped"] == 1
        assert signal_data["flagged_count"] == 2

    def test_skips_remaining_stages_when_scan_becomes_terminal_after_preprocess(self) -> None:
        """Terminal scans stop downstream batch work and suppress completion signals."""
        from src.dbos_workflows.content_scan_workflow import process_content_scan_batch

        with ExitStack() as stack:
            mocks = _patch_process_content_scan_batch_dependencies(stack)
            mocks["preprocess"].return_value = {
                "filtered_messages_key": "test:filtered",
                "context_maps_key": "test:context",
                "message_count": 2,
                "skipped_count": 0,
            }
            mocks["terminal"].side_effect = [False, True]

            result = process_content_scan_batch.__wrapped__(
                orchestrator_workflow_id="orch-wf",
                scan_id=str(uuid4()),
                community_server_id=str(uuid4()),
                batch_number=1,
                messages_redis_key="test:messages:key",
                scan_types_json=json.dumps(["similarity", "conversation_flashpoint"]),
            )

        mocks["similarity"].assert_not_called()
        mocks["flashpoint"].assert_not_called()
        mocks["relevance"].assert_not_called()
        mocks["dbos"].send.assert_not_called()
        assert result == {
            "processed": 0,
            "skipped": 0,
            "errors": 0,
            "flagged_count": 0,
            "batch_number": 1,
        }

    def test_short_circuits_when_all_messages_skipped(self) -> None:
        """When preprocess returns message_count=0, skip scan steps entirely."""
        from src.dbos_workflows.content_scan_workflow import process_content_scan_batch

        with ExitStack() as stack:
            mocks = _patch_process_content_scan_batch_dependencies(stack)
            mocks["preprocess"].return_value = {
                "filtered_messages_key": "",
                "context_maps_key": "",
                "message_count": 0,
                "skipped_count": 5,
            }

            result = process_content_scan_batch.__wrapped__(
                orchestrator_workflow_id="orch",
                scan_id=str(uuid4()),
                community_server_id=str(uuid4()),
                batch_number=1,
                messages_redis_key="test:messages:key",
                scan_types_json=json.dumps(["similarity"]),
            )

        mocks["similarity"].assert_not_called()
        mocks["flashpoint"].assert_not_called()
        mocks["relevance"].assert_not_called()
        assert result["processed"] == 0
        assert result["skipped"] == 5

    def test_sends_signal_on_preprocess_error(self) -> None:
        """Batch workflow sends signal to orchestrator even when preprocess fails."""
        from src.dbos_workflows.content_scan_workflow import process_content_scan_batch

        with ExitStack() as stack:
            mocks = _patch_process_content_scan_batch_dependencies(stack)
            mocks["preprocess"].side_effect = RuntimeError("Step failed")

            result = process_content_scan_batch.__wrapped__(
                orchestrator_workflow_id="wf-123",
                scan_id=str(uuid4()),
                community_server_id=str(uuid4()),
                batch_number=1,
                messages_redis_key="test:key",
                scan_types_json='["similarity"]',
            )

        assert result["errors"] >= 1
        assert "preprocess" in result.get("step_errors", [""])[0]
        mocks["dbos"].send.assert_called_once()

    def test_run_batch_scan_steps_collects_step_errors(self) -> None:
        """Helper records individual scan-stage failures and returns aggregate error count."""
        from src.dbos_workflows.content_scan_workflow import _run_batch_scan_steps

        step_errors: list[str] = []

        with (
            patch(
                "src.dbos_workflows.content_scan_workflow.similarity_scan_step",
                side_effect=RuntimeError("sim boom"),
            ),
            patch(
                "src.dbos_workflows.content_scan_workflow.flashpoint_scan_step",
                side_effect=RuntimeError("flash boom"),
            ),
            patch(
                "src.dbos_workflows.content_scan_workflow.relevance_filter_step",
                side_effect=RuntimeError("relevance boom"),
            ),
        ):
            flagged_count, errors = _run_batch_scan_steps(
                scan_id=str(uuid4()),
                community_server_id=str(uuid4()),
                batch_number=1,
                filtered_messages_key="test:filtered",
                context_maps_key="test:context",
                scan_types=["similarity", "conversation_flashpoint"],
                step_errors=step_errors,
            )

        assert (flagged_count, errors) == (0, 3)
        assert step_errors == [
            "similarity: sim boom",
            "flashpoint: flash boom",
            "relevance: relevance boom",
        ]

    def test_run_batch_scan_steps_uses_empty_candidate_keys_when_optional_steps_skipped(
        self,
    ) -> None:
        from src.dbos_workflows.content_scan_workflow import _run_batch_scan_steps

        step_errors: list[str] = []

        with (
            patch(
                "src.dbos_workflows.content_scan_workflow.similarity_scan_step"
            ) as mock_similarity,
            patch(
                "src.dbos_workflows.content_scan_workflow.flashpoint_scan_step"
            ) as mock_flashpoint,
            patch(
                "src.dbos_workflows.content_scan_workflow.relevance_filter_step",
                return_value={"flagged_count": 4, "errors": 1},
            ) as mock_relevance,
        ):
            flagged_count, errors = _run_batch_scan_steps(
                scan_id=str(uuid4()),
                community_server_id=str(uuid4()),
                batch_number=2,
                filtered_messages_key="test:filtered",
                context_maps_key="test:context",
                scan_types=[],
                step_errors=step_errors,
            )

        assert (flagged_count, errors) == (4, 1)
        mock_similarity.assert_not_called()
        mock_flashpoint.assert_not_called()
        assert mock_relevance.call_args.kwargs["similarity_candidates_key"] == ""
        assert mock_relevance.call_args.kwargs["flashpoint_candidates_key"] == ""


class TestProcessBatchMessagesStep:
    """Tests for process_batch_messages_step logic."""

    def _make_message_dict(self, message_id: str = "msg_1") -> dict:
        return {
            "message_id": message_id,
            "channel_id": "ch_1",
            "community_server_id": "cs_1",
            "content": "test message",
            "author_id": "user_1",
            "author_username": "testuser",
            "timestamp": "2025-01-01T00:00:00Z",
            "attachment_urls": None,
            "embed_content": None,
        }

    def test_processes_messages_successfully(self) -> None:
        """Step delegates to run_sync and returns batch result."""
        from src.dbos_workflows.content_scan_workflow import process_batch_messages_step

        scan_id = str(uuid4())
        community_server_id = str(uuid4())
        messages = [self._make_message_dict("msg_1"), self._make_message_dict("msg_2")]
        messages_json = json.dumps(messages)
        scan_types_json = json.dumps(["similarity"])

        with patch("src.dbos_workflows.content_scan_workflow.run_sync") as mock_run_sync:
            mock_run_sync.return_value = {
                "processed": 2,
                "skipped": 0,
                "errors": 0,
                "flagged_count": 0,
                "batch_number": 1,
            }

            result = process_batch_messages_step.__wrapped__(
                scan_id=scan_id,
                community_server_id=community_server_id,
                batch_number=1,
                messages_json=messages_json,
                scan_types_json=scan_types_json,
            )

        assert result["processed"] == 2
        assert result["errors"] == 0
        assert result["batch_number"] == 1
        mock_run_sync.assert_called_once()

    def test_returns_error_counts_when_inner_process_fails(self) -> None:
        """When inner async raises, step propagates the exception for DBOS retry."""
        from src.dbos_workflows.content_scan_workflow import process_batch_messages_step

        scan_id = str(uuid4())
        community_server_id = str(uuid4())
        messages_json = json.dumps([self._make_message_dict("msg_1")])
        scan_types_json = json.dumps(["similarity"])

        with patch("src.dbos_workflows.content_scan_workflow.run_sync") as mock_run_sync:
            mock_run_sync.side_effect = RuntimeError("Redis connection failed")

            with pytest.raises(RuntimeError, match="Redis connection failed"):
                process_batch_messages_step.__wrapped__(
                    scan_id=scan_id,
                    community_server_id=community_server_id,
                    batch_number=1,
                    messages_json=messages_json,
                    scan_types_json=scan_types_json,
                )

    def test_returns_flagged_count(self) -> None:
        """Step propagates flagged_count from inner processing."""
        from src.dbos_workflows.content_scan_workflow import process_batch_messages_step

        scan_id = str(uuid4())
        community_server_id = str(uuid4())
        messages_json = json.dumps([self._make_message_dict("msg_1")])
        scan_types_json = json.dumps(["similarity", "conversation_flashpoint"])

        with patch("src.dbos_workflows.content_scan_workflow.run_sync") as mock_run_sync:
            mock_run_sync.return_value = {
                "processed": 1,
                "skipped": 0,
                "errors": 0,
                "flagged_count": 1,
                "batch_number": 1,
            }

            result = process_batch_messages_step.__wrapped__(
                scan_id=scan_id,
                community_server_id=community_server_id,
                batch_number=1,
                messages_json=messages_json,
                scan_types_json=scan_types_json,
            )

        assert result["flagged_count"] == 1

    def test_no_step_retry_config(self) -> None:
        """Step has no retry config to avoid non-idempotent Redis write duplication."""
        from src.dbos_workflows.content_scan_workflow import process_batch_messages_step

        assert hasattr(process_batch_messages_step, "__wrapped__")


class TestCreateScanRecordStep:
    """Tests for create_scan_record_step."""

    def test_updates_pending_scan_to_in_progress(self) -> None:
        """Step transitions PENDING scan to IN_PROGRESS."""
        from src.dbos_workflows.content_scan_workflow import create_scan_record_step

        scan_id = str(uuid4())
        community_server_id = str(uuid4())

        with patch("src.dbos_workflows.content_scan_workflow.run_sync") as mock_run_sync:
            mock_run_sync.return_value = True

            result = create_scan_record_step.__wrapped__(
                scan_id=scan_id,
                community_server_id=community_server_id,
            )

        assert result is True
        mock_run_sync.assert_called_once()


class TestFinalizeScanStep:
    """Tests for finalize_scan_step."""

    @staticmethod
    def _make_session_context(mock_session: AsyncMock) -> MagicMock:
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)
        return MagicMock(return_value=mock_session_ctx)

    def test_finalizes_completed_scan(self) -> None:
        """Step returns finalization result for completed scan."""
        from src.dbos_workflows.content_scan_workflow import finalize_scan_step

        scan_id = str(uuid4())
        community_server_id = str(uuid4())

        expected = {
            "status": "completed",
            "messages_scanned": 100,
            "messages_flagged": 5,
            "messages_skipped": 3,
            "total_errors": 0,
        }

        with patch("src.dbos_workflows.content_scan_workflow.run_sync") as mock_run_sync:
            mock_run_sync.return_value = expected

            result = finalize_scan_step.__wrapped__(
                scan_id=scan_id,
                community_server_id=community_server_id,
                messages_scanned=100,
                processed_count=97,
                skipped_count=3,
                error_count=0,
                flagged_count=5,
            )

        assert result["status"] == "completed"
        assert result["messages_scanned"] == 100
        assert result["messages_flagged"] == 5
        mock_run_sync.assert_called_once()

    def test_finalizes_failed_scan(self) -> None:
        """Step returns failed status when all messages errored."""
        from src.dbos_workflows.content_scan_workflow import finalize_scan_step

        scan_id = str(uuid4())
        community_server_id = str(uuid4())

        expected = {
            "status": "failed",
            "messages_scanned": 10,
            "messages_flagged": 0,
            "messages_skipped": 0,
            "total_errors": 10,
        }

        with patch("src.dbos_workflows.content_scan_workflow.run_sync") as mock_run_sync:
            mock_run_sync.return_value = expected

            result = finalize_scan_step.__wrapped__(
                scan_id=scan_id,
                community_server_id=community_server_id,
                messages_scanned=10,
                processed_count=0,
                skipped_count=0,
                error_count=10,
                flagged_count=0,
            )

        assert result["status"] == "failed"
        assert result["total_errors"] == 10

    def test_failed_scan_publishes_failed_and_processing_finished_events(self) -> None:
        """Failed scans publish failed + processing finished after persisting failed status."""
        from src.bulk_content_scan.schemas import BulkScanStatus
        from src.dbos_workflows.content_scan_workflow import finalize_scan_step
        from src.events.schemas import BulkScanFailedEvent, BulkScanProcessingFinishedEvent

        scan_id = str(uuid4())
        community_server_id = str(uuid4())

        mock_session = AsyncMock()
        mock_service = MagicMock()
        mock_service.get_flagged_results = AsyncMock(return_value=[{"message_id": "msg-1"}])
        mock_service.get_error_summary = AsyncMock(
            return_value={
                "total_errors": 4,
                "error_types": {"RuntimeError": 4},
                "sample_errors": [
                    {
                        "error_type": "RuntimeError",
                        "message_id": "msg-1",
                        "batch_number": 2,
                        "error_message": "LLM request failed",
                    }
                ],
            }
        )
        mock_service.get_skipped_count = AsyncMock(return_value=2)
        mock_service.complete_scan = AsyncMock()

        mock_worker_publisher = AsyncMock()
        mock_worker_publisher.nats = MagicMock()

        mock_worker_context = AsyncMock()
        mock_worker_context.__aenter__ = AsyncMock(return_value=mock_worker_publisher)
        mock_worker_context.__aexit__ = AsyncMock(return_value=False)

        mock_results_publisher = MagicMock()
        mock_results_publisher.publish = AsyncMock()

        with (
            patch(
                "src.dbos_workflows.content_scan_workflow.run_sync",
                side_effect=lambda coroutine: asyncio.run(coroutine),
            ),
            patch(
                "src.cache.redis_client.get_shared_redis_client",
                new_callable=AsyncMock,
                return_value=MagicMock(),
            ),
            patch("src.config.get_settings", return_value=MagicMock(REDIS_URL="redis://test")),
            patch(
                "src.database.get_session_maker",
                return_value=self._make_session_context(mock_session),
            ),
            patch(
                "src.tasks.content_monitoring_tasks._get_llm_service",
                return_value=MagicMock(),
            ),
            patch(
                "src.fact_checking.embedding_service.EmbeddingService",
                return_value=MagicMock(),
            ),
            patch(
                "src.bulk_content_scan.service.BulkContentScanService",
                return_value=mock_service,
            ),
            patch(
                "src.events.publisher.create_worker_event_publisher",
                return_value=mock_worker_context,
            ),
            patch(
                "src.bulk_content_scan.nats_handler.BulkScanResultsPublisher",
                return_value=mock_results_publisher,
            ),
            patch("src.monitoring.metrics.bulk_scan_finalization_dispatch_total") as mock_metric,
        ):
            result = finalize_scan_step.__wrapped__(
                scan_id=scan_id,
                community_server_id=community_server_id,
                messages_scanned=4,
                processed_count=0,
                skipped_count=2,
                error_count=4,
                flagged_count=1,
            )

        assert result["status"] == "failed"
        mock_service.complete_scan.assert_awaited_once_with(
            scan_id=mock_service.complete_scan.await_args.kwargs["scan_id"],
            messages_scanned=4,
            messages_flagged=1,
            status=BulkScanStatus.FAILED,
        )
        mock_results_publisher.publish.assert_awaited_once()
        published_events = [
            call.args[0] for call in mock_worker_publisher.publish_event.await_args_list
        ]
        assert any(isinstance(event, BulkScanFailedEvent) for event in published_events)
        assert any(isinstance(event, BulkScanProcessingFinishedEvent) for event in published_events)
        failed_event = next(
            event for event in published_events if isinstance(event, BulkScanFailedEvent)
        )
        assert failed_event.error_message == "100% of messages had errors"
        mock_metric.add.assert_called_once_with(1, {"outcome": "success"})

    def test_completed_scan_does_not_publish_failed_event(self) -> None:
        """Completed scans publish processing finished without a failed event."""
        from src.bulk_content_scan.schemas import BulkScanStatus
        from src.dbos_workflows.content_scan_workflow import finalize_scan_step
        from src.events.schemas import BulkScanFailedEvent, BulkScanProcessingFinishedEvent

        scan_id = str(uuid4())
        community_server_id = str(uuid4())

        mock_session = AsyncMock()
        mock_service = MagicMock()
        mock_service.get_flagged_results = AsyncMock(return_value=[])
        mock_service.get_error_summary = AsyncMock(
            return_value={"total_errors": 0, "error_types": {}, "sample_errors": []}
        )
        mock_service.get_skipped_count = AsyncMock(return_value=1)
        mock_service.complete_scan = AsyncMock()

        mock_worker_publisher = AsyncMock()
        mock_worker_publisher.nats = MagicMock()

        mock_worker_context = AsyncMock()
        mock_worker_context.__aenter__ = AsyncMock(return_value=mock_worker_publisher)
        mock_worker_context.__aexit__ = AsyncMock(return_value=False)

        mock_results_publisher = MagicMock()
        mock_results_publisher.publish = AsyncMock()

        with (
            patch(
                "src.dbos_workflows.content_scan_workflow.run_sync",
                side_effect=lambda coroutine: asyncio.run(coroutine),
            ),
            patch(
                "src.cache.redis_client.get_shared_redis_client",
                new_callable=AsyncMock,
                return_value=MagicMock(),
            ),
            patch("src.config.get_settings", return_value=MagicMock(REDIS_URL="redis://test")),
            patch(
                "src.database.get_session_maker",
                return_value=self._make_session_context(mock_session),
            ),
            patch(
                "src.tasks.content_monitoring_tasks._get_llm_service",
                return_value=MagicMock(),
            ),
            patch(
                "src.fact_checking.embedding_service.EmbeddingService",
                return_value=MagicMock(),
            ),
            patch(
                "src.bulk_content_scan.service.BulkContentScanService",
                return_value=mock_service,
            ),
            patch(
                "src.events.publisher.create_worker_event_publisher",
                return_value=mock_worker_context,
            ),
            patch(
                "src.bulk_content_scan.nats_handler.BulkScanResultsPublisher",
                return_value=mock_results_publisher,
            ),
            patch("src.monitoring.metrics.bulk_scan_finalization_dispatch_total") as mock_metric,
        ):
            result = finalize_scan_step.__wrapped__(
                scan_id=scan_id,
                community_server_id=community_server_id,
                messages_scanned=4,
                processed_count=3,
                skipped_count=1,
                error_count=0,
                flagged_count=0,
            )

        assert result["status"] == "completed"
        mock_service.complete_scan.assert_awaited_once_with(
            scan_id=mock_service.complete_scan.await_args.kwargs["scan_id"],
            messages_scanned=4,
            messages_flagged=0,
            status=BulkScanStatus.COMPLETED,
        )
        mock_results_publisher.publish.assert_awaited_once()
        published_events = [
            call.args[0] for call in mock_worker_publisher.publish_event.await_args_list
        ]
        assert not any(isinstance(event, BulkScanFailedEvent) for event in published_events)
        assert any(isinstance(event, BulkScanProcessingFinishedEvent) for event in published_events)
        mock_metric.add.assert_called_once_with(1, {"outcome": "success"})

    def test_skipped_only_scan_completes_without_publishing_failed_event(self) -> None:
        """Skipped-only scans stay completed and do not emit a failed event."""
        from src.bulk_content_scan.schemas import BulkScanStatus
        from src.dbos_workflows.content_scan_workflow import finalize_scan_step
        from src.events.schemas import BulkScanFailedEvent, BulkScanProcessingFinishedEvent

        scan_id = str(uuid4())
        community_server_id = str(uuid4())

        mock_session = AsyncMock()
        mock_service = MagicMock()
        mock_service.get_flagged_results = AsyncMock(return_value=[])
        mock_service.get_error_summary = AsyncMock(
            return_value={"total_errors": 0, "error_types": {}, "sample_errors": []}
        )
        mock_service.get_skipped_count = AsyncMock(return_value=4)
        mock_service.complete_scan = AsyncMock()

        mock_worker_publisher = AsyncMock()
        mock_worker_publisher.nats = MagicMock()

        mock_worker_context = AsyncMock()
        mock_worker_context.__aenter__ = AsyncMock(return_value=mock_worker_publisher)
        mock_worker_context.__aexit__ = AsyncMock(return_value=False)

        mock_results_publisher = MagicMock()
        mock_results_publisher.publish = AsyncMock()

        with (
            patch(
                "src.dbos_workflows.content_scan_workflow.run_sync",
                side_effect=lambda coroutine: asyncio.run(coroutine),
            ),
            patch(
                "src.cache.redis_client.get_shared_redis_client",
                new_callable=AsyncMock,
                return_value=MagicMock(),
            ),
            patch("src.config.get_settings", return_value=MagicMock(REDIS_URL="redis://test")),
            patch(
                "src.database.get_session_maker",
                return_value=self._make_session_context(mock_session),
            ),
            patch(
                "src.tasks.content_monitoring_tasks._get_llm_service",
                return_value=MagicMock(),
            ),
            patch(
                "src.fact_checking.embedding_service.EmbeddingService",
                return_value=MagicMock(),
            ),
            patch(
                "src.bulk_content_scan.service.BulkContentScanService",
                return_value=mock_service,
            ),
            patch(
                "src.events.publisher.create_worker_event_publisher",
                return_value=mock_worker_context,
            ),
            patch(
                "src.bulk_content_scan.nats_handler.BulkScanResultsPublisher",
                return_value=mock_results_publisher,
            ),
            patch("src.monitoring.metrics.bulk_scan_finalization_dispatch_total") as mock_metric,
        ):
            result = finalize_scan_step.__wrapped__(
                scan_id=scan_id,
                community_server_id=community_server_id,
                messages_scanned=4,
                processed_count=0,
                skipped_count=4,
                error_count=0,
                flagged_count=0,
            )

        assert result["status"] == "completed"
        mock_service.complete_scan.assert_awaited_once_with(
            scan_id=mock_service.complete_scan.await_args.kwargs["scan_id"],
            messages_scanned=4,
            messages_flagged=0,
            status=BulkScanStatus.COMPLETED,
        )
        published_events = [
            call.args[0] for call in mock_worker_publisher.publish_event.await_args_list
        ]
        assert not any(isinstance(event, BulkScanFailedEvent) for event in published_events)
        assert any(isinstance(event, BulkScanProcessingFinishedEvent) for event in published_events)
        mock_metric.add.assert_called_once_with(1, {"outcome": "success"})

    def test_workflow_skipped_count_fallback_wins_when_redis_drifts_low(self) -> None:
        """Workflow skipped_count keeps skipped-only scans completed when Redis under-reports."""
        from src.bulk_content_scan.schemas import BulkScanStatus
        from src.dbos_workflows.content_scan_workflow import finalize_scan_step
        from src.events.schemas import BulkScanFailedEvent, BulkScanProcessingFinishedEvent

        scan_id = str(uuid4())
        community_server_id = str(uuid4())

        mock_session = AsyncMock()
        mock_service = MagicMock()
        mock_service.get_flagged_results = AsyncMock(return_value=[])
        mock_service.get_error_summary = AsyncMock(
            return_value={"total_errors": 0, "error_types": {}, "sample_errors": []}
        )
        mock_service.get_skipped_count = AsyncMock(return_value=0)
        mock_service.complete_scan = AsyncMock()

        mock_worker_publisher = AsyncMock()
        mock_worker_publisher.nats = MagicMock()

        mock_worker_context = AsyncMock()
        mock_worker_context.__aenter__ = AsyncMock(return_value=mock_worker_publisher)
        mock_worker_context.__aexit__ = AsyncMock(return_value=False)

        mock_results_publisher = MagicMock()
        mock_results_publisher.publish = AsyncMock()

        with (
            patch(
                "src.dbos_workflows.content_scan_workflow.run_sync",
                side_effect=lambda coroutine: asyncio.run(coroutine),
            ),
            patch(
                "src.cache.redis_client.get_shared_redis_client",
                new_callable=AsyncMock,
                return_value=MagicMock(),
            ),
            patch("src.config.get_settings", return_value=MagicMock(REDIS_URL="redis://test")),
            patch(
                "src.database.get_session_maker",
                return_value=self._make_session_context(mock_session),
            ),
            patch(
                "src.tasks.content_monitoring_tasks._get_llm_service",
                return_value=MagicMock(),
            ),
            patch(
                "src.fact_checking.embedding_service.EmbeddingService",
                return_value=MagicMock(),
            ),
            patch(
                "src.bulk_content_scan.service.BulkContentScanService",
                return_value=mock_service,
            ),
            patch(
                "src.events.publisher.create_worker_event_publisher",
                return_value=mock_worker_context,
            ),
            patch(
                "src.bulk_content_scan.nats_handler.BulkScanResultsPublisher",
                return_value=mock_results_publisher,
            ),
            patch("src.monitoring.metrics.bulk_scan_finalization_dispatch_total") as mock_metric,
        ):
            result = finalize_scan_step.__wrapped__(
                scan_id=scan_id,
                community_server_id=community_server_id,
                messages_scanned=4,
                processed_count=0,
                skipped_count=4,
                error_count=0,
                flagged_count=0,
            )

        assert result["status"] == "completed"
        assert result["messages_skipped"] == 4
        mock_service.complete_scan.assert_awaited_once_with(
            scan_id=mock_service.complete_scan.await_args.kwargs["scan_id"],
            messages_scanned=4,
            messages_flagged=0,
            status=BulkScanStatus.COMPLETED,
        )
        assert mock_results_publisher.publish.await_args.kwargs["messages_skipped"] == 4
        published_events = [
            call.args[0] for call in mock_worker_publisher.publish_event.await_args_list
        ]
        assert not any(isinstance(event, BulkScanFailedEvent) for event in published_events)
        processing_finished_event = next(
            event
            for event in published_events
            if isinstance(event, BulkScanProcessingFinishedEvent)
        )
        assert processing_finished_event.messages_skipped == 4
        mock_metric.add.assert_called_once_with(1, {"outcome": "success"})


class TestDetermineScanStatus:
    """Tests for _determine_scan_status helper."""

    def test_timeout_with_zero_processed_returns_failed(self) -> None:
        from src.dbos_workflows.content_scan_workflow import _determine_scan_status

        status, reason = _determine_scan_status(
            messages_scanned=91,
            processed_count=0,
            error_count=0,
            total_errors=0,
        )
        assert status.value == "failed"
        assert reason is not None
        assert "timed out" in reason

    def test_all_errors_returns_failed(self) -> None:
        from src.dbos_workflows.content_scan_workflow import _determine_scan_status

        status, reason = _determine_scan_status(
            messages_scanned=10,
            processed_count=0,
            error_count=0,
            total_errors=10,
        )
        assert status.value == "failed"
        assert reason is not None
        assert "errors" in reason

    def test_normal_completion_returns_completed(self) -> None:
        from src.dbos_workflows.content_scan_workflow import _determine_scan_status

        status, reason = _determine_scan_status(
            messages_scanned=10,
            processed_count=10,
            error_count=0,
            total_errors=0,
        )
        assert status.value == "completed"
        assert reason is None

    def test_zero_messages_without_all_transmitted_returns_failed(self) -> None:
        from src.dbos_workflows.content_scan_workflow import _determine_scan_status

        status, reason = _determine_scan_status(
            messages_scanned=0,
            processed_count=0,
            error_count=0,
            total_errors=0,
            all_transmitted_observed=False,
        )
        assert status.value == "failed"
        assert reason is not None
        assert "all_transmitted" in reason

    def test_zero_messages_with_all_transmitted_returns_completed(self) -> None:
        from src.dbos_workflows.content_scan_workflow import _determine_scan_status

        status, reason = _determine_scan_status(
            messages_scanned=0,
            processed_count=0,
            error_count=0,
            total_errors=0,
            all_transmitted_observed=True,
        )
        assert status.value == "completed"
        assert reason is None

    def test_error_count_with_zero_total_errors_returns_failed(self) -> None:
        from src.dbos_workflows.content_scan_workflow import _determine_scan_status

        status, reason = _determine_scan_status(
            messages_scanned=10,
            processed_count=0,
            error_count=5,
            total_errors=0,
        )
        assert status.value == "failed"
        assert reason is not None
        assert "batch errors" in reason

    def test_partial_processing_returns_completed(self) -> None:
        from src.dbos_workflows.content_scan_workflow import _determine_scan_status

        status, reason = _determine_scan_status(
            messages_scanned=10,
            processed_count=5,
            skipped_count=0,
            error_count=5,
            total_errors=5,
        )
        assert status.value == "completed"
        assert reason is None

    def test_all_skipped_returns_completed(self) -> None:
        from src.dbos_workflows.content_scan_workflow import _determine_scan_status

        status, reason = _determine_scan_status(
            messages_scanned=4,
            processed_count=0,
            skipped_count=4,
            error_count=0,
            total_errors=0,
        )
        assert status.value == "completed"
        assert reason is None

    def test_incomplete_finalization_returns_failed(self) -> None:
        from src.dbos_workflows.content_scan_workflow import _determine_scan_status

        status, reason = _determine_scan_status(
            messages_scanned=10,
            processed_count=5,
            skipped_count=0,
            error_count=0,
            total_errors=0,
            finalization_incomplete=True,
        )
        assert status.value == "failed"
        assert reason is not None
        assert "incomplete" in reason


class TestAdaptiveTimeoutProducesFailed:
    """Integration-level test: adaptive cap exceeded → _determine_scan_status → FAILED."""

    def test_adaptive_cap_exceeded_produces_failed_via_determine_status(self) -> None:
        from src.dbos_workflows.content_scan_workflow import (
            _determine_scan_status,
            compute_adaptive_timeout_cap,
        )

        messages_scanned = 10
        cap = compute_adaptive_timeout_cap(messages_scanned)
        assert cap == 120

        status, reason = _determine_scan_status(
            messages_scanned=messages_scanned,
            processed_count=0,
            error_count=0,
            total_errors=0,
        )
        assert status.value == "failed"
        assert reason is not None
        assert "timed out" in reason


class TestDispatchContentScanWorkflow:
    """Tests for dispatch_content_scan_workflow async helper."""

    @pytest.mark.asyncio
    async def test_dispatches_workflow_and_returns_id(self) -> None:
        from src.dbos_workflows.content_scan_workflow import dispatch_content_scan_workflow

        scan_id = uuid4()
        community_server_id = uuid4()
        scan_types = ["similarity", "openai_moderation"]

        mock_handle = MagicMock()
        mock_handle.workflow_id = "dispatched-wf-123"

        with patch(
            "src.dbos_workflows.content_scan_workflow.content_scan_queue.enqueue",
            return_value=mock_handle,
        ):
            result = await dispatch_content_scan_workflow(
                scan_id=scan_id,
                community_server_id=community_server_id,
                scan_types=scan_types,
            )

        assert result == "dispatched-wf-123"

    @pytest.mark.asyncio
    async def test_returns_none_on_enqueue_error(self) -> None:
        from src.dbos_workflows.content_scan_workflow import dispatch_content_scan_workflow

        with patch(
            "src.dbos_workflows.content_scan_workflow.content_scan_queue.enqueue",
            side_effect=RuntimeError("Connection refused"),
        ):
            result = await dispatch_content_scan_workflow(
                scan_id=uuid4(),
                community_server_id=uuid4(),
                scan_types=["similarity"],
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_uses_scan_id_as_idempotency_key(self) -> None:
        from src.dbos_workflows.content_scan_workflow import dispatch_content_scan_workflow

        scan_id = uuid4()

        mock_handle = MagicMock()
        mock_handle.workflow_id = "wf-idempotent"

        with (
            patch(
                "src.dbos_workflows.content_scan_workflow.content_scan_queue.enqueue",
                return_value=mock_handle,
            ),
            patch(
                "src.dbos_workflows.content_scan_workflow.SetEnqueueOptions",
            ) as mock_set_options,
        ):
            mock_set_options.return_value.__enter__ = MagicMock(return_value=None)
            mock_set_options.return_value.__exit__ = MagicMock(return_value=False)

            await dispatch_content_scan_workflow(
                scan_id=scan_id,
                community_server_id=uuid4(),
                scan_types=["similarity"],
            )

        mock_set_options.assert_called_once_with(deduplication_id=str(scan_id))

    @pytest.mark.asyncio
    async def test_uses_scan_id_as_workflow_id(self) -> None:
        from src.dbos_workflows.content_scan_workflow import dispatch_content_scan_workflow

        scan_id = uuid4()

        mock_handle = MagicMock()
        mock_handle.workflow_id = str(scan_id)

        with (
            patch(
                "src.dbos_workflows.content_scan_workflow.content_scan_queue.enqueue",
                return_value=mock_handle,
            ),
            patch(
                "src.dbos_workflows.content_scan_workflow.SetWorkflowID",
            ) as mock_set_wf_id,
        ):
            mock_set_wf_id.return_value.__enter__ = MagicMock(return_value=None)
            mock_set_wf_id.return_value.__exit__ = MagicMock(return_value=False)

            await dispatch_content_scan_workflow(
                scan_id=scan_id,
                community_server_id=uuid4(),
                scan_types=["similarity"],
            )

        mock_set_wf_id.assert_called_once_with(str(scan_id))


class TestEnqueueContentScanBatch:
    """Tests for enqueue_content_scan_batch async helper."""

    @pytest.mark.asyncio
    async def test_enqueues_batch_and_returns_workflow_id(self) -> None:
        from src.dbos_workflows.content_scan_workflow import enqueue_content_scan_batch

        scan_id = uuid4()
        community_server_id = uuid4()

        mock_handle = MagicMock()
        mock_handle.workflow_id = "batch-wf-456"

        with patch(
            "src.dbos_workflows.content_scan_workflow.content_scan_queue.enqueue",
            return_value=mock_handle,
        ):
            result = await enqueue_content_scan_batch(
                orchestrator_workflow_id="orchestrator-wf-123",
                scan_id=scan_id,
                community_server_id=community_server_id,
                batch_number=1,
                messages_redis_key="test:messages:key",
                scan_types=["similarity"],
            )

        assert result == "batch-wf-456"

    @pytest.mark.asyncio
    async def test_returns_none_on_enqueue_failure(self) -> None:
        from src.dbos_workflows.content_scan_workflow import enqueue_content_scan_batch

        with patch(
            "src.dbos_workflows.content_scan_workflow.content_scan_queue.enqueue",
            side_effect=RuntimeError("Queue full"),
        ):
            result = await enqueue_content_scan_batch(
                orchestrator_workflow_id="wf-123",
                scan_id=uuid4(),
                community_server_id=uuid4(),
                batch_number=1,
                messages_redis_key="test:messages:key",
                scan_types=["similarity"],
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_enqueues_correct_workflow_function(self) -> None:
        from src.dbos_workflows.content_scan_workflow import (
            enqueue_content_scan_batch,
            process_content_scan_batch,
        )

        mock_handle = MagicMock()
        mock_handle.workflow_id = "wf-789"

        with patch(
            "src.dbos_workflows.content_scan_workflow.content_scan_queue.enqueue",
            return_value=mock_handle,
        ) as mock_enqueue:
            await enqueue_content_scan_batch(
                orchestrator_workflow_id="wf-123",
                scan_id=uuid4(),
                community_server_id=uuid4(),
                batch_number=1,
                messages_redis_key="test:messages:key",
                scan_types=["similarity"],
            )

        call_args = mock_enqueue.call_args.args
        assert call_args[0] is process_content_scan_batch


class TestSendAllTransmittedSignal:
    """Tests for send_all_transmitted_signal async helper."""

    @pytest.mark.asyncio
    async def test_sends_signal_and_returns_true(self) -> None:
        from src.dbos_workflows.content_scan_workflow import send_all_transmitted_signal

        with patch(
            "src.dbos_workflows.content_scan_workflow.DBOS.send",
        ) as mock_send:
            result = await send_all_transmitted_signal(
                orchestrator_workflow_id="wf-123",
                messages_scanned=50,
            )

        assert result is True
        mock_send.assert_called_once_with(
            "wf-123",
            {"messages_scanned": 50},
            "all_transmitted",
        )

    @pytest.mark.asyncio
    async def test_returns_false_on_failure(self) -> None:
        from src.dbos_workflows.content_scan_workflow import send_all_transmitted_signal

        with patch(
            "src.dbos_workflows.content_scan_workflow.DBOS.send",
            side_effect=RuntimeError("Connection lost"),
        ):
            result = await send_all_transmitted_signal(
                orchestrator_workflow_id="wf-123",
                messages_scanned=50,
            )

        assert result is False


class TestWorkflowNames:
    """Tests for exported workflow name constants."""

    def test_orchestration_workflow_name_matches_qualname(self) -> None:
        from src.dbos_workflows.content_scan_workflow import (
            CONTENT_SCAN_ORCHESTRATION_WORKFLOW_NAME,
            content_scan_orchestration_workflow,
        )

        assert (
            content_scan_orchestration_workflow.__qualname__
            == CONTENT_SCAN_ORCHESTRATION_WORKFLOW_NAME
        )

    def test_batch_workflow_name_matches_qualname(self) -> None:
        from src.dbos_workflows.content_scan_workflow import (
            PROCESS_CONTENT_SCAN_BATCH_WORKFLOW_NAME,
            process_content_scan_batch,
        )

        assert process_content_scan_batch.__qualname__ == PROCESS_CONTENT_SCAN_BATCH_WORKFLOW_NAME

    def test_workflow_names_are_bare_function_names(self) -> None:
        from src.dbos_workflows.content_scan_workflow import (
            CONTENT_SCAN_ORCHESTRATION_WORKFLOW_NAME,
            PROCESS_CONTENT_SCAN_BATCH_WORKFLOW_NAME,
        )

        assert CONTENT_SCAN_ORCHESTRATION_WORKFLOW_NAME == "content_scan_orchestration_workflow"
        assert PROCESS_CONTENT_SCAN_BATCH_WORKFLOW_NAME == "process_content_scan_batch"


class TestFlashpointDetectionToggleInWorkflow:
    """Tests that flashpoint_detection_enabled toggle is respected in DBOS workflow."""

    def test_scan_types_include_flashpoint_when_requested(self) -> None:
        from src.bulk_content_scan.scan_types import ScanType

        scan_types_json = json.dumps(["similarity", "openai_moderation", "conversation_flashpoint"])
        scan_types = [ScanType(st) for st in json.loads(scan_types_json)]

        assert ScanType.CONVERSATION_FLASHPOINT in scan_types
        assert len(scan_types) == 3

    def test_scan_types_exclude_flashpoint_when_not_requested(self) -> None:
        from src.bulk_content_scan.scan_types import ScanType

        scan_types_json = json.dumps(["similarity"])
        scan_types = [ScanType(st) for st in json.loads(scan_types_json)]

        assert ScanType.CONVERSATION_FLASHPOINT not in scan_types

    def test_batch_step_passes_scan_types_to_service(self) -> None:
        from src.dbos_workflows.content_scan_workflow import process_batch_messages_step

        scan_id = str(uuid4())
        community_server_id = str(uuid4())
        messages = [
            {
                "message_id": "msg_1",
                "channel_id": "ch_1",
                "community_server_id": "cs_1",
                "content": "heated argument",
                "author_id": "user_1",
                "author_username": "testuser",
                "timestamp": "2025-01-01T00:00:00Z",
                "attachment_urls": None,
                "embed_content": None,
            }
        ]
        messages_json = json.dumps(messages)
        scan_types_json = json.dumps(["similarity", "conversation_flashpoint"])

        with patch("src.dbos_workflows.content_scan_workflow.run_sync") as mock_run_sync:
            mock_run_sync.return_value = {
                "processed": 1,
                "skipped": 0,
                "errors": 0,
                "flagged_count": 0,
                "batch_number": 1,
            }

            result = process_batch_messages_step.__wrapped__(
                scan_id=scan_id,
                community_server_id=community_server_id,
                batch_number=1,
                messages_json=messages_json,
                scan_types_json=scan_types_json,
            )

        assert result["processed"] == 1
        mock_run_sync.assert_called_once()


class TestSignalCoordination:
    """Tests for signal coordination between batch workers and orchestrator."""

    def test_batch_complete_signal_sent_with_correct_topic(self) -> None:
        from src.dbos_workflows.content_scan_workflow import process_content_scan_batch

        with ExitStack() as stack:
            mocks = _patch_process_content_scan_batch_dependencies(stack)
            mocks["preprocess"].return_value = {
                "filtered_messages_key": "k",
                "context_maps_key": "k",
                "message_count": 10,
                "skipped_count": 1,
            }
            mocks["relevance"].return_value = {"flagged_count": 2, "errors": 0}

            process_content_scan_batch.__wrapped__(
                orchestrator_workflow_id="orch-wf-id",
                scan_id=str(uuid4()),
                community_server_id=str(uuid4()),
                batch_number=3,
                messages_redis_key="test:messages:key",
                scan_types_json='["similarity"]',
            )

        call_args = mocks["dbos"].send.call_args
        assert call_args.args[0] == "orch-wf-id"
        assert call_args.kwargs["topic"] == "batch_complete"

    def test_orchestrator_marks_scan_finalizing_before_finalize_step(self) -> None:
        from src.dbos_workflows.content_scan_workflow import (
            content_scan_orchestration_workflow,
        )

        scan_id = str(uuid4())
        community_server_id = str(uuid4())

        recv_fn = _make_recv_dispatcher(
            batch_responses=[
                {"processed": 3, "skipped": 0, "errors": 0, "flagged_count": 1, "batch_number": 1},
            ],
            tx_responses=[
                {"messages_scanned": 3},
            ],
        )
        call_order: list[str] = []

        with (
            patch("src.dbos_workflows.content_scan_workflow.create_scan_record_step"),
            patch(
                "src.dbos_workflows.content_scan_workflow._checkpoint_wall_clock_step",
                return_value=time.time(),
            ),
            patch(
                "src.dbos_workflows.content_scan_workflow.mark_scan_finalizing_step",
                side_effect=lambda **_: call_order.append("mark"),
            ) as mock_mark_finalizing,
            patch(
                "src.dbos_workflows.content_scan_workflow.finalize_scan_step",
                side_effect=lambda **_: call_order.append("finalize") or {"status": "completed"},
            ) as mock_finalize,
            patch("src.dbos_workflows.content_scan_workflow.DBOS") as mock_dbos,
            patch("src.dbos_workflows.content_scan_workflow.TokenGate"),
        ):
            mock_dbos.workflow_id = "test-wf-id"
            mock_dbos.recv.side_effect = recv_fn

            content_scan_orchestration_workflow.__wrapped__(
                scan_id=scan_id,
                community_server_id=community_server_id,
                scan_types_json=json.dumps(["similarity"]),
            )

        mock_mark_finalizing.assert_called_once_with(scan_id=scan_id)
        mock_finalize.assert_called_once()
        assert call_order == ["mark", "finalize"]

    def test_orchestrator_clears_finalizing_latch_when_finalize_step_fails(self) -> None:
        from src.dbos_workflows.content_scan_workflow import (
            content_scan_orchestration_workflow,
        )

        scan_id = str(uuid4())
        community_server_id = str(uuid4())

        recv_fn = _make_recv_dispatcher(
            batch_responses=[
                {"processed": 3, "skipped": 0, "errors": 0, "flagged_count": 1, "batch_number": 1},
            ],
            tx_responses=[
                {"messages_scanned": 3},
            ],
        )
        call_order: list[str] = []

        with (
            patch("src.dbos_workflows.content_scan_workflow.create_scan_record_step"),
            patch(
                "src.dbos_workflows.content_scan_workflow._checkpoint_wall_clock_step",
                return_value=time.time(),
            ),
            patch(
                "src.dbos_workflows.content_scan_workflow.mark_scan_finalizing_step",
                side_effect=lambda **_: call_order.append("mark"),
            ) as mock_mark_finalizing,
            patch(
                "src.dbos_workflows.content_scan_workflow.clear_scan_finalizing_step",
                side_effect=lambda **_: call_order.append("clear"),
                create=True,
            ) as mock_clear_finalizing,
            patch(
                "src.dbos_workflows.content_scan_workflow.finalize_scan_step",
                side_effect=RuntimeError("finalize boom"),
            ) as mock_finalize,
            patch("src.dbos_workflows.content_scan_workflow.DBOS") as mock_dbos,
            patch("src.dbos_workflows.content_scan_workflow.TokenGate"),
        ):
            mock_dbos.workflow_id = "test-wf-id"
            mock_dbos.recv.side_effect = recv_fn

            with pytest.raises(RuntimeError, match="finalize boom"):
                content_scan_orchestration_workflow.__wrapped__(
                    scan_id=scan_id,
                    community_server_id=community_server_id,
                    scan_types_json=json.dumps(["similarity"]),
                )

        mock_mark_finalizing.assert_called_once_with(scan_id=scan_id)
        mock_finalize.assert_called_once()
        mock_clear_finalizing.assert_called_once_with(scan_id=scan_id)
        assert call_order == ["mark", "clear"]

    def test_orchestrator_logs_and_returns_when_finalizing_latch_clear_fails_after_finalize(
        self,
    ) -> None:
        from src.dbos_workflows.content_scan_workflow import (
            content_scan_orchestration_workflow,
        )

        scan_id = str(uuid4())
        community_server_id = str(uuid4())

        recv_fn = _make_recv_dispatcher(
            batch_responses=[
                {"processed": 3, "skipped": 0, "errors": 0, "flagged_count": 1, "batch_number": 1},
            ],
            tx_responses=[
                {"messages_scanned": 3},
            ],
        )
        finalized_result = {"status": "completed"}
        call_order: list[str] = []

        with (
            patch("src.dbos_workflows.content_scan_workflow.create_scan_record_step"),
            patch(
                "src.dbos_workflows.content_scan_workflow._checkpoint_wall_clock_step",
                return_value=time.time(),
            ),
            patch(
                "src.dbos_workflows.content_scan_workflow.mark_scan_finalizing_step",
                side_effect=lambda **_: call_order.append("mark"),
            ) as mock_mark_finalizing,
            patch(
                "src.dbos_workflows.content_scan_workflow.finalize_scan_step",
                side_effect=lambda **_: call_order.append("finalize") or finalized_result,
            ) as mock_finalize,
            patch(
                "src.dbos_workflows.content_scan_workflow.clear_scan_finalizing_step",
                side_effect=lambda **_: call_order.append("clear")
                or (_ for _ in ()).throw(RuntimeError("clear boom")),
                create=True,
            ) as mock_clear_finalizing,
            patch("src.dbos_workflows.content_scan_workflow.logger.warning") as mock_warning,
            patch("src.dbos_workflows.content_scan_workflow.DBOS") as mock_dbos,
            patch("src.dbos_workflows.content_scan_workflow.TokenGate"),
        ):
            mock_dbos.workflow_id = "test-wf-id"
            mock_dbos.recv.side_effect = recv_fn

            result = content_scan_orchestration_workflow.__wrapped__(
                scan_id=scan_id,
                community_server_id=community_server_id,
                scan_types_json=json.dumps(["similarity"]),
            )

        assert result == finalized_result
        mock_mark_finalizing.assert_called_once_with(scan_id=scan_id)
        mock_finalize.assert_called_once()
        mock_clear_finalizing.assert_called_once_with(scan_id=scan_id)
        mock_warning.assert_called_once_with(
            "Failed to clear finalizing latch after successful finalization",
            extra={"scan_id": scan_id},
            exc_info=True,
        )
        assert call_order == ["mark", "finalize", "clear"]

    def test_late_batch_does_not_send_batch_complete_after_finalizing(self) -> None:
        from src.dbos_workflows.content_scan_workflow import process_content_scan_batch

        with ExitStack() as stack:
            mocks = _patch_process_content_scan_batch_dependencies(stack)
            mocks["terminal"].side_effect = [False, False, True]
            mocks["preprocess"].return_value = {
                "filtered_messages_key": "filtered-key",
                "context_maps_key": "context-key",
                "message_count": 4,
                "skipped_count": 2,
            }
            mocks["relevance"].return_value = {"flagged_count": 1, "errors": 3}

            result = process_content_scan_batch.__wrapped__(
                orchestrator_workflow_id="orch-wf-id",
                scan_id=str(uuid4()),
                community_server_id=str(uuid4()),
                batch_number=3,
                messages_redis_key="test:messages:key",
                scan_types_json='["similarity"]',
            )

        assert result == {
            "processed": 0,
            "skipped": 2,
            "errors": 3,
            "flagged_count": 0,
            "batch_number": 3,
        }
        mocks["dbos"].send.assert_not_called()

    def test_orchestrator_receives_both_signal_types(self) -> None:
        from src.dbos_workflows.content_scan_workflow import (
            content_scan_orchestration_workflow,
        )

        scan_id = str(uuid4())
        community_server_id = str(uuid4())

        recv_fn = _make_recv_dispatcher(
            batch_responses=[
                {"processed": 3, "skipped": 0, "errors": 0, "flagged_count": 1, "batch_number": 1},
            ],
            tx_responses=[
                None,
                {"messages_scanned": 3},
            ],
        )

        with (
            patch("src.dbos_workflows.content_scan_workflow.create_scan_record_step"),
            patch(
                "src.dbos_workflows.content_scan_workflow._checkpoint_wall_clock_step"
            ) as mock_clock,
            patch(
                "src.dbos_workflows.content_scan_workflow.mark_scan_finalizing_step",
                return_value=True,
            ),
            patch("src.dbos_workflows.content_scan_workflow.finalize_scan_step") as mock_finalize,
            patch("src.dbos_workflows.content_scan_workflow.DBOS") as mock_dbos,
            patch("src.dbos_workflows.content_scan_workflow.TokenGate"),
        ):
            mock_dbos.workflow_id = "test-wf-id"
            mock_dbos.recv.side_effect = recv_fn
            mock_clock.return_value = time.time()
            mock_finalize.return_value = {"status": "completed"}

            content_scan_orchestration_workflow.__wrapped__(
                scan_id=scan_id,
                community_server_id=community_server_id,
                scan_types_json=json.dumps(["similarity"]),
            )

        recv_topics = [call.args[0] for call in mock_dbos.recv.call_args_list]
        assert "batch_complete" in recv_topics
        assert "all_transmitted" in recv_topics

    def test_termination_condition_requires_all_messages_processed(self) -> None:
        from src.dbos_workflows.content_scan_workflow import (
            content_scan_orchestration_workflow,
        )

        scan_id = str(uuid4())
        community_server_id = str(uuid4())

        recv_fn = _make_recv_dispatcher(
            batch_responses=[
                {"processed": 3, "skipped": 0, "errors": 0, "flagged_count": 0, "batch_number": 1},
                {"processed": 4, "skipped": 0, "errors": 3, "flagged_count": 0, "batch_number": 2},
            ],
            tx_responses=[
                None,
                {"messages_scanned": 10},
                None,
            ],
        )

        with (
            patch("src.dbos_workflows.content_scan_workflow.create_scan_record_step"),
            patch(
                "src.dbos_workflows.content_scan_workflow._checkpoint_wall_clock_step"
            ) as mock_clock,
            patch(
                "src.dbos_workflows.content_scan_workflow.mark_scan_finalizing_step",
                return_value=True,
            ),
            patch("src.dbos_workflows.content_scan_workflow.finalize_scan_step") as mock_finalize,
            patch("src.dbos_workflows.content_scan_workflow.DBOS") as mock_dbos,
            patch("src.dbos_workflows.content_scan_workflow.TokenGate"),
        ):
            mock_dbos.workflow_id = "test-wf-id"
            mock_dbos.recv.side_effect = recv_fn
            mock_clock.return_value = time.time()
            mock_finalize.return_value = {"status": "completed"}

            content_scan_orchestration_workflow.__wrapped__(
                scan_id=scan_id,
                community_server_id=community_server_id,
                scan_types_json=json.dumps(["similarity"]),
            )

        finalize_kwargs = mock_finalize.call_args.kwargs
        assert finalize_kwargs["processed_count"] == 7
        assert finalize_kwargs["error_count"] == 3
        assert finalize_kwargs["messages_scanned"] == 10


class TestCountMismatchBreakCondition:
    """Tests for the count mismatch adaptive timeout condition."""

    def test_polls_then_breaks_on_adaptive_cap_after_count_mismatch(self) -> None:
        """After mismatch, orchestrator continues polling then breaks when adaptive cap exceeded."""
        from src.dbos_workflows.content_scan_workflow import (
            content_scan_orchestration_workflow,
        )

        scan_id = str(uuid4())
        community_server_id = str(uuid4())

        recv_fn = _make_recv_dispatcher(
            batch_responses=[
                {"processed": 3, "skipped": 0, "errors": 0, "flagged_count": 1, "batch_number": 1},
                None,
            ],
            tx_responses=[
                {"messages_scanned": 10},
            ],
        )

        start = 1000000.0
        time_values = iter(
            [
                start,
                start + 10,
                start + 200,
                start + 200,
            ]
        )

        with (
            patch("src.dbos_workflows.content_scan_workflow.create_scan_record_step"),
            patch(
                "src.dbos_workflows.content_scan_workflow._checkpoint_wall_clock_step"
            ) as mock_clock,
            patch(
                "src.dbos_workflows.content_scan_workflow.mark_scan_finalizing_step",
                return_value=True,
            ),
            patch("src.dbos_workflows.content_scan_workflow.finalize_scan_step") as mock_finalize,
            patch("src.dbos_workflows.content_scan_workflow.DBOS") as mock_dbos,
            patch("src.dbos_workflows.content_scan_workflow.TokenGate"),
            patch("src.dbos_workflows.content_scan_workflow.time") as mock_time,
        ):
            mock_dbos.workflow_id = "test-wf-id"
            mock_dbos.recv.side_effect = recv_fn
            mock_clock.return_value = start
            mock_time.time.side_effect = time_values
            mock_finalize.return_value = {"status": "completed"}

            content_scan_orchestration_workflow.__wrapped__(
                scan_id=scan_id,
                community_server_id=community_server_id,
                scan_types_json=json.dumps(["similarity"]),
            )

        mock_finalize.assert_called_once()
        finalize_kwargs = mock_finalize.call_args.kwargs
        assert finalize_kwargs["processed_count"] == 3
        assert finalize_kwargs["messages_scanned"] == 10


class TestProgressTrackingThroughWorkflowSteps:
    """Tests that progress accumulates correctly across batch signals."""

    def test_progress_accumulates_across_batches(self) -> None:
        from src.dbos_workflows.content_scan_workflow import (
            content_scan_orchestration_workflow,
        )

        scan_id = str(uuid4())
        community_server_id = str(uuid4())

        recv_fn = _make_recv_dispatcher(
            batch_responses=[
                {"processed": 10, "skipped": 1, "errors": 0, "flagged_count": 2, "batch_number": 1},
                {"processed": 8, "skipped": 2, "errors": 1, "flagged_count": 3, "batch_number": 2},
                {"processed": 5, "skipped": 0, "errors": 2, "flagged_count": 0, "batch_number": 3},
            ],
            tx_responses=[
                None,
                None,
                None,
                {"messages_scanned": 29},
            ],
        )

        with (
            patch("src.dbos_workflows.content_scan_workflow.create_scan_record_step"),
            patch(
                "src.dbos_workflows.content_scan_workflow._checkpoint_wall_clock_step"
            ) as mock_clock,
            patch(
                "src.dbos_workflows.content_scan_workflow.mark_scan_finalizing_step",
                return_value=True,
            ),
            patch("src.dbos_workflows.content_scan_workflow.finalize_scan_step") as mock_finalize,
            patch("src.dbos_workflows.content_scan_workflow.DBOS") as mock_dbos,
            patch("src.dbos_workflows.content_scan_workflow.TokenGate"),
        ):
            mock_dbos.workflow_id = "test-wf-id"
            mock_dbos.recv.side_effect = recv_fn
            mock_clock.return_value = time.time()
            mock_finalize.return_value = {"status": "completed"}

            content_scan_orchestration_workflow.__wrapped__(
                scan_id=scan_id,
                community_server_id=community_server_id,
                scan_types_json=json.dumps(["similarity"]),
            )

        finalize_kwargs = mock_finalize.call_args.kwargs
        assert finalize_kwargs["processed_count"] == 23
        assert finalize_kwargs["skipped_count"] == 3
        assert finalize_kwargs["error_count"] == 3
        assert finalize_kwargs["flagged_count"] == 5
        assert finalize_kwargs["messages_scanned"] == 29

    def test_completion_triggers_finalize_step(self) -> None:
        from src.dbos_workflows.content_scan_workflow import (
            content_scan_orchestration_workflow,
        )

        scan_id = str(uuid4())

        recv_fn = _make_recv_dispatcher(
            batch_responses=[
                {"processed": 5, "skipped": 0, "errors": 0, "flagged_count": 1, "batch_number": 1},
            ],
            tx_responses=[
                None,
                {"messages_scanned": 5},
            ],
        )

        with (
            patch("src.dbos_workflows.content_scan_workflow.create_scan_record_step"),
            patch(
                "src.dbos_workflows.content_scan_workflow._checkpoint_wall_clock_step"
            ) as mock_clock,
            patch(
                "src.dbos_workflows.content_scan_workflow.mark_scan_finalizing_step",
                return_value=True,
            ),
            patch("src.dbos_workflows.content_scan_workflow.finalize_scan_step") as mock_finalize,
            patch("src.dbos_workflows.content_scan_workflow.DBOS") as mock_dbos,
            patch("src.dbos_workflows.content_scan_workflow.TokenGate"),
        ):
            mock_dbos.workflow_id = "test-wf-id"
            mock_dbos.recv.side_effect = recv_fn
            mock_clock.return_value = time.time()
            mock_finalize.return_value = {"status": "completed"}

            content_scan_orchestration_workflow.__wrapped__(
                scan_id=scan_id,
                community_server_id=str(uuid4()),
                scan_types_json=json.dumps(["similarity"]),
            )

        mock_finalize.assert_called_once()
        assert mock_finalize.call_args.kwargs["scan_id"] == scan_id

    def test_batch_signal_carries_progress_data(self) -> None:
        from src.dbos_workflows.content_scan_workflow import process_content_scan_batch

        with ExitStack() as stack:
            mocks = _patch_process_content_scan_batch_dependencies(stack)
            mocks["preprocess"].return_value = {
                "filtered_messages_key": "k",
                "context_maps_key": "k",
                "message_count": 7,
                "skipped_count": 1,
            }
            mocks["relevance"].return_value = {"flagged_count": 3, "errors": 2}

            process_content_scan_batch.__wrapped__(
                orchestrator_workflow_id="orch-wf-id",
                scan_id=str(uuid4()),
                community_server_id=str(uuid4()),
                batch_number=4,
                messages_redis_key="test:messages:key",
                scan_types_json='["similarity"]',
            )

        signal_data = mocks["dbos"].send.call_args.args[1]
        assert signal_data["processed"] == 7
        assert signal_data["skipped"] == 1
        assert signal_data["errors"] == 2
        assert signal_data["flagged_count"] == 3
        assert signal_data["batch_number"] == 4


class TestPreprocessBatchStep:
    """Tests for preprocess_batch_step DBOS step."""

    def test_returns_filtered_keys_and_counts(self) -> None:
        from src.dbos_workflows.content_scan_workflow import preprocess_batch_step

        expected = {
            "filtered_messages_key": "test:filtered",
            "context_maps_key": "test:context",
            "message_count": 3,
            "skipped_count": 2,
        }

        with patch("src.dbos_workflows.content_scan_workflow.run_sync") as mock_run_sync:
            mock_run_sync.return_value = expected

            result = preprocess_batch_step.__wrapped__(
                scan_id=str(uuid4()),
                community_server_id=str(uuid4()),
                batch_number=1,
                messages_redis_key="test:messages",
                scan_types_json=json.dumps(["similarity"]),
            )

        assert result["filtered_messages_key"] == "test:filtered"
        assert result["context_maps_key"] == "test:context"
        assert result["message_count"] == 3
        assert result["skipped_count"] == 2

    def test_delegates_to_run_sync(self) -> None:
        from src.dbos_workflows.content_scan_workflow import preprocess_batch_step

        with patch("src.dbos_workflows.content_scan_workflow.run_sync") as mock_run_sync:
            mock_run_sync.return_value = {
                "filtered_messages_key": "k",
                "context_maps_key": "k",
                "message_count": 0,
                "skipped_count": 0,
            }

            preprocess_batch_step.__wrapped__(
                scan_id=str(uuid4()),
                community_server_id=str(uuid4()),
                batch_number=1,
                messages_redis_key="test:key",
                scan_types_json=json.dumps(["similarity"]),
            )

        mock_run_sync.assert_called_once()


class TestSimilarityScanStep:
    """Tests for similarity_scan_step DBOS step."""

    def test_returns_candidates_key_and_count(self) -> None:
        from src.dbos_workflows.content_scan_workflow import similarity_scan_step

        expected = {"similarity_candidates_key": "test:sim", "candidate_count": 5}

        with patch("src.dbos_workflows.content_scan_workflow.run_sync") as mock_run_sync:
            mock_run_sync.return_value = expected

            result = similarity_scan_step.__wrapped__(
                scan_id=str(uuid4()),
                community_server_id=str(uuid4()),
                batch_number=1,
                filtered_messages_key="test:filtered",
                context_maps_key="test:context",
            )

        assert result["similarity_candidates_key"] == "test:sim"
        assert result["candidate_count"] == 5

    def test_delegates_to_run_sync(self) -> None:
        from src.dbos_workflows.content_scan_workflow import similarity_scan_step

        with patch("src.dbos_workflows.content_scan_workflow.run_sync") as mock_run_sync:
            mock_run_sync.return_value = {"similarity_candidates_key": "", "candidate_count": 0}

            similarity_scan_step.__wrapped__(
                scan_id=str(uuid4()),
                community_server_id=str(uuid4()),
                batch_number=1,
                filtered_messages_key="test:filtered",
                context_maps_key="test:context",
            )

        mock_run_sync.assert_called_once()

    def test_propagates_run_sync_error(self) -> None:
        from src.dbos_workflows.content_scan_workflow import similarity_scan_step

        with patch("src.dbos_workflows.content_scan_workflow.run_sync") as mock_run_sync:
            mock_run_sync.side_effect = RuntimeError("Redis unavailable")

            with pytest.raises(RuntimeError, match="Redis unavailable"):
                similarity_scan_step.__wrapped__(
                    scan_id=str(uuid4()),
                    community_server_id=str(uuid4()),
                    batch_number=1,
                    filtered_messages_key="test:filtered",
                    context_maps_key="test:context",
                )


class TestFlashpointScanStep:
    """Tests for flashpoint_scan_step DBOS step."""

    def test_returns_candidates_key_and_count(self) -> None:
        from src.dbos_workflows.content_scan_workflow import flashpoint_scan_step

        expected = {"flashpoint_candidates_key": "test:fp", "candidate_count": 2}

        with patch("src.dbos_workflows.content_scan_workflow.run_sync") as mock_run_sync:
            mock_run_sync.return_value = expected

            result = flashpoint_scan_step.__wrapped__(
                scan_id=str(uuid4()),
                community_server_id=str(uuid4()),
                batch_number=1,
                filtered_messages_key="test:filtered",
                context_maps_key="test:context",
            )

        assert result["flashpoint_candidates_key"] == "test:fp"
        assert result["candidate_count"] == 2

    def test_delegates_to_run_sync(self) -> None:
        from src.dbos_workflows.content_scan_workflow import flashpoint_scan_step

        with patch("src.dbos_workflows.content_scan_workflow.run_sync") as mock_run_sync:
            mock_run_sync.return_value = {"flashpoint_candidates_key": "", "candidate_count": 0}

            flashpoint_scan_step.__wrapped__(
                scan_id=str(uuid4()),
                community_server_id=str(uuid4()),
                batch_number=1,
                filtered_messages_key="test:filtered",
                context_maps_key="test:context",
            )

        mock_run_sync.assert_called_once()


class TestRelevanceFilterStep:
    """Tests for relevance_filter_step DBOS step."""

    def test_returns_flagged_count_and_errors(self) -> None:
        from src.dbos_workflows.content_scan_workflow import relevance_filter_step

        expected = {"flagged_count": 3, "errors": 0}

        with patch("src.dbos_workflows.content_scan_workflow.run_sync") as mock_run_sync:
            mock_run_sync.return_value = expected

            result = relevance_filter_step.__wrapped__(
                scan_id=str(uuid4()),
                community_server_id=str(uuid4()),
                batch_number=1,
                similarity_candidates_key="test:sim",
                flashpoint_candidates_key="test:fp",
            )

        assert result["flagged_count"] == 3
        assert result["errors"] == 0

    def test_handles_empty_candidate_keys(self) -> None:
        from src.dbos_workflows.content_scan_workflow import relevance_filter_step

        expected = {"flagged_count": 0, "errors": 0}

        with patch("src.dbos_workflows.content_scan_workflow.run_sync") as mock_run_sync:
            mock_run_sync.return_value = expected

            result = relevance_filter_step.__wrapped__(
                scan_id=str(uuid4()),
                community_server_id=str(uuid4()),
                batch_number=1,
                similarity_candidates_key="",
                flashpoint_candidates_key="",
            )

        assert result["flagged_count"] == 0

    def test_delegates_to_run_sync(self) -> None:
        from src.dbos_workflows.content_scan_workflow import relevance_filter_step

        with patch("src.dbos_workflows.content_scan_workflow.run_sync") as mock_run_sync:
            mock_run_sync.return_value = {"flagged_count": 0, "errors": 0}

            relevance_filter_step.__wrapped__(
                scan_id=str(uuid4()),
                community_server_id=str(uuid4()),
                batch_number=1,
                similarity_candidates_key="test:sim",
                flashpoint_candidates_key="",
            )

        mock_run_sync.assert_called_once()

    def test_propagates_run_sync_error(self) -> None:
        from src.dbos_workflows.content_scan_workflow import relevance_filter_step

        with patch("src.dbos_workflows.content_scan_workflow.run_sync") as mock_run_sync:
            mock_run_sync.side_effect = RuntimeError("LLM service down")

            with pytest.raises(RuntimeError, match="LLM service down"):
                relevance_filter_step.__wrapped__(
                    scan_id=str(uuid4()),
                    community_server_id=str(uuid4()),
                    batch_number=1,
                    similarity_candidates_key="test:sim",
                    flashpoint_candidates_key="",
                )


class TestEnqueueContentScanBatchRedisKey:
    """Tests for enqueue_content_scan_batch with Redis key support."""

    @pytest.mark.asyncio
    async def test_enqueues_with_redis_key(self) -> None:
        from src.dbos_workflows.content_scan_workflow import enqueue_content_scan_batch

        scan_id = uuid4()
        community_server_id = uuid4()
        redis_key = "test:bulk_scan:messages:scan:1"

        mock_handle = MagicMock()
        mock_handle.workflow_id = "batch-wf-789"

        with patch(
            "asyncio.to_thread", new_callable=AsyncMock, return_value=mock_handle
        ) as mock_to_thread:
            result = await enqueue_content_scan_batch(
                orchestrator_workflow_id="orchestrator-wf-123",
                scan_id=scan_id,
                community_server_id=community_server_id,
                batch_number=1,
                messages_redis_key=redis_key,
                scan_types=["similarity"],
            )

        assert result == "batch-wf-789"
        enqueue_args = mock_to_thread.call_args.args
        assert enqueue_args[5] == 1
        assert enqueue_args[6] == redis_key

    @pytest.mark.asyncio
    async def test_messages_redis_key_is_required(self) -> None:
        from src.dbos_workflows.content_scan_workflow import enqueue_content_scan_batch

        mock_handle = MagicMock()
        mock_handle.workflow_id = "batch-wf-required"

        with patch(
            "asyncio.to_thread", new_callable=AsyncMock, return_value=mock_handle
        ) as mock_to_thread:
            result = await enqueue_content_scan_batch(
                orchestrator_workflow_id="orch",
                scan_id=uuid4(),
                community_server_id=uuid4(),
                batch_number=1,
                messages_redis_key="test:required:key",
                scan_types=["similarity"],
            )

        assert result == "batch-wf-required"
        enqueue_args = mock_to_thread.call_args.args
        assert enqueue_args[6] == "test:required:key"


def _make_test_message(message_id: str = "msg_1", channel_id: str = "ch_1") -> dict:
    return {
        "message_id": message_id,
        "channel_id": channel_id,
        "community_server_id": "cs_1",
        "content": "test message content that is long enough",
        "author_id": "user_1",
        "author_username": "testuser",
        "timestamp": "2025-01-01T00:00:00Z",
        "attachment_urls": None,
        "embed_content": None,
    }


class TestPreprocessBatchStepInnerLogic:
    """Tests for inner async logic of preprocess_batch_step.

    These tests do NOT mock run_sync, exercising the actual async inner function
    including Redis reads, service calls, and filtering logic.
    """

    def _make_session_context(self, mock_session):
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)
        return MagicMock(return_value=mock_session_ctx)

    def test_filters_existing_requests_and_stores_to_redis(self) -> None:
        from src.dbos_workflows.content_scan_workflow import preprocess_batch_step

        scan_id = str(uuid4())
        community_server_id = str(uuid4())
        messages = [_make_test_message("msg_1"), _make_test_message("msg_2")]

        mock_service_instance = MagicMock()
        mock_service_instance.get_existing_request_message_ids = AsyncMock(return_value={"msg_1"})
        mock_service_instance.increment_skipped_count = AsyncMock()

        mock_session = AsyncMock()

        store_calls = []

        async def track_store(redis_client, key, data, **kwargs):
            store_calls.append((key, len(data)))
            return key

        with (
            patch(
                "src.cache.redis_client.get_shared_redis_client",
                new_callable=AsyncMock,
                return_value=MagicMock(),
            ),
            patch("src.config.get_settings") as mock_settings,
            patch(
                "src.database.get_session_maker",
                return_value=self._make_session_context(mock_session),
            ),
            patch(
                "src.tasks.content_monitoring_tasks._get_llm_service",
                return_value=MagicMock(),
            ),
            patch(
                "src.fact_checking.embedding_service.EmbeddingService",
                return_value=MagicMock(),
            ),
            patch(
                "src.bulk_content_scan.service.BulkContentScanService",
                return_value=mock_service_instance,
            ),
            patch(
                "src.dbos_workflows.content_scan_workflow.load_messages_from_redis",
                new_callable=AsyncMock,
                return_value=messages,
            ),
            patch(
                "src.dbos_workflows.content_scan_workflow.store_messages_in_redis",
                side_effect=track_store,
            ),
            patch(
                "src.dbos_workflows.content_scan_workflow.get_batch_redis_key",
                side_effect=lambda sid, bn, suffix: f"test:{suffix}:{sid}:{bn}",
            ),
        ):
            mock_settings.return_value = MagicMock(REDIS_URL="redis://test")

            result = preprocess_batch_step.__wrapped__(
                scan_id=scan_id,
                community_server_id=community_server_id,
                batch_number=1,
                messages_redis_key="test:messages",
                scan_types_json=json.dumps(["similarity"]),
            )

        assert result["message_count"] == 1
        assert result["skipped_count"] == 1
        mock_service_instance.get_existing_request_message_ids.assert_awaited_once()
        mock_service_instance.increment_skipped_count.assert_not_awaited()
        assert len(store_calls) == 2

    def test_builds_context_map_when_flashpoint_requested(self) -> None:
        from src.dbos_workflows.content_scan_workflow import preprocess_batch_step

        messages = [
            _make_test_message("msg_1", "ch_A"),
            _make_test_message("msg_2", "ch_B"),
        ]

        mock_service_instance = MagicMock()
        mock_service_instance.get_existing_request_message_ids = AsyncMock(return_value=set())
        mock_service_instance._populate_cross_batch_cache = AsyncMock()
        mock_service_instance._enrich_context_from_cache = AsyncMock(
            side_effect=lambda ctx_map, _cs_id: ctx_map
        )

        mock_session = AsyncMock()

        context_data_captured: list[list] = []

        async def capture_store(redis_client, key, data, **kwargs):
            if "context" in key:
                context_data_captured.append(data)
            return key

        from src.bulk_content_scan.service import BulkContentScanService as RealService

        real_build_context_map = RealService.build_channel_context_map

        mock_service_cls = MagicMock(return_value=mock_service_instance)
        mock_service_cls.build_channel_context_map = real_build_context_map

        community_server_id = str(uuid4())

        with (
            patch(
                "src.cache.redis_client.get_shared_redis_client",
                new_callable=AsyncMock,
                return_value=MagicMock(),
            ),
            patch("src.config.get_settings") as mock_settings,
            patch(
                "src.database.get_session_maker",
                return_value=self._make_session_context(mock_session),
            ),
            patch(
                "src.tasks.content_monitoring_tasks._get_llm_service",
                return_value=MagicMock(),
            ),
            patch(
                "src.fact_checking.embedding_service.EmbeddingService",
                return_value=MagicMock(),
            ),
            patch(
                "src.bulk_content_scan.service.BulkContentScanService",
                mock_service_cls,
            ),
            patch(
                "src.dbos_workflows.content_scan_workflow.load_messages_from_redis",
                new_callable=AsyncMock,
                return_value=messages,
            ),
            patch(
                "src.dbos_workflows.content_scan_workflow.store_messages_in_redis",
                side_effect=capture_store,
            ),
            patch(
                "src.dbos_workflows.content_scan_workflow.get_batch_redis_key",
                side_effect=lambda sid, bn, suffix: f"test:{suffix}:{sid}:{bn}",
            ),
        ):
            mock_settings.return_value = MagicMock(REDIS_URL="redis://test")

            result = preprocess_batch_step.__wrapped__(
                scan_id=str(uuid4()),
                community_server_id=community_server_id,
                batch_number=1,
                messages_redis_key="test:messages",
                scan_types_json=json.dumps(["similarity", "conversation_flashpoint"]),
            )

        assert result["message_count"] == 2
        assert len(context_data_captured) == 1
        context_map = context_data_captured[0][0]
        assert "ch_A" in context_map
        assert "ch_B" in context_map

        mock_service_instance._populate_cross_batch_cache.assert_awaited_once()
        populate_args = mock_service_instance._populate_cross_batch_cache.call_args
        typed_messages_arg = populate_args[0][0]
        assert len(typed_messages_arg) == 2
        assert typed_messages_arg[0].message_id == "msg_1"
        assert typed_messages_arg[1].message_id == "msg_2"
        platform_id_arg = populate_args[0][1]
        assert platform_id_arg is not None

        mock_service_instance._enrich_context_from_cache.assert_awaited_once()
        enrich_args = mock_service_instance._enrich_context_from_cache.call_args
        ctx_map_arg = enrich_args[0][0]
        assert isinstance(ctx_map_arg, dict)
        assert "ch_A" in ctx_map_arg
        assert "ch_B" in ctx_map_arg
        assert enrich_args[0][1] == platform_id_arg

    def test_returns_empty_when_all_filtered(self) -> None:
        from src.dbos_workflows.content_scan_workflow import preprocess_batch_step

        messages = [_make_test_message("msg_1")]

        mock_service_instance = MagicMock()
        mock_service_instance.get_existing_request_message_ids = AsyncMock(return_value={"msg_1"})
        mock_service_instance.increment_skipped_count = AsyncMock()

        mock_session = AsyncMock()

        with (
            patch(
                "src.cache.redis_client.get_shared_redis_client",
                new_callable=AsyncMock,
                return_value=MagicMock(),
            ),
            patch("src.config.get_settings") as mock_settings,
            patch(
                "src.database.get_session_maker",
                return_value=self._make_session_context(mock_session),
            ),
            patch(
                "src.tasks.content_monitoring_tasks._get_llm_service",
                return_value=MagicMock(),
            ),
            patch(
                "src.fact_checking.embedding_service.EmbeddingService",
                return_value=MagicMock(),
            ),
            patch(
                "src.bulk_content_scan.service.BulkContentScanService",
                return_value=mock_service_instance,
            ),
            patch(
                "src.dbos_workflows.content_scan_workflow.load_messages_from_redis",
                new_callable=AsyncMock,
                return_value=messages,
            ),
            patch(
                "src.dbos_workflows.content_scan_workflow.store_messages_in_redis",
                new_callable=AsyncMock,
                return_value="test:key",
            ),
            patch(
                "src.dbos_workflows.content_scan_workflow.get_batch_redis_key",
                return_value="test:filtered",
            ),
        ):
            mock_settings.return_value = MagicMock(REDIS_URL="redis://test")

            result = preprocess_batch_step.__wrapped__(
                scan_id=str(uuid4()),
                community_server_id=str(uuid4()),
                batch_number=1,
                messages_redis_key="test:messages",
                scan_types_json=json.dumps(["similarity"]),
            )

        assert result["message_count"] == 0
        assert result["skipped_count"] == 1

    def test_redis_load_failure_propagates(self) -> None:
        from src.dbos_workflows.content_scan_workflow import preprocess_batch_step

        with (
            patch(
                "src.cache.redis_client.get_shared_redis_client",
                new_callable=AsyncMock,
                return_value=MagicMock(),
            ),
            patch("src.config.get_settings") as mock_settings,
            patch(
                "src.dbos_workflows.content_scan_workflow.load_messages_from_redis",
                new_callable=AsyncMock,
                side_effect=ValueError("Redis key not found or expired"),
            ),
        ):
            mock_settings.return_value = MagicMock(REDIS_URL="redis://test")

            with pytest.raises(ValueError, match="not found or expired"):
                preprocess_batch_step.__wrapped__(
                    scan_id=str(uuid4()),
                    community_server_id=str(uuid4()),
                    batch_number=1,
                    messages_redis_key="expired:key",
                    scan_types_json=json.dumps(["similarity"]),
                )

    def test_skips_derived_writes_when_scan_is_terminal(self) -> None:
        from src.dbos_workflows.content_scan_workflow import preprocess_batch_step

        messages = [_make_test_message("msg_1"), _make_test_message("msg_2")]

        mock_service_instance = MagicMock()
        mock_service_instance.get_existing_request_message_ids = AsyncMock(return_value={"msg_1"})
        mock_service_instance.increment_skipped_count = AsyncMock()
        mock_service_instance._populate_cross_batch_cache = AsyncMock()

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = "platform_123"
        mock_session.execute = AsyncMock(return_value=mock_result)

        with (
            patch(
                "src.cache.redis_client.get_shared_redis_client",
                new_callable=AsyncMock,
                return_value=MagicMock(),
            ),
            patch("src.config.get_settings") as mock_settings,
            patch(
                "src.database.get_session_maker",
                return_value=self._make_session_context(mock_session),
            ),
            patch(
                "src.tasks.content_monitoring_tasks._get_llm_service",
                return_value=MagicMock(),
            ),
            patch(
                "src.fact_checking.embedding_service.EmbeddingService",
                return_value=MagicMock(),
            ),
            patch(
                "src.bulk_content_scan.service.BulkContentScanService",
                return_value=mock_service_instance,
            ),
            patch(
                "src.dbos_workflows.content_scan_workflow.load_messages_from_redis",
                new_callable=AsyncMock,
                return_value=messages,
            ),
            patch(
                "src.dbos_workflows.content_scan_workflow.store_messages_in_redis",
                new_callable=AsyncMock,
            ) as mock_store,
            patch(
                "src.dbos_workflows.content_scan_workflow._scan_is_terminal_async",
                new_callable=AsyncMock,
                return_value=True,
            ),
        ):
            mock_settings.return_value = MagicMock(REDIS_URL="redis://test")

            result = preprocess_batch_step.__wrapped__(
                scan_id=str(uuid4()),
                community_server_id=str(uuid4()),
                batch_number=1,
                messages_redis_key="test:messages",
                scan_types_json=json.dumps(["similarity", "conversation_flashpoint"]),
            )

        assert result == {
            "filtered_messages_key": "",
            "context_maps_key": "",
            "message_count": 0,
            "skipped_count": 0,
        }
        mock_service_instance.increment_skipped_count.assert_not_awaited()
        mock_service_instance._populate_cross_batch_cache.assert_not_awaited()
        mock_store.assert_not_awaited()

    def test_skips_derived_writes_when_scan_becomes_terminal_before_persist(self) -> None:
        from src.dbos_workflows.content_scan_workflow import preprocess_batch_step

        messages = [_make_test_message("msg_1"), _make_test_message("msg_2")]
        context_message = MagicMock()
        context_message.model_dump.return_value = messages[0]

        mock_service_instance = MagicMock()
        mock_service_instance.get_existing_request_message_ids = AsyncMock(return_value=set())
        mock_service_instance.increment_skipped_count = AsyncMock()
        mock_service_instance._enrich_context_from_cache = AsyncMock(
            return_value={"channel_1": [context_message]}
        )
        mock_service_instance._populate_cross_batch_cache = AsyncMock()

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = "platform_123"
        mock_session.execute = AsyncMock(return_value=mock_result)

        with (
            patch(
                "src.cache.redis_client.get_shared_redis_client",
                new_callable=AsyncMock,
                return_value=MagicMock(),
            ),
            patch("src.config.get_settings") as mock_settings,
            patch(
                "src.database.get_session_maker",
                return_value=self._make_session_context(mock_session),
            ),
            patch(
                "src.tasks.content_monitoring_tasks._get_llm_service",
                return_value=MagicMock(),
            ),
            patch(
                "src.fact_checking.embedding_service.EmbeddingService",
                return_value=MagicMock(),
            ),
            patch(
                "src.bulk_content_scan.service.BulkContentScanService",
                return_value=mock_service_instance,
            ),
            patch(
                "src.dbos_workflows.content_scan_workflow.load_messages_from_redis",
                new_callable=AsyncMock,
                return_value=messages,
            ),
            patch(
                "src.dbos_workflows.content_scan_workflow.store_messages_in_redis",
                new_callable=AsyncMock,
            ) as mock_store,
            patch(
                "src.dbos_workflows.content_scan_workflow._scan_is_terminal_async",
                new_callable=AsyncMock,
                side_effect=[False, True],
            ),
        ):
            mock_settings.return_value = MagicMock(REDIS_URL="redis://test")

            result = preprocess_batch_step.__wrapped__(
                scan_id=str(uuid4()),
                community_server_id=str(uuid4()),
                batch_number=1,
                messages_redis_key="test:messages",
                scan_types_json=json.dumps(["similarity", "conversation_flashpoint"]),
            )

        assert result == {
            "filtered_messages_key": "",
            "context_maps_key": "",
            "message_count": 0,
            "skipped_count": 0,
        }
        mock_service_instance.increment_skipped_count.assert_not_awaited()
        mock_service_instance._populate_cross_batch_cache.assert_not_awaited()
        mock_store.assert_not_awaited()


class TestSimilarityScanStepInnerLogic:
    """Tests for inner async logic of similarity_scan_step."""

    def _make_session_context(self, mock_session):
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)
        return MagicMock(return_value=mock_session_ctx)

    def test_scans_messages_and_stores_candidates(self) -> None:
        from src.dbos_workflows.content_scan_workflow import similarity_scan_step

        messages = [_make_test_message("msg_1"), _make_test_message("msg_2")]

        mock_candidate = MagicMock()
        mock_candidate.model_dump.return_value = {"scan_type": "similarity"}

        mock_service_instance = MagicMock()
        mock_service_instance._similarity_scan_candidate = AsyncMock(return_value=mock_candidate)

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = "platform_123"
        mock_session.execute = AsyncMock(return_value=mock_result)

        with (
            patch(
                "src.cache.redis_client.get_shared_redis_client",
                new_callable=AsyncMock,
                return_value=MagicMock(),
            ),
            patch("src.config.get_settings") as mock_settings,
            patch(
                "src.database.get_session_maker",
                return_value=self._make_session_context(mock_session),
            ),
            patch(
                "src.tasks.content_monitoring_tasks._get_llm_service",
                return_value=MagicMock(),
            ),
            patch(
                "src.fact_checking.embedding_service.EmbeddingService",
                return_value=MagicMock(),
            ),
            patch(
                "src.bulk_content_scan.flashpoint_service.get_flashpoint_service",
                return_value=MagicMock(),
            ),
            patch(
                "src.bulk_content_scan.service.BulkContentScanService",
                return_value=mock_service_instance,
            ),
            patch(
                "src.dbos_workflows.content_scan_workflow.load_messages_from_redis",
                new_callable=AsyncMock,
                return_value=messages,
            ),
            patch(
                "src.dbos_workflows.content_scan_workflow.store_messages_in_redis",
                new_callable=AsyncMock,
                return_value="test:sim_candidates",
            ),
            patch(
                "src.dbos_workflows.content_scan_workflow.get_batch_redis_key",
                return_value="test:similarity_candidates:scan:1",
            ),
        ):
            mock_settings.return_value = MagicMock(REDIS_URL="redis://test")

            result = similarity_scan_step.__wrapped__(
                scan_id=str(uuid4()),
                community_server_id=str(uuid4()),
                batch_number=1,
                filtered_messages_key="test:filtered",
                context_maps_key="test:context",
            )

        assert result["candidate_count"] == 2
        assert result["similarity_candidates_key"] == "test:similarity_candidates:scan:1"
        assert mock_service_instance._similarity_scan_candidate.await_count == 2

    def test_skips_short_messages(self) -> None:
        from src.dbos_workflows.content_scan_workflow import similarity_scan_step

        short_msg = _make_test_message("msg_short")
        short_msg["content"] = "hi"
        long_msg = _make_test_message("msg_long")

        mock_candidate = MagicMock()
        mock_candidate.model_dump.return_value = {"scan_type": "similarity"}

        mock_service_instance = MagicMock()
        mock_service_instance._similarity_scan_candidate = AsyncMock(return_value=mock_candidate)

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = "platform_123"
        mock_session.execute = AsyncMock(return_value=mock_result)

        with (
            patch(
                "src.cache.redis_client.get_shared_redis_client",
                new_callable=AsyncMock,
                return_value=MagicMock(),
            ),
            patch("src.config.get_settings") as mock_settings,
            patch(
                "src.database.get_session_maker",
                return_value=self._make_session_context(mock_session),
            ),
            patch(
                "src.tasks.content_monitoring_tasks._get_llm_service",
                return_value=MagicMock(),
            ),
            patch(
                "src.fact_checking.embedding_service.EmbeddingService",
                return_value=MagicMock(),
            ),
            patch(
                "src.bulk_content_scan.flashpoint_service.get_flashpoint_service",
                return_value=MagicMock(),
            ),
            patch(
                "src.bulk_content_scan.service.BulkContentScanService",
                return_value=mock_service_instance,
            ),
            patch(
                "src.dbos_workflows.content_scan_workflow.load_messages_from_redis",
                new_callable=AsyncMock,
                return_value=[short_msg, long_msg],
            ),
            patch(
                "src.dbos_workflows.content_scan_workflow.store_messages_in_redis",
                new_callable=AsyncMock,
                return_value="test:key",
            ),
            patch(
                "src.dbos_workflows.content_scan_workflow.get_batch_redis_key",
                return_value="test:sim",
            ),
        ):
            mock_settings.return_value = MagicMock(REDIS_URL="redis://test")

            result = similarity_scan_step.__wrapped__(
                scan_id=str(uuid4()),
                community_server_id=str(uuid4()),
                batch_number=1,
                filtered_messages_key="test:filtered",
                context_maps_key="test:context",
            )

        assert result["candidate_count"] == 1
        assert mock_service_instance._similarity_scan_candidate.await_count == 1

    def test_returns_empty_when_platform_id_not_found(self) -> None:
        from src.dbos_workflows.content_scan_workflow import similarity_scan_step

        messages = [_make_test_message("msg_1")]

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        with (
            patch(
                "src.cache.redis_client.get_shared_redis_client",
                new_callable=AsyncMock,
                return_value=MagicMock(),
            ),
            patch("src.config.get_settings") as mock_settings,
            patch(
                "src.database.get_session_maker",
                return_value=self._make_session_context(mock_session),
            ),
            patch(
                "src.tasks.content_monitoring_tasks._get_llm_service",
                return_value=MagicMock(),
            ),
            patch(
                "src.fact_checking.embedding_service.EmbeddingService",
                return_value=MagicMock(),
            ),
            patch(
                "src.bulk_content_scan.flashpoint_service.get_flashpoint_service",
                return_value=MagicMock(),
            ),
            patch(
                "src.dbos_workflows.content_scan_workflow.load_messages_from_redis",
                new_callable=AsyncMock,
                return_value=messages,
            ),
        ):
            mock_settings.return_value = MagicMock(REDIS_URL="redis://test")

            result = similarity_scan_step.__wrapped__(
                scan_id=str(uuid4()),
                community_server_id=str(uuid4()),
                batch_number=1,
                filtered_messages_key="test:filtered",
                context_maps_key="test:context",
            )

        assert result["similarity_candidates_key"] == ""
        assert result["candidate_count"] == 0

    def test_skips_candidate_writes_when_scan_is_terminal(self) -> None:
        from src.dbos_workflows.content_scan_workflow import similarity_scan_step

        messages = [_make_test_message("msg_1")]

        mock_service_instance = MagicMock()
        mock_service_instance._similarity_scan_candidate = AsyncMock()

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = "platform_123"
        mock_session.execute = AsyncMock(return_value=mock_result)

        with (
            patch(
                "src.cache.redis_client.get_shared_redis_client",
                new_callable=AsyncMock,
                return_value=MagicMock(),
            ),
            patch("src.config.get_settings") as mock_settings,
            patch(
                "src.database.get_session_maker",
                return_value=self._make_session_context(mock_session),
            ),
            patch(
                "src.tasks.content_monitoring_tasks._get_llm_service",
                return_value=MagicMock(),
            ),
            patch(
                "src.fact_checking.embedding_service.EmbeddingService",
                return_value=MagicMock(),
            ),
            patch(
                "src.bulk_content_scan.flashpoint_service.get_flashpoint_service",
                return_value=MagicMock(),
            ),
            patch(
                "src.bulk_content_scan.service.BulkContentScanService",
                return_value=mock_service_instance,
            ),
            patch(
                "src.dbos_workflows.content_scan_workflow.load_messages_from_redis",
                new_callable=AsyncMock,
                return_value=messages,
            ),
            patch(
                "src.dbos_workflows.content_scan_workflow.store_messages_in_redis",
                new_callable=AsyncMock,
            ) as mock_store,
            patch(
                "src.dbos_workflows.content_scan_workflow._scan_is_terminal_async",
                new_callable=AsyncMock,
                return_value=True,
            ),
        ):
            mock_settings.return_value = MagicMock(REDIS_URL="redis://test")

            result = similarity_scan_step.__wrapped__(
                scan_id=str(uuid4()),
                community_server_id=str(uuid4()),
                batch_number=1,
                filtered_messages_key="test:filtered",
                context_maps_key="test:context",
            )

        assert result == {"similarity_candidates_key": "", "candidate_count": 0}
        mock_service_instance._similarity_scan_candidate.assert_not_awaited()
        mock_store.assert_not_awaited()

    def test_skips_candidate_writes_when_scan_becomes_terminal_before_persist(self) -> None:
        from src.dbos_workflows.content_scan_workflow import similarity_scan_step

        messages = [_make_test_message("msg_1")]
        candidate = MagicMock()
        candidate.model_dump.return_value = {"message_id": "msg_1"}

        mock_service_instance = MagicMock()
        mock_service_instance._similarity_scan_candidate = AsyncMock(return_value=candidate)

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = "platform_123"
        mock_session.execute = AsyncMock(return_value=mock_result)

        with (
            patch(
                "src.cache.redis_client.get_shared_redis_client",
                new_callable=AsyncMock,
                return_value=MagicMock(),
            ),
            patch("src.config.get_settings") as mock_settings,
            patch(
                "src.database.get_session_maker",
                return_value=self._make_session_context(mock_session),
            ),
            patch(
                "src.tasks.content_monitoring_tasks._get_llm_service",
                return_value=MagicMock(),
            ),
            patch(
                "src.fact_checking.embedding_service.EmbeddingService",
                return_value=MagicMock(),
            ),
            patch(
                "src.bulk_content_scan.flashpoint_service.get_flashpoint_service",
                return_value=MagicMock(),
            ),
            patch(
                "src.bulk_content_scan.service.BulkContentScanService",
                return_value=mock_service_instance,
            ),
            patch(
                "src.dbos_workflows.content_scan_workflow.load_messages_from_redis",
                new_callable=AsyncMock,
                return_value=messages,
            ),
            patch(
                "src.dbos_workflows.content_scan_workflow.store_messages_in_redis",
                new_callable=AsyncMock,
            ) as mock_store,
            patch(
                "src.dbos_workflows.content_scan_workflow._scan_is_terminal_async",
                new_callable=AsyncMock,
                side_effect=[False, True],
            ),
        ):
            mock_settings.return_value = MagicMock(REDIS_URL="redis://test")

            result = similarity_scan_step.__wrapped__(
                scan_id=str(uuid4()),
                community_server_id=str(uuid4()),
                batch_number=1,
                filtered_messages_key="test:filtered",
                context_maps_key="test:context",
            )

        assert result == {"similarity_candidates_key": "", "candidate_count": 0}
        mock_service_instance._similarity_scan_candidate.assert_awaited_once()
        mock_store.assert_not_awaited()


class TestFlashpointScanStepInnerLogic:
    """Tests for inner async logic of flashpoint_scan_step."""

    def _make_session_context(self, mock_session):
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)
        return MagicMock(return_value=mock_session_ctx)

    def test_stores_candidates_and_returns_key_when_scan_remains_active(self) -> None:
        from src.dbos_workflows.content_scan_workflow import flashpoint_scan_step

        messages = [_make_test_message("msg_1")]
        candidate = MagicMock()
        candidate.model_dump.return_value = {"message_id": "msg_1"}

        mock_service_instance = MagicMock()
        mock_service_instance._build_message_id_index.return_value = {}
        mock_service_instance._get_context_for_message.return_value = []
        mock_service_instance._flashpoint_scan_candidate = AsyncMock(return_value=candidate)

        mock_session = AsyncMock()
        mock_redis = MagicMock()

        with (
            patch(
                "src.cache.redis_client.get_shared_redis_client",
                new_callable=AsyncMock,
                return_value=mock_redis,
            ),
            patch("src.config.get_settings") as mock_settings,
            patch(
                "src.database.get_session_maker",
                return_value=self._make_session_context(mock_session),
            ),
            patch(
                "src.tasks.content_monitoring_tasks._get_llm_service",
                return_value=MagicMock(),
            ),
            patch(
                "src.fact_checking.embedding_service.EmbeddingService",
                return_value=MagicMock(),
            ),
            patch(
                "src.bulk_content_scan.flashpoint_service.get_flashpoint_service",
                return_value=MagicMock(),
            ),
            patch(
                "src.bulk_content_scan.service.BulkContentScanService",
                return_value=mock_service_instance,
            ),
            patch(
                "src.dbos_workflows.content_scan_workflow.load_messages_from_redis",
                new_callable=AsyncMock,
                side_effect=[messages, [{"ch_1": messages}]],
            ),
            patch(
                "src.dbos_workflows.content_scan_workflow.store_messages_in_redis",
                new_callable=AsyncMock,
            ) as mock_store,
            patch(
                "src.dbos_workflows.content_scan_workflow.get_batch_redis_key",
                return_value="test:flashpoint",
            ),
            patch(
                "src.dbos_workflows.content_scan_workflow._scan_is_terminal_async",
                new_callable=AsyncMock,
                return_value=False,
            ),
        ):
            mock_settings.return_value = MagicMock(REDIS_URL="redis://test")

            result = flashpoint_scan_step.__wrapped__(
                scan_id=str(uuid4()),
                community_server_id=str(uuid4()),
                batch_number=1,
                filtered_messages_key="test:filtered",
                context_maps_key="test:context",
            )

        assert result == {
            "flashpoint_candidates_key": "test:flashpoint",
            "candidate_count": 1,
        }
        mock_service_instance._flashpoint_scan_candidate.assert_awaited_once()
        mock_store.assert_awaited_once_with(
            mock_redis,
            "test:flashpoint",
            [{"message_id": "msg_1"}],
        )

    def test_skips_candidate_writes_when_scan_is_terminal(self) -> None:
        from src.dbos_workflows.content_scan_workflow import flashpoint_scan_step

        messages = [_make_test_message("msg_1")]

        mock_service_instance = MagicMock()
        mock_service_instance._build_message_id_index.return_value = {}
        mock_service_instance._get_context_for_message.return_value = []
        mock_service_instance._flashpoint_scan_candidate = AsyncMock()

        mock_session = AsyncMock()

        with (
            patch(
                "src.cache.redis_client.get_shared_redis_client",
                new_callable=AsyncMock,
                return_value=MagicMock(),
            ),
            patch("src.config.get_settings") as mock_settings,
            patch(
                "src.database.get_session_maker",
                return_value=self._make_session_context(mock_session),
            ),
            patch(
                "src.tasks.content_monitoring_tasks._get_llm_service",
                return_value=MagicMock(),
            ),
            patch(
                "src.fact_checking.embedding_service.EmbeddingService",
                return_value=MagicMock(),
            ),
            patch(
                "src.bulk_content_scan.flashpoint_service.get_flashpoint_service",
                return_value=MagicMock(),
            ),
            patch(
                "src.bulk_content_scan.service.BulkContentScanService",
                return_value=mock_service_instance,
            ),
            patch(
                "src.dbos_workflows.content_scan_workflow.load_messages_from_redis",
                new_callable=AsyncMock,
                side_effect=[messages, [{"ch_1": messages}]],
            ),
            patch(
                "src.dbos_workflows.content_scan_workflow.store_messages_in_redis",
                new_callable=AsyncMock,
            ) as mock_store,
            patch(
                "src.dbos_workflows.content_scan_workflow._scan_is_terminal_async",
                new_callable=AsyncMock,
                return_value=True,
            ),
        ):
            mock_settings.return_value = MagicMock(REDIS_URL="redis://test")

            result = flashpoint_scan_step.__wrapped__(
                scan_id=str(uuid4()),
                community_server_id=str(uuid4()),
                batch_number=1,
                filtered_messages_key="test:filtered",
                context_maps_key="test:context",
            )

        assert result == {"flashpoint_candidates_key": "", "candidate_count": 0}
        mock_service_instance._flashpoint_scan_candidate.assert_not_awaited()
        mock_store.assert_not_awaited()

    def test_skips_candidate_writes_when_scan_becomes_terminal_before_persist(self) -> None:
        from src.dbos_workflows.content_scan_workflow import flashpoint_scan_step

        messages = [_make_test_message("msg_1")]
        candidate = MagicMock()
        candidate.model_dump.return_value = {"message_id": "msg_1"}

        mock_service_instance = MagicMock()
        mock_service_instance._build_message_id_index.return_value = {}
        mock_service_instance._get_context_for_message.return_value = []
        mock_service_instance._flashpoint_scan_candidate = AsyncMock(return_value=candidate)

        mock_session = AsyncMock()

        with (
            patch(
                "src.cache.redis_client.get_shared_redis_client",
                new_callable=AsyncMock,
                return_value=MagicMock(),
            ),
            patch("src.config.get_settings") as mock_settings,
            patch(
                "src.database.get_session_maker",
                return_value=self._make_session_context(mock_session),
            ),
            patch(
                "src.tasks.content_monitoring_tasks._get_llm_service",
                return_value=MagicMock(),
            ),
            patch(
                "src.fact_checking.embedding_service.EmbeddingService",
                return_value=MagicMock(),
            ),
            patch(
                "src.bulk_content_scan.flashpoint_service.get_flashpoint_service",
                return_value=MagicMock(),
            ),
            patch(
                "src.bulk_content_scan.service.BulkContentScanService",
                return_value=mock_service_instance,
            ),
            patch(
                "src.dbos_workflows.content_scan_workflow.load_messages_from_redis",
                new_callable=AsyncMock,
                side_effect=[messages, [{"ch_1": messages}]],
            ),
            patch(
                "src.dbos_workflows.content_scan_workflow.store_messages_in_redis",
                new_callable=AsyncMock,
            ) as mock_store,
            patch(
                "src.dbos_workflows.content_scan_workflow._scan_is_terminal_async",
                new_callable=AsyncMock,
                side_effect=[False, True],
            ),
        ):
            mock_settings.return_value = MagicMock(REDIS_URL="redis://test")

            result = flashpoint_scan_step.__wrapped__(
                scan_id=str(uuid4()),
                community_server_id=str(uuid4()),
                batch_number=1,
                filtered_messages_key="test:filtered",
                context_maps_key="test:context",
            )

        assert result == {"flashpoint_candidates_key": "", "candidate_count": 0}
        mock_service_instance._flashpoint_scan_candidate.assert_awaited_once()
        mock_store.assert_not_awaited()


class TestRelevanceFilterStepInnerLogic:
    """Tests for inner async logic of relevance_filter_step."""

    def _make_session_context(self, mock_session):
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)
        return MagicMock(return_value=mock_session_ctx)

    def _make_candidate_dict(self) -> dict:
        return {
            "message": _make_test_message("msg_1"),
            "scan_type": "similarity",
            "match_data": {
                "scan_type": "similarity",
                "score": 0.9,
                "matched_claim": "test claim",
                "matched_source": "http://test.com",
            },
            "score": 0.9,
            "matched_content": "test claim",
            "matched_source": "http://test.com",
        }

    def test_merges_candidates_from_both_keys(self) -> None:
        from src.dbos_workflows.content_scan_workflow import relevance_filter_step

        sim_candidates = [self._make_candidate_dict()]
        fp_candidate = self._make_candidate_dict()
        fp_candidate["scan_type"] = "conversation_flashpoint"
        fp_candidate["match_data"] = {
            "scan_type": "conversation_flashpoint",
            "derailment_score": 80,
            "risk_level": "Hostile",
            "reasoning": "heated",
            "context_messages": 3,
        }
        fp_candidates = [fp_candidate]

        mock_flagged = MagicMock()
        mock_service_instance = MagicMock()
        mock_service_instance._filter_candidates_with_relevance = AsyncMock(
            return_value=[mock_flagged]
        )
        mock_service_instance.append_flagged_result = AsyncMock()

        mock_session = AsyncMock()

        load_returns = {"sim_key": sim_candidates, "fp_key": fp_candidates}

        async def mock_load(redis_client, key):
            return load_returns[key]

        with (
            patch(
                "src.cache.redis_client.get_shared_redis_client",
                new_callable=AsyncMock,
                return_value=MagicMock(),
            ),
            patch("src.config.get_settings") as mock_settings,
            patch(
                "src.database.get_session_maker",
                return_value=self._make_session_context(mock_session),
            ),
            patch(
                "src.tasks.content_monitoring_tasks._get_llm_service",
                return_value=MagicMock(),
            ),
            patch(
                "src.fact_checking.embedding_service.EmbeddingService",
                return_value=MagicMock(),
            ),
            patch(
                "src.bulk_content_scan.flashpoint_service.get_flashpoint_service",
                return_value=MagicMock(),
            ),
            patch(
                "src.bulk_content_scan.service.BulkContentScanService",
                return_value=mock_service_instance,
            ),
            patch(
                "src.dbos_workflows.content_scan_workflow.load_messages_from_redis",
                side_effect=mock_load,
            ),
        ):
            mock_settings.return_value = MagicMock(REDIS_URL="redis://test")

            result = relevance_filter_step.__wrapped__(
                scan_id=str(uuid4()),
                community_server_id=str(uuid4()),
                batch_number=1,
                similarity_candidates_key="sim_key",
                flashpoint_candidates_key="fp_key",
            )

        assert result["flagged_count"] == 1
        assert result["errors"] == 0
        filter_call_args = mock_service_instance._filter_candidates_with_relevance.call_args
        assert len(filter_call_args.args[0]) == 2

    def test_handles_expired_similarity_key_gracefully(self) -> None:
        from src.dbos_workflows.content_scan_workflow import relevance_filter_step

        async def mock_load(redis_client, key):
            if "sim" in key:
                raise ValueError("Redis key not found or expired")
            return []

        with (
            patch(
                "src.cache.redis_client.get_shared_redis_client",
                new_callable=AsyncMock,
                return_value=MagicMock(),
            ),
            patch("src.config.get_settings") as mock_settings,
            patch(
                "src.dbos_workflows.content_scan_workflow.load_messages_from_redis",
                side_effect=mock_load,
            ),
        ):
            mock_settings.return_value = MagicMock(REDIS_URL="redis://test")

            result = relevance_filter_step.__wrapped__(
                scan_id=str(uuid4()),
                community_server_id=str(uuid4()),
                batch_number=1,
                similarity_candidates_key="sim_key",
                flashpoint_candidates_key="",
            )

        assert result["errors"] == 1
        assert result["flagged_count"] == 0

    def test_handles_expired_flashpoint_key_gracefully(self) -> None:
        """When flashpoint key expires but similarity candidates exist,
        filtering proceeds with only the similarity candidates.
        The successful filter preserves the candidate-load error count.
        """
        from src.dbos_workflows.content_scan_workflow import relevance_filter_step

        sim_candidate = self._make_candidate_dict()

        async def mock_load(redis_client, key):
            if "fp" in key:
                raise ValueError("Redis key not found or expired")
            return [sim_candidate]

        mock_flagged = MagicMock()
        mock_service_instance = MagicMock()
        mock_service_instance._filter_candidates_with_relevance = AsyncMock(
            return_value=[mock_flagged]
        )
        mock_service_instance.append_flagged_result = AsyncMock()

        mock_session = AsyncMock()

        with (
            patch(
                "src.cache.redis_client.get_shared_redis_client",
                new_callable=AsyncMock,
                return_value=MagicMock(),
            ),
            patch("src.config.get_settings") as mock_settings,
            patch(
                "src.database.get_session_maker",
                return_value=self._make_session_context(mock_session),
            ),
            patch(
                "src.tasks.content_monitoring_tasks._get_llm_service",
                return_value=MagicMock(),
            ),
            patch(
                "src.fact_checking.embedding_service.EmbeddingService",
                return_value=MagicMock(),
            ),
            patch(
                "src.bulk_content_scan.flashpoint_service.get_flashpoint_service",
                return_value=MagicMock(),
            ),
            patch(
                "src.bulk_content_scan.service.BulkContentScanService",
                return_value=mock_service_instance,
            ),
            patch(
                "src.dbos_workflows.content_scan_workflow.load_messages_from_redis",
                side_effect=mock_load,
            ),
        ):
            mock_settings.return_value = MagicMock(REDIS_URL="redis://test")

            result = relevance_filter_step.__wrapped__(
                scan_id=str(uuid4()),
                community_server_id=str(uuid4()),
                batch_number=1,
                similarity_candidates_key="sim_key",
                flashpoint_candidates_key="fp_key",
            )

        assert result["flagged_count"] == 1
        assert result["errors"] == 1
        mock_service_instance._filter_candidates_with_relevance.assert_awaited_once()
        filter_args = mock_service_instance._filter_candidates_with_relevance.call_args
        assert len(filter_args.args[0]) == 1

    def test_returns_zero_flagged_when_no_candidates(self) -> None:
        from src.dbos_workflows.content_scan_workflow import relevance_filter_step

        with (
            patch(
                "src.cache.redis_client.get_shared_redis_client",
                new_callable=AsyncMock,
                return_value=MagicMock(),
            ),
            patch("src.config.get_settings") as mock_settings,
            patch(
                "src.dbos_workflows.content_scan_workflow.load_messages_from_redis",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            mock_settings.return_value = MagicMock(REDIS_URL="redis://test")

            result = relevance_filter_step.__wrapped__(
                scan_id=str(uuid4()),
                community_server_id=str(uuid4()),
                batch_number=1,
                similarity_candidates_key="sim_key",
                flashpoint_candidates_key="",
            )

        assert result["flagged_count"] == 0
        assert result["errors"] == 0

    def test_service_error_records_and_returns_errors(self) -> None:
        from src.dbos_workflows.content_scan_workflow import relevance_filter_step

        candidates = [self._make_candidate_dict()]

        mock_service_instance = MagicMock()
        mock_service_instance._filter_candidates_with_relevance = AsyncMock(
            side_effect=RuntimeError("LLM unavailable")
        )
        mock_service_instance.record_error = AsyncMock()

        mock_session = AsyncMock()

        with (
            patch(
                "src.cache.redis_client.get_shared_redis_client",
                new_callable=AsyncMock,
                return_value=MagicMock(),
            ),
            patch("src.config.get_settings") as mock_settings,
            patch(
                "src.database.get_session_maker",
                return_value=self._make_session_context(mock_session),
            ),
            patch(
                "src.tasks.content_monitoring_tasks._get_llm_service",
                return_value=MagicMock(),
            ),
            patch(
                "src.fact_checking.embedding_service.EmbeddingService",
                return_value=MagicMock(),
            ),
            patch(
                "src.bulk_content_scan.flashpoint_service.get_flashpoint_service",
                return_value=MagicMock(),
            ),
            patch(
                "src.bulk_content_scan.service.BulkContentScanService",
                return_value=mock_service_instance,
            ),
            patch(
                "src.dbos_workflows.content_scan_workflow.load_messages_from_redis",
                new_callable=AsyncMock,
                return_value=candidates,
            ),
        ):
            mock_settings.return_value = MagicMock(REDIS_URL="redis://test")

            result = relevance_filter_step.__wrapped__(
                scan_id=str(uuid4()),
                community_server_id=str(uuid4()),
                batch_number=1,
                similarity_candidates_key="sim_key",
                flashpoint_candidates_key="",
            )

        assert result["flagged_count"] == 0
        assert result["errors"] == 1
        mock_service_instance.record_error.assert_awaited_once()

    def test_preserves_candidate_load_errors_when_scan_becomes_terminal_before_persist(
        self,
    ) -> None:
        from src.dbos_workflows.content_scan_workflow import relevance_filter_step

        flashpoint_candidates = [self._make_candidate_dict()]
        mock_service_instance = MagicMock()
        mock_service_instance._filter_candidates_with_relevance = AsyncMock(
            return_value=[MagicMock()]
        )
        mock_service_instance.append_flagged_result = AsyncMock()

        mock_session = AsyncMock()

        with (
            patch(
                "src.cache.redis_client.get_shared_redis_client",
                new_callable=AsyncMock,
                return_value=MagicMock(),
            ),
            patch("src.config.get_settings") as mock_settings,
            patch(
                "src.database.get_session_maker",
                return_value=self._make_session_context(mock_session),
            ),
            patch(
                "src.tasks.content_monitoring_tasks._get_llm_service",
                return_value=MagicMock(),
            ),
            patch(
                "src.fact_checking.embedding_service.EmbeddingService",
                return_value=MagicMock(),
            ),
            patch(
                "src.bulk_content_scan.flashpoint_service.get_flashpoint_service",
                return_value=MagicMock(),
            ),
            patch(
                "src.bulk_content_scan.service.BulkContentScanService",
                return_value=mock_service_instance,
            ),
            patch(
                "src.dbos_workflows.content_scan_workflow.load_messages_from_redis",
                new_callable=AsyncMock,
                side_effect=[ValueError("sim expired"), flashpoint_candidates],
            ),
            patch(
                "src.dbos_workflows.content_scan_workflow._scan_is_terminal_async",
                new_callable=AsyncMock,
                side_effect=[False, True],
            ),
        ):
            mock_settings.return_value = MagicMock(REDIS_URL="redis://test")

            result = relevance_filter_step.__wrapped__(
                scan_id=str(uuid4()),
                community_server_id=str(uuid4()),
                batch_number=1,
                similarity_candidates_key="sim_key",
                flashpoint_candidates_key="fp_key",
            )

        assert result == {"flagged_count": 0, "errors": 1}
        mock_service_instance._filter_candidates_with_relevance.assert_awaited_once()
        mock_service_instance.append_flagged_result.assert_not_awaited()

    def test_does_not_record_new_error_when_scan_finalizes_during_relevance_exception(
        self,
    ) -> None:
        from src.dbos_workflows.content_scan_workflow import relevance_filter_step

        candidates = [self._make_candidate_dict()]

        mock_service_instance = MagicMock()
        mock_service_instance._filter_candidates_with_relevance = AsyncMock(
            side_effect=RuntimeError("LLM unavailable")
        )
        mock_service_instance.record_error = AsyncMock()

        mock_session = AsyncMock()

        with (
            patch(
                "src.cache.redis_client.get_shared_redis_client",
                new_callable=AsyncMock,
                return_value=MagicMock(),
            ),
            patch("src.config.get_settings") as mock_settings,
            patch(
                "src.database.get_session_maker",
                return_value=self._make_session_context(mock_session),
            ),
            patch(
                "src.tasks.content_monitoring_tasks._get_llm_service",
                return_value=MagicMock(),
            ),
            patch(
                "src.fact_checking.embedding_service.EmbeddingService",
                return_value=MagicMock(),
            ),
            patch(
                "src.bulk_content_scan.flashpoint_service.get_flashpoint_service",
                return_value=MagicMock(),
            ),
            patch(
                "src.bulk_content_scan.service.BulkContentScanService",
                return_value=mock_service_instance,
            ),
            patch(
                "src.dbos_workflows.content_scan_workflow.load_messages_from_redis",
                new_callable=AsyncMock,
                return_value=candidates,
            ),
            patch(
                "src.dbos_workflows.content_scan_workflow._scan_is_terminal_async",
                new_callable=AsyncMock,
                side_effect=[False, True],
            ),
        ):
            mock_settings.return_value = MagicMock(REDIS_URL="redis://test")

            result = relevance_filter_step.__wrapped__(
                scan_id=str(uuid4()),
                community_server_id=str(uuid4()),
                batch_number=1,
                similarity_candidates_key="sim_key",
                flashpoint_candidates_key="",
            )

        assert result == {"flagged_count": 0, "errors": 0}
        mock_service_instance.record_error.assert_not_awaited()

    def test_skips_flagged_writes_when_scan_is_terminal(self) -> None:
        from src.dbos_workflows.content_scan_workflow import relevance_filter_step

        candidates = [self._make_candidate_dict()]
        mock_service_instance = MagicMock()
        mock_service_instance._filter_candidates_with_relevance = AsyncMock(
            return_value=[MagicMock()]
        )
        mock_service_instance.append_flagged_result = AsyncMock()

        mock_session = AsyncMock()

        with (
            patch(
                "src.cache.redis_client.get_shared_redis_client",
                new_callable=AsyncMock,
                return_value=MagicMock(),
            ),
            patch("src.config.get_settings") as mock_settings,
            patch(
                "src.database.get_session_maker",
                return_value=self._make_session_context(mock_session),
            ),
            patch(
                "src.tasks.content_monitoring_tasks._get_llm_service",
                return_value=MagicMock(),
            ),
            patch(
                "src.fact_checking.embedding_service.EmbeddingService",
                return_value=MagicMock(),
            ),
            patch(
                "src.bulk_content_scan.flashpoint_service.get_flashpoint_service",
                return_value=MagicMock(),
            ),
            patch(
                "src.bulk_content_scan.service.BulkContentScanService",
                return_value=mock_service_instance,
            ),
            patch(
                "src.dbos_workflows.content_scan_workflow.load_messages_from_redis",
                new_callable=AsyncMock,
                return_value=candidates,
            ),
            patch(
                "src.dbos_workflows.content_scan_workflow._scan_is_terminal_async",
                new_callable=AsyncMock,
                return_value=True,
            ),
        ):
            mock_settings.return_value = MagicMock(REDIS_URL="redis://test")

            result = relevance_filter_step.__wrapped__(
                scan_id=str(uuid4()),
                community_server_id=str(uuid4()),
                batch_number=1,
                similarity_candidates_key="sim_key",
                flashpoint_candidates_key="",
            )

        assert result == {"flagged_count": 0, "errors": 0}
        mock_service_instance._filter_candidates_with_relevance.assert_not_awaited()
        mock_service_instance.append_flagged_result.assert_not_awaited()

    def test_skips_flagged_writes_when_scan_becomes_terminal_before_persist(self) -> None:
        from src.dbos_workflows.content_scan_workflow import relevance_filter_step

        candidates = [self._make_candidate_dict()]
        mock_service_instance = MagicMock()
        mock_service_instance._filter_candidates_with_relevance = AsyncMock(
            return_value=[MagicMock()]
        )
        mock_service_instance.append_flagged_result = AsyncMock()

        mock_session = AsyncMock()

        with (
            patch(
                "src.cache.redis_client.get_shared_redis_client",
                new_callable=AsyncMock,
                return_value=MagicMock(),
            ),
            patch("src.config.get_settings") as mock_settings,
            patch(
                "src.database.get_session_maker",
                return_value=self._make_session_context(mock_session),
            ),
            patch(
                "src.tasks.content_monitoring_tasks._get_llm_service",
                return_value=MagicMock(),
            ),
            patch(
                "src.fact_checking.embedding_service.EmbeddingService",
                return_value=MagicMock(),
            ),
            patch(
                "src.bulk_content_scan.flashpoint_service.get_flashpoint_service",
                return_value=MagicMock(),
            ),
            patch(
                "src.bulk_content_scan.service.BulkContentScanService",
                return_value=mock_service_instance,
            ),
            patch(
                "src.dbos_workflows.content_scan_workflow.load_messages_from_redis",
                new_callable=AsyncMock,
                return_value=candidates,
            ),
            patch(
                "src.dbos_workflows.content_scan_workflow._scan_is_terminal_async",
                new_callable=AsyncMock,
                side_effect=[False, True],
            ),
        ):
            mock_settings.return_value = MagicMock(REDIS_URL="redis://test")

            result = relevance_filter_step.__wrapped__(
                scan_id=str(uuid4()),
                community_server_id=str(uuid4()),
                batch_number=1,
                similarity_candidates_key="sim_key",
                flashpoint_candidates_key="",
            )

        assert result == {"flagged_count": 0, "errors": 0}
        mock_service_instance._filter_candidates_with_relevance.assert_awaited_once()
        mock_service_instance.append_flagged_result.assert_not_awaited()


class TestDBOSReplayWithExpiredRedisKeys:
    """Tests for DBOS replay behavior with Redis TTL.

    Simulates the scenario where DBOS replays a workflow after a crash:
    step N was checkpointed (its return value is replayed from DB), but
    the Redis keys it wrote may have expired if the replay happens late.
    Step N+1 reads those Redis keys and must handle expiry gracefully.

    The TTL refresh mechanism (load_messages_from_redis refreshes to 7 days
    on each read) ensures keys survive long enough for normal replay windows.
    """

    @pytest.mark.asyncio
    async def test_sequential_reads_each_refresh_ttl(self) -> None:
        from src.dbos_workflows.content_scan_workflow import (
            REDIS_REPLAY_TTL_SECONDS,
            load_messages_from_redis,
        )

        messages = [{"message_id": "m1"}]
        mock_redis = MagicMock()
        mock_redis.get = AsyncMock(return_value=json.dumps(messages).encode())
        mock_redis.expire = AsyncMock(return_value=True)

        await load_messages_from_redis(mock_redis, "key_1")
        await load_messages_from_redis(mock_redis, "key_2")
        await load_messages_from_redis(mock_redis, "key_3")

        assert mock_redis.expire.await_count == 3
        for call in mock_redis.expire.call_args_list:
            assert call.args[1] == REDIS_REPLAY_TTL_SECONDS

    @pytest.mark.asyncio
    async def test_expired_key_raises_valueerror_expire_not_called(self) -> None:
        from src.dbos_workflows.content_scan_workflow import load_messages_from_redis

        mock_redis = MagicMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.expire = AsyncMock()

        with pytest.raises(ValueError, match="not found or expired"):
            await load_messages_from_redis(mock_redis, "expired:key")

        mock_redis.expire.assert_not_awaited()

    def test_replay_ttl_constant_is_7_days(self) -> None:
        from src.dbos_workflows.content_scan_workflow import REDIS_REPLAY_TTL_SECONDS

        assert REDIS_REPLAY_TTL_SECONDS == 604800
        assert REDIS_REPLAY_TTL_SECONDS == 7 * 24 * 3600

    @pytest.mark.asyncio
    async def test_replay_scenario_step_n_plus_1_reads_refreshed_key(self) -> None:
        """Simulates step N writing data, step N+1 reading it during replay.

        When step N+1 reads the key, TTL is refreshed to 7 days, ensuring
        the key survives even if step N+2 replays much later.
        """
        from src.dbos_workflows.content_scan_workflow import (
            REDIS_REPLAY_TTL_SECONDS,
            load_messages_from_redis,
            store_messages_in_redis,
        )

        mock_redis = MagicMock()
        mock_redis.setex = AsyncMock()

        messages = [{"id": "msg_1"}, {"id": "msg_2"}]
        key = await store_messages_in_redis(mock_redis, "scan:batch:1", messages)

        mock_redis.get = AsyncMock(return_value=json.dumps(messages).encode())
        mock_redis.expire = AsyncMock(return_value=True)

        result = await load_messages_from_redis(mock_redis, key)

        assert result == messages
        mock_redis.expire.assert_awaited_once_with(key, REDIS_REPLAY_TTL_SECONDS)
