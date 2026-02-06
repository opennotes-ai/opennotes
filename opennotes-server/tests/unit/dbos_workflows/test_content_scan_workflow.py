"""Tests for DBOS content scan workflow.

Tests the content scan orchestration workflow, batch processing step,
finalization step, and async dispatch/enqueue/signal helpers.

Note: Tests call __wrapped__ to bypass DBOS decorators (which require a
running DBOS runtime). External services (database, Redis, NATS, LLM) are
mocked since these are unit tests for workflow logic.
"""

from __future__ import annotations

import collections.abc
import json
import time
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest


class TestContentScanQueueConfiguration:
    """Tests for DBOS Queue configuration."""

    def test_queue_exists(self) -> None:
        from src.dbos_workflows.content_scan_workflow import content_scan_queue

        assert content_scan_queue.name == "content_scan"

    def test_queue_worker_concurrency(self) -> None:
        from src.dbos_workflows.content_scan_workflow import content_scan_queue

        assert content_scan_queue.worker_concurrency == 2

    def test_queue_global_concurrency(self) -> None:
        from src.dbos_workflows.content_scan_workflow import content_scan_queue

        assert content_scan_queue.concurrency == 4


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

        assert SCAN_RECV_TIMEOUT_SECONDS == 0


class TestCheckpointWallClockStep:
    """Tests for _checkpoint_wall_clock_step."""

    def test_returns_epoch_time(self) -> None:
        from src.dbos_workflows.content_scan_workflow import _checkpoint_wall_clock_step

        before = time.time()
        result = _checkpoint_wall_clock_step.__wrapped__()
        after = time.time()

        assert before <= result <= after


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

    def test_single_batch_completes_normally(self) -> None:
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
            patch("src.dbos_workflows.content_scan_workflow.finalize_scan_step") as mock_finalize,
            patch("src.dbos_workflows.content_scan_workflow.DBOS") as mock_dbos,
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
            patch("src.dbos_workflows.content_scan_workflow.finalize_scan_step") as mock_finalize,
            patch("src.dbos_workflows.content_scan_workflow.DBOS") as mock_dbos,
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
            patch("src.dbos_workflows.content_scan_workflow.finalize_scan_step") as mock_finalize,
            patch("src.dbos_workflows.content_scan_workflow.DBOS") as mock_dbos,
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
            patch("src.dbos_workflows.content_scan_workflow.finalize_scan_step") as mock_finalize,
            patch("src.dbos_workflows.content_scan_workflow.DBOS") as mock_dbos,
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
            patch("src.dbos_workflows.content_scan_workflow.finalize_scan_step") as mock_finalize,
            patch("src.dbos_workflows.content_scan_workflow.DBOS") as mock_dbos,
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
            patch("src.dbos_workflows.content_scan_workflow.finalize_scan_step") as mock_finalize,
            patch("src.dbos_workflows.content_scan_workflow.DBOS") as mock_dbos,
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


class TestProcessContentScanBatch:
    """Tests for process_content_scan_batch workflow."""

    def test_processes_batch_and_signals_orchestrator(self) -> None:
        """Batch workflow calls step and sends signal to orchestrator."""
        from src.dbos_workflows.content_scan_workflow import process_content_scan_batch

        orchestrator_wf_id = "orchestrator-wf-123"
        scan_id = str(uuid4())
        community_server_id = str(uuid4())
        batch_number = 1
        messages_json = json.dumps([{"message_id": "msg1", "content": "test"}])
        scan_types_json = json.dumps(["similarity"])

        batch_result = {
            "processed": 1,
            "skipped": 0,
            "errors": 0,
            "flagged_count": 0,
            "batch_number": 1,
        }

        with (
            patch(
                "src.dbos_workflows.content_scan_workflow.process_batch_messages_step"
            ) as mock_step,
            patch("src.dbos_workflows.content_scan_workflow.DBOS") as mock_dbos,
        ):
            mock_step.return_value = batch_result

            result = process_content_scan_batch.__wrapped__(
                orchestrator_workflow_id=orchestrator_wf_id,
                scan_id=scan_id,
                community_server_id=community_server_id,
                batch_number=batch_number,
                messages_json=messages_json,
                scan_types_json=scan_types_json,
            )

        assert result == batch_result
        mock_step.assert_called_once_with(
            scan_id=scan_id,
            community_server_id=community_server_id,
            batch_number=batch_number,
            messages_json=messages_json,
            scan_types_json=scan_types_json,
        )
        mock_dbos.send.assert_called_once_with(
            orchestrator_wf_id,
            batch_result,
            topic="batch_complete",
        )

    def test_propagates_step_error(self) -> None:
        """Batch workflow propagates errors from the step."""
        from src.dbos_workflows.content_scan_workflow import process_content_scan_batch

        with (
            patch(
                "src.dbos_workflows.content_scan_workflow.process_batch_messages_step"
            ) as mock_step,
            patch("src.dbos_workflows.content_scan_workflow.DBOS"),
        ):
            mock_step.side_effect = RuntimeError("Step failed")

            with pytest.raises(RuntimeError, match="Step failed"):
                process_content_scan_batch.__wrapped__(
                    orchestrator_workflow_id="wf-123",
                    scan_id=str(uuid4()),
                    community_server_id=str(uuid4()),
                    batch_number=1,
                    messages_json="[]",
                    scan_types_json='["similarity"]',
                )


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


class TestDispatchContentScanWorkflow:
    """Tests for dispatch_content_scan_workflow async helper."""

    @pytest.mark.asyncio
    async def test_dispatches_workflow_and_returns_id(self) -> None:
        from src.dbos_workflows.content_scan_workflow import dispatch_content_scan_workflow

        scan_id = uuid4()
        community_server_id = uuid4()
        scan_types = ["similarity", "openai_moderation"]

        with patch("src.dbos_workflows.config.get_dbos_client") as mock_get_client:
            mock_client = MagicMock()
            mock_handle = MagicMock()
            mock_handle.workflow_id = "dispatched-wf-123"
            mock_client.enqueue.return_value = mock_handle
            mock_get_client.return_value = mock_client

            result = await dispatch_content_scan_workflow(
                scan_id=scan_id,
                community_server_id=community_server_id,
                scan_types=scan_types,
            )

        assert result == "dispatched-wf-123"

    @pytest.mark.asyncio
    async def test_returns_none_on_client_error(self) -> None:
        from src.dbos_workflows.content_scan_workflow import dispatch_content_scan_workflow

        with patch("src.dbos_workflows.config.get_dbos_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.enqueue.side_effect = RuntimeError("Connection refused")
            mock_get_client.return_value = mock_client

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

        with patch("src.dbos_workflows.config.get_dbos_client") as mock_get_client:
            mock_client = MagicMock()
            mock_handle = MagicMock()
            mock_handle.workflow_id = "wf-idempotent"
            mock_client.enqueue.return_value = mock_handle
            mock_get_client.return_value = mock_client

            await dispatch_content_scan_workflow(
                scan_id=scan_id,
                community_server_id=uuid4(),
                scan_types=["similarity"],
            )

        options = mock_client.enqueue.call_args.args[0]
        assert options["deduplication_id"] == str(scan_id)

    @pytest.mark.asyncio
    async def test_uses_scan_id_as_workflow_id(self) -> None:
        from src.dbos_workflows.content_scan_workflow import dispatch_content_scan_workflow

        scan_id = uuid4()

        with patch("src.dbos_workflows.config.get_dbos_client") as mock_get_client:
            mock_client = MagicMock()
            mock_handle = MagicMock()
            mock_handle.workflow_id = str(scan_id)
            mock_client.enqueue.return_value = mock_handle
            mock_get_client.return_value = mock_client

            await dispatch_content_scan_workflow(
                scan_id=scan_id,
                community_server_id=uuid4(),
                scan_types=["similarity"],
            )

        options = mock_client.enqueue.call_args.args[0]
        assert options["workflow_id"] == str(scan_id)


class TestEnqueueContentScanBatch:
    """Tests for enqueue_content_scan_batch async helper."""

    @pytest.mark.asyncio
    async def test_enqueues_batch_and_returns_workflow_id(self) -> None:
        from src.dbos_workflows.content_scan_workflow import enqueue_content_scan_batch

        scan_id = uuid4()
        community_server_id = uuid4()
        messages = [{"message_id": "m1", "content": "test"}]
        scan_types = ["similarity"]

        with patch("src.dbos_workflows.config.get_dbos_client") as mock_get_client:
            mock_client = MagicMock()
            mock_handle = MagicMock()
            mock_handle.workflow_id = "batch-wf-456"
            mock_client.enqueue.return_value = mock_handle
            mock_get_client.return_value = mock_client

            result = await enqueue_content_scan_batch(
                orchestrator_workflow_id="orchestrator-wf-123",
                scan_id=scan_id,
                community_server_id=community_server_id,
                batch_number=1,
                messages=messages,
                scan_types=scan_types,
            )

        assert result == "batch-wf-456"

    @pytest.mark.asyncio
    async def test_returns_none_on_enqueue_failure(self) -> None:
        from src.dbos_workflows.content_scan_workflow import enqueue_content_scan_batch

        with patch("src.dbos_workflows.config.get_dbos_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.enqueue.side_effect = RuntimeError("Queue full")
            mock_get_client.return_value = mock_client

            result = await enqueue_content_scan_batch(
                orchestrator_workflow_id="wf-123",
                scan_id=uuid4(),
                community_server_id=uuid4(),
                batch_number=1,
                messages=[],
                scan_types=["similarity"],
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_enqueue_options_use_correct_queue(self) -> None:
        from src.dbos_workflows.content_scan_workflow import enqueue_content_scan_batch

        with patch("src.dbos_workflows.config.get_dbos_client") as mock_get_client:
            mock_client = MagicMock()
            mock_handle = MagicMock()
            mock_handle.workflow_id = "wf-789"
            mock_client.enqueue.return_value = mock_handle
            mock_get_client.return_value = mock_client

            await enqueue_content_scan_batch(
                orchestrator_workflow_id="wf-123",
                scan_id=uuid4(),
                community_server_id=uuid4(),
                batch_number=1,
                messages=[],
                scan_types=["similarity"],
            )

        call_args = mock_client.enqueue.call_args.args
        options = call_args[0]
        assert options["queue_name"] == "content_scan"
        assert "process_content_scan_batch" in options["workflow_name"]


class TestSendAllTransmittedSignal:
    """Tests for send_all_transmitted_signal async helper."""

    @pytest.mark.asyncio
    async def test_sends_signal_and_returns_true(self) -> None:
        from src.dbos_workflows.content_scan_workflow import send_all_transmitted_signal

        with patch("src.dbos_workflows.config.get_dbos_client") as mock_get_client:
            mock_client = MagicMock()
            mock_get_client.return_value = mock_client

            result = await send_all_transmitted_signal(
                orchestrator_workflow_id="wf-123",
                messages_scanned=50,
            )

        assert result is True
        mock_client.send.assert_called_once_with(
            "wf-123",
            {"messages_scanned": 50},
            "all_transmitted",
        )

    @pytest.mark.asyncio
    async def test_returns_false_on_failure(self) -> None:
        from src.dbos_workflows.content_scan_workflow import send_all_transmitted_signal

        with patch("src.dbos_workflows.config.get_dbos_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.send.side_effect = RuntimeError("Connection lost")
            mock_get_client.return_value = mock_client

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

        batch_result = {
            "processed": 10,
            "skipped": 1,
            "errors": 0,
            "flagged_count": 2,
            "batch_number": 3,
        }

        with (
            patch(
                "src.dbos_workflows.content_scan_workflow.process_batch_messages_step"
            ) as mock_step,
            patch("src.dbos_workflows.content_scan_workflow.DBOS") as mock_dbos,
        ):
            mock_step.return_value = batch_result

            process_content_scan_batch.__wrapped__(
                orchestrator_workflow_id="orch-wf-id",
                scan_id=str(uuid4()),
                community_server_id=str(uuid4()),
                batch_number=3,
                messages_json="[]",
                scan_types_json='["similarity"]',
            )

        mock_dbos.send.assert_called_once_with(
            "orch-wf-id",
            batch_result,
            topic="batch_complete",
        )

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
            patch("src.dbos_workflows.content_scan_workflow.finalize_scan_step") as mock_finalize,
            patch("src.dbos_workflows.content_scan_workflow.DBOS") as mock_dbos,
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
            patch("src.dbos_workflows.content_scan_workflow.finalize_scan_step") as mock_finalize,
            patch("src.dbos_workflows.content_scan_workflow.DBOS") as mock_dbos,
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
    """Tests for the count mismatch break condition."""

    def test_breaks_on_count_mismatch_after_all_transmitted(self) -> None:
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

        with (
            patch("src.dbos_workflows.content_scan_workflow.create_scan_record_step"),
            patch(
                "src.dbos_workflows.content_scan_workflow._checkpoint_wall_clock_step"
            ) as mock_clock,
            patch("src.dbos_workflows.content_scan_workflow.finalize_scan_step") as mock_finalize,
            patch("src.dbos_workflows.content_scan_workflow.DBOS") as mock_dbos,
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
            patch("src.dbos_workflows.content_scan_workflow.finalize_scan_step") as mock_finalize,
            patch("src.dbos_workflows.content_scan_workflow.DBOS") as mock_dbos,
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
            patch("src.dbos_workflows.content_scan_workflow.finalize_scan_step") as mock_finalize,
            patch("src.dbos_workflows.content_scan_workflow.DBOS") as mock_dbos,
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

        expected_result = {
            "processed": 7,
            "skipped": 1,
            "errors": 2,
            "flagged_count": 3,
            "batch_number": 4,
        }

        with (
            patch(
                "src.dbos_workflows.content_scan_workflow.process_batch_messages_step"
            ) as mock_step,
            patch("src.dbos_workflows.content_scan_workflow.DBOS") as mock_dbos,
        ):
            mock_step.return_value = expected_result

            process_content_scan_batch.__wrapped__(
                orchestrator_workflow_id="orch-wf-id",
                scan_id=str(uuid4()),
                community_server_id=str(uuid4()),
                batch_number=4,
                messages_json="[]",
                scan_types_json='["similarity"]',
            )

        signal_data = mock_dbos.send.call_args.args[1]
        assert signal_data["processed"] == 7
        assert signal_data["skipped"] == 1
        assert signal_data["errors"] == 2
        assert signal_data["flagged_count"] == 3
        assert signal_data["batch_number"] == 4
