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
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


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

    def _patch_all_steps(self):
        """Patch all per-strategy steps for workflow-level tests."""
        return (
            patch("src.dbos_workflows.content_scan_workflow.preprocess_batch_step"),
            patch("src.dbos_workflows.content_scan_workflow.similarity_scan_step"),
            patch("src.dbos_workflows.content_scan_workflow.flashpoint_scan_step"),
            patch("src.dbos_workflows.content_scan_workflow.relevance_filter_step"),
            patch("src.dbos_workflows.content_scan_workflow.DBOS"),
        )

    def test_calls_per_strategy_steps_in_order(self) -> None:
        """Batch workflow calls preprocess, similarity, and relevance steps."""
        from src.dbos_workflows.content_scan_workflow import process_content_scan_batch

        scan_id = str(uuid4())
        community_server_id = str(uuid4())
        redis_key = "test:bulk_scan:messages:scan:1"
        scan_types_json = json.dumps(["similarity"])

        with (
            patch(
                "src.dbos_workflows.content_scan_workflow.preprocess_batch_step"
            ) as mock_preprocess,
            patch("src.dbos_workflows.content_scan_workflow.similarity_scan_step") as mock_sim,
            patch("src.dbos_workflows.content_scan_workflow.flashpoint_scan_step") as mock_fp,
            patch("src.dbos_workflows.content_scan_workflow.relevance_filter_step") as mock_filter,
            patch("src.dbos_workflows.content_scan_workflow.DBOS") as mock_dbos,
            patch("src.dbos_workflows.content_scan_workflow.TokenGate"),
        ):
            mock_preprocess.return_value = {
                "filtered_messages_key": "test:filtered",
                "context_maps_key": "test:context",
                "message_count": 1,
                "skipped_count": 0,
            }
            mock_sim.return_value = {"similarity_candidates_key": "test:sim", "candidate_count": 1}
            mock_filter.return_value = {"flagged_count": 1, "errors": 0}

            result = process_content_scan_batch.__wrapped__(
                orchestrator_workflow_id="orch-wf",
                scan_id=scan_id,
                community_server_id=community_server_id,
                batch_number=1,
                messages_redis_key=redis_key,
                scan_types_json=scan_types_json,
            )

        mock_preprocess.assert_called_once()
        mock_sim.assert_called_once()
        mock_fp.assert_not_called()
        mock_filter.assert_called_once()
        assert result["processed"] == 1
        assert result["flagged_count"] == 1
        mock_dbos.send.assert_called_once()

    def test_passes_redis_key_to_preprocess_step(self) -> None:
        """Batch workflow passes messages_redis_key to preprocess step."""
        from src.dbos_workflows.content_scan_workflow import process_content_scan_batch

        redis_key = "test:bulk_scan:messages:scan-id:1"

        with (
            patch("src.dbos_workflows.content_scan_workflow.preprocess_batch_step") as mock_pre,
            patch("src.dbos_workflows.content_scan_workflow.similarity_scan_step"),
            patch("src.dbos_workflows.content_scan_workflow.relevance_filter_step") as mock_filter,
            patch("src.dbos_workflows.content_scan_workflow.DBOS"),
        ):
            mock_pre.return_value = {
                "filtered_messages_key": "k",
                "context_maps_key": "k",
                "message_count": 1,
                "skipped_count": 0,
            }
            mock_filter.return_value = {"flagged_count": 0, "errors": 0}

            process_content_scan_batch.__wrapped__(
                orchestrator_workflow_id="orch",
                scan_id=str(uuid4()),
                community_server_id=str(uuid4()),
                batch_number=1,
                messages_redis_key=redis_key,
                scan_types_json=json.dumps(["similarity"]),
            )

        assert mock_pre.call_args.kwargs["messages_redis_key"] == redis_key

    def test_includes_flashpoint_step_when_scan_type_requested(self) -> None:
        """Flashpoint step is called when conversation_flashpoint is in scan_types."""
        from src.dbos_workflows.content_scan_workflow import process_content_scan_batch

        scan_types_json = json.dumps(["similarity", "conversation_flashpoint"])

        with (
            patch("src.dbos_workflows.content_scan_workflow.preprocess_batch_step") as mock_pre,
            patch("src.dbos_workflows.content_scan_workflow.similarity_scan_step") as mock_sim,
            patch("src.dbos_workflows.content_scan_workflow.flashpoint_scan_step") as mock_fp,
            patch("src.dbos_workflows.content_scan_workflow.relevance_filter_step") as mock_filter,
            patch("src.dbos_workflows.content_scan_workflow.DBOS"),
        ):
            mock_pre.return_value = {
                "filtered_messages_key": "k",
                "context_maps_key": "k",
                "message_count": 1,
                "skipped_count": 0,
            }
            mock_sim.return_value = {"similarity_candidates_key": "s", "candidate_count": 1}
            mock_fp.return_value = {"flashpoint_candidates_key": "f", "candidate_count": 1}
            mock_filter.return_value = {"flagged_count": 2, "errors": 0}

            result = process_content_scan_batch.__wrapped__(
                orchestrator_workflow_id="orch",
                scan_id=str(uuid4()),
                community_server_id=str(uuid4()),
                batch_number=1,
                messages_redis_key="test:messages:key",
                scan_types_json=scan_types_json,
            )

        mock_sim.assert_called_once()
        mock_fp.assert_called_once()
        assert result["flagged_count"] == 2

    def test_signals_orchestrator_with_result(self) -> None:
        """Batch workflow sends batch_complete signal to orchestrator."""
        from src.dbos_workflows.content_scan_workflow import process_content_scan_batch

        orchestrator_wf_id = "orchestrator-wf-123"

        with (
            patch("src.dbos_workflows.content_scan_workflow.preprocess_batch_step") as mock_pre,
            patch("src.dbos_workflows.content_scan_workflow.similarity_scan_step"),
            patch("src.dbos_workflows.content_scan_workflow.relevance_filter_step") as mock_filter,
            patch("src.dbos_workflows.content_scan_workflow.DBOS") as mock_dbos,
            patch("src.dbos_workflows.content_scan_workflow.TokenGate"),
        ):
            mock_pre.return_value = {
                "filtered_messages_key": "k",
                "context_maps_key": "k",
                "message_count": 5,
                "skipped_count": 1,
            }
            mock_filter.return_value = {"flagged_count": 2, "errors": 0}

            process_content_scan_batch.__wrapped__(
                orchestrator_workflow_id=orchestrator_wf_id,
                scan_id=str(uuid4()),
                community_server_id=str(uuid4()),
                batch_number=1,
                messages_redis_key="test:messages:key",
                scan_types_json=json.dumps(["similarity"]),
            )

        signal_data = mock_dbos.send.call_args.args[1]
        assert signal_data["processed"] == 5
        assert signal_data["skipped"] == 1
        assert signal_data["flagged_count"] == 2

    def test_short_circuits_when_all_messages_skipped(self) -> None:
        """When preprocess returns message_count=0, skip scan steps entirely."""
        from src.dbos_workflows.content_scan_workflow import process_content_scan_batch

        with (
            patch("src.dbos_workflows.content_scan_workflow.preprocess_batch_step") as mock_pre,
            patch("src.dbos_workflows.content_scan_workflow.similarity_scan_step") as mock_sim,
            patch("src.dbos_workflows.content_scan_workflow.flashpoint_scan_step") as mock_fp,
            patch("src.dbos_workflows.content_scan_workflow.relevance_filter_step") as mock_filter,
            patch("src.dbos_workflows.content_scan_workflow.DBOS"),
        ):
            mock_pre.return_value = {
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

        mock_sim.assert_not_called()
        mock_fp.assert_not_called()
        mock_filter.assert_not_called()
        assert result["processed"] == 0
        assert result["skipped"] == 5

    def test_sends_signal_on_preprocess_error(self) -> None:
        """Batch workflow sends signal to orchestrator even when preprocess fails."""
        from src.dbos_workflows.content_scan_workflow import process_content_scan_batch

        with (
            patch("src.dbos_workflows.content_scan_workflow.preprocess_batch_step") as mock_pre,
            patch("src.dbos_workflows.content_scan_workflow.DBOS") as mock_dbos,
            patch("src.dbos_workflows.content_scan_workflow.TokenGate"),
        ):
            mock_pre.side_effect = RuntimeError("Step failed")

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
        mock_dbos.send.assert_called_once()


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
                messages_redis_key="test:messages:key",
                scan_types=["similarity"],
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
                messages_redis_key="test:messages:key",
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
                messages_redis_key="test:messages:key",
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

        with (
            patch("src.dbos_workflows.content_scan_workflow.preprocess_batch_step") as mock_pre,
            patch("src.dbos_workflows.content_scan_workflow.similarity_scan_step"),
            patch("src.dbos_workflows.content_scan_workflow.relevance_filter_step") as mock_filter,
            patch("src.dbos_workflows.content_scan_workflow.DBOS") as mock_dbos,
            patch("src.dbos_workflows.content_scan_workflow.TokenGate"),
        ):
            mock_pre.return_value = {
                "filtered_messages_key": "k",
                "context_maps_key": "k",
                "message_count": 10,
                "skipped_count": 1,
            }
            mock_filter.return_value = {"flagged_count": 2, "errors": 0}

            process_content_scan_batch.__wrapped__(
                orchestrator_workflow_id="orch-wf-id",
                scan_id=str(uuid4()),
                community_server_id=str(uuid4()),
                batch_number=3,
                messages_redis_key="test:messages:key",
                scan_types_json='["similarity"]',
            )

        call_args = mock_dbos.send.call_args
        assert call_args.args[0] == "orch-wf-id"
        assert call_args.kwargs["topic"] == "batch_complete"

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

        with (
            patch("src.dbos_workflows.content_scan_workflow.preprocess_batch_step") as mock_pre,
            patch("src.dbos_workflows.content_scan_workflow.similarity_scan_step"),
            patch("src.dbos_workflows.content_scan_workflow.relevance_filter_step") as mock_filter,
            patch("src.dbos_workflows.content_scan_workflow.DBOS") as mock_dbos,
            patch("src.dbos_workflows.content_scan_workflow.TokenGate"),
        ):
            mock_pre.return_value = {
                "filtered_messages_key": "k",
                "context_maps_key": "k",
                "message_count": 7,
                "skipped_count": 1,
            }
            mock_filter.return_value = {"flagged_count": 3, "errors": 2}

            process_content_scan_batch.__wrapped__(
                orchestrator_workflow_id="orch-wf-id",
                scan_id=str(uuid4()),
                community_server_id=str(uuid4()),
                batch_number=4,
                messages_redis_key="test:messages:key",
                scan_types_json='["similarity"]',
            )

        signal_data = mock_dbos.send.call_args.args[1]
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

        with patch("src.dbos_workflows.config.get_dbos_client") as mock_get_client:
            mock_client = MagicMock()
            mock_handle = MagicMock()
            mock_handle.workflow_id = "batch-wf-789"
            mock_client.enqueue.return_value = mock_handle
            mock_get_client.return_value = mock_client

            result = await enqueue_content_scan_batch(
                orchestrator_workflow_id="orchestrator-wf-123",
                scan_id=scan_id,
                community_server_id=community_server_id,
                batch_number=1,
                messages_redis_key=redis_key,
                scan_types=["similarity"],
            )

        assert result == "batch-wf-789"
        enqueue_args = mock_client.enqueue.call_args.args
        assert enqueue_args[4] == 1
        assert enqueue_args[5] == redis_key

    @pytest.mark.asyncio
    async def test_messages_redis_key_is_required(self) -> None:
        from src.dbos_workflows.content_scan_workflow import enqueue_content_scan_batch

        with patch("src.dbos_workflows.config.get_dbos_client") as mock_get_client:
            mock_client = MagicMock()
            mock_handle = MagicMock()
            mock_handle.workflow_id = "batch-wf-required"
            mock_client.enqueue.return_value = mock_handle
            mock_get_client.return_value = mock_client

            result = await enqueue_content_scan_batch(
                orchestrator_workflow_id="orch",
                scan_id=uuid4(),
                community_server_id=uuid4(),
                batch_number=1,
                messages_redis_key="test:required:key",
                scan_types=["similarity"],
            )

        assert result == "batch-wf-required"
        enqueue_args = mock_client.enqueue.call_args.args
        assert enqueue_args[5] == "test:required:key"


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
        mock_service_instance.increment_skipped_count.assert_awaited_once()
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
        The successful filter resets errors to 0 (per source code behavior).
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
        assert result["errors"] == 0
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
