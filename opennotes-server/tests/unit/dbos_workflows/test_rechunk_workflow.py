"""Tests for DBOS rechunk workflow.

Tests the rechunk workflow components including queue configuration,
process_fact_check_item step, and the main workflow function.

Note: Tests mock the synchronous helper functions that wrap async operations
since DBOS steps/workflows are synchronous. The actual DBOS decorators
add checkpointing and retry behavior.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from src.dbos_workflows.circuit_breaker import CircuitOpenError


class TestRechunkQueueConfiguration:
    """Tests for DBOS Queue configuration."""

    def test_queue_exists(self) -> None:
        """Rechunk queue is defined with correct name."""
        from src.dbos_workflows.rechunk_workflow import rechunk_queue

        assert rechunk_queue.name == "rechunk"

    def test_queue_worker_concurrency(self) -> None:
        """Worker concurrency is set for memory safety."""
        from src.dbos_workflows.rechunk_workflow import rechunk_queue

        assert rechunk_queue.worker_concurrency == 2

    def test_queue_global_concurrency(self) -> None:
        """Global concurrency matches SC-008 requirement (5-10 concurrent jobs)."""
        from src.dbos_workflows.rechunk_workflow import rechunk_queue

        assert rechunk_queue.concurrency == 10


class TestEmbeddingRetryConfig:
    """Tests for retry configuration constants."""

    def test_retry_config_values(self) -> None:
        """Retry config has correct values for exponential backoff."""
        from src.dbos_workflows.rechunk_workflow import EMBEDDING_RETRY_CONFIG

        assert EMBEDDING_RETRY_CONFIG["retries_allowed"] is True
        assert EMBEDDING_RETRY_CONFIG["max_attempts"] == 5
        assert EMBEDDING_RETRY_CONFIG["interval_seconds"] == 1.0
        assert EMBEDDING_RETRY_CONFIG["backoff_rate"] == 2.0


class TestProcessFactCheckItem:
    """Tests for process_fact_check_item step logic."""

    def test_returns_success_on_successful_processing(self) -> None:
        """Returns success result when processing succeeds."""
        from src.dbos_workflows.rechunk_workflow import process_fact_check_item

        item_id = str(uuid4())
        community_server_id = str(uuid4())

        with patch(
            "src.dbos_workflows.rechunk_workflow.chunk_and_embed_fact_check_sync"
        ) as mock_chunk:
            mock_chunk.return_value = {"chunks_created": 5}

            result = process_fact_check_item.__wrapped__(  # type: ignore[attr-defined]
                item_id=item_id,
                community_server_id=community_server_id,
            )

        assert result["success"] is True
        assert result["item_id"] == item_id
        assert result["chunks_created"] == 5

    def test_raises_on_processing_failure(self) -> None:
        """Raises exception to trigger DBOS retry."""
        from src.dbos_workflows.rechunk_workflow import process_fact_check_item

        item_id = str(uuid4())

        with patch(
            "src.dbos_workflows.rechunk_workflow.chunk_and_embed_fact_check_sync"
        ) as mock_chunk:
            mock_chunk.side_effect = RuntimeError("Embedding service unavailable")

            with pytest.raises(RuntimeError, match="Embedding service unavailable"):
                process_fact_check_item.__wrapped__(  # type: ignore[attr-defined]
                    item_id=item_id,
                    community_server_id=None,
                )


class TestChunkAndEmbedSyncWrapper:
    """Tests for the synchronous wrapper around async chunking logic."""

    def test_wrapper_uses_run_sync(self) -> None:
        """Sync wrapper uses run_sync to execute async code safely."""
        from src.dbos_workflows.rechunk_workflow import chunk_and_embed_fact_check_sync

        fact_check_id = uuid4()
        community_server_id = uuid4()

        with patch("src.dbos_workflows.rechunk_workflow.run_sync") as mock_run_sync:
            mock_run_sync.return_value = {"chunks_created": 3}

            result = chunk_and_embed_fact_check_sync(
                fact_check_id=fact_check_id,
                community_server_id=community_server_id,
            )

            assert result["chunks_created"] == 3
            mock_run_sync.assert_called_once()


class TestRechunkWorkflow:
    """Tests for rechunk_fact_check_workflow logic."""

    def test_workflow_processes_all_items(self) -> None:
        """Workflow processes each item via process_fact_check_item."""
        from src.dbos_workflows.rechunk_workflow import rechunk_fact_check_workflow

        batch_job_id = str(uuid4())
        item_ids = [str(uuid4()) for _ in range(3)]

        with (
            patch("src.dbos_workflows.rechunk_workflow.process_fact_check_item") as mock_process,
            patch(
                "src.dbos_workflows.rechunk_workflow.update_batch_job_progress_sync"
            ) as mock_progress,
            patch("src.dbos_workflows.rechunk_workflow.finalize_batch_job_sync") as mock_finalize,
            patch("src.dbos_workflows.rechunk_workflow.DBOS") as mock_dbos,
        ):
            mock_dbos.workflow_id = "test-workflow-id"
            mock_process.return_value = {"success": True, "chunks_created": 2}
            mock_progress.return_value = True
            mock_finalize.return_value = True

            result = rechunk_fact_check_workflow.__wrapped__(  # type: ignore[attr-defined]
                batch_job_id=batch_job_id,
                community_server_id=None,
                item_ids=item_ids,
            )

            assert mock_process.call_count == 3
            assert result["completed_count"] == 3
            assert result["failed_count"] == 0

    def test_workflow_handles_item_failure(self) -> None:
        """Workflow tracks failed items and continues processing."""
        from src.dbos_workflows.rechunk_workflow import rechunk_fact_check_workflow

        batch_job_id = str(uuid4())
        item_ids = [str(uuid4()) for _ in range(3)]

        call_count = 0

        def mock_process_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RuntimeError("Failed")
            return {"success": True, "chunks_created": 1}

        with (
            patch("src.dbos_workflows.rechunk_workflow.process_fact_check_item") as mock_process,
            patch(
                "src.dbos_workflows.rechunk_workflow.update_batch_job_progress_sync"
            ) as mock_progress,
            patch("src.dbos_workflows.rechunk_workflow.finalize_batch_job_sync") as mock_finalize,
            patch("src.dbos_workflows.rechunk_workflow.DBOS") as mock_dbos,
        ):
            mock_dbos.workflow_id = "test-workflow-id"
            mock_process.side_effect = mock_process_side_effect
            mock_progress.return_value = True
            mock_finalize.return_value = True

            result = rechunk_fact_check_workflow.__wrapped__(  # type: ignore[attr-defined]
                batch_job_id=batch_job_id,
                community_server_id=None,
                item_ids=item_ids,
            )

            assert result["completed_count"] == 2
            assert result["failed_count"] == 1
            assert len(result["errors"]) == 1

    def test_workflow_stops_on_circuit_breaker_open(self) -> None:
        """Workflow raises CircuitOpenError when circuit breaker trips."""
        from src.dbos_workflows.rechunk_workflow import rechunk_fact_check_workflow

        batch_job_id = str(uuid4())
        item_ids = [str(uuid4()) for _ in range(10)]

        with (
            patch("src.dbos_workflows.rechunk_workflow.process_fact_check_item") as mock_process,
            patch(
                "src.dbos_workflows.rechunk_workflow.update_batch_job_progress_sync"
            ) as mock_progress,
            patch("src.dbos_workflows.rechunk_workflow.finalize_batch_job_sync"),
            patch("src.dbos_workflows.rechunk_workflow.DBOS") as mock_dbos,
        ):
            mock_dbos.workflow_id = "test-workflow-id"
            mock_process.side_effect = RuntimeError("Always fail")
            mock_progress.return_value = True

            with pytest.raises(CircuitOpenError):
                rechunk_fact_check_workflow.__wrapped__(  # type: ignore[attr-defined]
                    batch_job_id=batch_job_id,
                    community_server_id=None,
                    item_ids=item_ids,
                )

    def test_workflow_finalizes_batch_job_on_success(self) -> None:
        """Workflow calls finalize_batch_job_sync on successful completion."""
        from src.dbos_workflows.rechunk_workflow import rechunk_fact_check_workflow

        batch_job_id = str(uuid4())
        item_ids = [str(uuid4())]

        with (
            patch("src.dbos_workflows.rechunk_workflow.process_fact_check_item") as mock_process,
            patch(
                "src.dbos_workflows.rechunk_workflow.update_batch_job_progress_sync"
            ) as mock_progress,
            patch("src.dbos_workflows.rechunk_workflow.finalize_batch_job_sync") as mock_finalize,
            patch("src.dbos_workflows.rechunk_workflow.DBOS") as mock_dbos,
        ):
            mock_dbos.workflow_id = "test-workflow-id"
            mock_process.return_value = {"success": True, "chunks_created": 1}
            mock_progress.return_value = True
            mock_finalize.return_value = True

            rechunk_fact_check_workflow.__wrapped__(  # type: ignore[attr-defined]
                batch_job_id=batch_job_id,
                community_server_id=None,
                item_ids=item_ids,
            )

            mock_finalize.assert_called_once()
            call_kwargs = mock_finalize.call_args.kwargs
            assert call_kwargs["success"] is True

    def test_workflow_updates_progress_periodically(self) -> None:
        """Workflow updates progress every batch_size items."""
        from src.dbos_workflows.rechunk_workflow import rechunk_fact_check_workflow

        batch_job_id = str(uuid4())
        item_ids = [str(uuid4()) for _ in range(150)]

        with (
            patch("src.dbos_workflows.rechunk_workflow.process_fact_check_item") as mock_process,
            patch(
                "src.dbos_workflows.rechunk_workflow.update_batch_job_progress_sync"
            ) as mock_progress,
            patch("src.dbos_workflows.rechunk_workflow.finalize_batch_job_sync") as mock_finalize,
            patch("src.dbos_workflows.rechunk_workflow.DBOS") as mock_dbos,
        ):
            mock_dbos.workflow_id = "test-workflow-id"
            mock_process.return_value = {"success": True, "chunks_created": 1}
            mock_progress.return_value = True
            mock_finalize.return_value = True

            rechunk_fact_check_workflow.__wrapped__(  # type: ignore[attr-defined]
                batch_job_id=batch_job_id,
                community_server_id=None,
                item_ids=item_ids,
                batch_size=100,
            )

            progress_calls = mock_progress.call_count
            assert progress_calls == 2


class TestChunkSingleFactCheckWorkflow:
    """Tests for chunk_single_fact_check_workflow (task-1056.01)."""

    def test_returns_success_on_successful_processing(self) -> None:
        """Returns success result when single item processing succeeds."""
        from src.dbos_workflows.rechunk_workflow import chunk_single_fact_check_workflow

        fact_check_id = str(uuid4())
        community_server_id = str(uuid4())

        with (
            patch("src.dbos_workflows.rechunk_workflow.process_fact_check_item") as mock_process,
            patch("src.dbos_workflows.rechunk_workflow.DBOS") as mock_dbos,
        ):
            mock_dbos.workflow_id = "test-workflow-id"
            mock_process.return_value = {
                "success": True,
                "item_id": fact_check_id,
                "chunks_created": 3,
            }

            result = chunk_single_fact_check_workflow.__wrapped__(  # type: ignore[attr-defined]
                fact_check_id=fact_check_id,
                community_server_id=community_server_id,
            )

        assert result["success"] is True
        assert result["item_id"] == fact_check_id
        assert result["chunks_created"] == 3
        mock_process.assert_called_once_with(
            item_id=fact_check_id,
            community_server_id=community_server_id,
        )

    def test_returns_failure_on_processing_error(self) -> None:
        """Returns failure result when processing raises exception."""
        from src.dbos_workflows.rechunk_workflow import chunk_single_fact_check_workflow

        fact_check_id = str(uuid4())

        with (
            patch("src.dbos_workflows.rechunk_workflow.process_fact_check_item") as mock_process,
            patch("src.dbos_workflows.rechunk_workflow.DBOS") as mock_dbos,
        ):
            mock_dbos.workflow_id = "test-workflow-id"
            mock_process.side_effect = RuntimeError("Embedding service unavailable")

            result = chunk_single_fact_check_workflow.__wrapped__(  # type: ignore[attr-defined]
                fact_check_id=fact_check_id,
                community_server_id=None,
            )

        assert result["success"] is False
        assert result["item_id"] == fact_check_id
        assert "Embedding service unavailable" in result["error"]

    def test_handles_null_community_server_id(self) -> None:
        """Handles null community_server_id correctly."""
        from src.dbos_workflows.rechunk_workflow import chunk_single_fact_check_workflow

        fact_check_id = str(uuid4())

        with (
            patch("src.dbos_workflows.rechunk_workflow.process_fact_check_item") as mock_process,
            patch("src.dbos_workflows.rechunk_workflow.DBOS") as mock_dbos,
        ):
            mock_dbos.workflow_id = "test-workflow-id"
            mock_process.return_value = {
                "success": True,
                "item_id": fact_check_id,
                "chunks_created": 1,
            }

            result = chunk_single_fact_check_workflow.__wrapped__(  # type: ignore[attr-defined]
                fact_check_id=fact_check_id,
                community_server_id=None,
            )

        assert result["success"] is True
        mock_process.assert_called_once_with(
            item_id=fact_check_id,
            community_server_id=None,
        )


class TestEnqueueSingleFactCheckChunkDBOS:
    """Tests for enqueue_single_fact_check_chunk DBOS function (task-1056.01).

    Updated for task-1058.04: Now uses DBOSClient.enqueue() instead of
    rechunk_queue.enqueue() for server-side enqueueing.
    """

    @pytest.mark.asyncio
    async def test_enqueues_via_dbos_client(self) -> None:
        """Enqueues single item workflow via DBOSClient.enqueue()."""
        from src.dbos_workflows.rechunk_workflow import enqueue_single_fact_check_chunk

        fact_check_id = uuid4()
        community_server_id = uuid4()

        with patch("src.dbos_workflows.rechunk_workflow.get_dbos_client") as mock_get_client:
            mock_client = MagicMock()
            mock_handle = MagicMock()
            mock_handle.workflow_id = "test-workflow-id"
            mock_client.enqueue.return_value = mock_handle
            mock_get_client.return_value = mock_client

            result = await enqueue_single_fact_check_chunk(
                fact_check_id=fact_check_id,
                community_server_id=community_server_id,
            )

        assert result == "test-workflow-id"
        mock_client.enqueue.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_none_on_enqueue_failure(self) -> None:
        """Returns None when client.enqueue fails."""
        from src.dbos_workflows.rechunk_workflow import enqueue_single_fact_check_chunk

        fact_check_id = uuid4()

        with patch("src.dbos_workflows.rechunk_workflow.get_dbos_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.enqueue.side_effect = RuntimeError("Queue unavailable")
            mock_get_client.return_value = mock_client

            result = await enqueue_single_fact_check_chunk(
                fact_check_id=fact_check_id,
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_handles_null_community_server_id(self) -> None:
        """Handles null community_server_id by passing None."""
        from src.dbos_workflows.rechunk_workflow import enqueue_single_fact_check_chunk

        fact_check_id = uuid4()

        with patch("src.dbos_workflows.rechunk_workflow.get_dbos_client") as mock_get_client:
            mock_client = MagicMock()
            mock_handle = MagicMock()
            mock_handle.workflow_id = "test-workflow-id"
            mock_client.enqueue.return_value = mock_handle
            mock_get_client.return_value = mock_client

            await enqueue_single_fact_check_chunk(
                fact_check_id=fact_check_id,
                community_server_id=None,
            )

        call_args = mock_client.enqueue.call_args
        assert call_args.args[2] is None

    @pytest.mark.asyncio
    async def test_uses_correct_enqueue_options(self) -> None:
        """Verifies EnqueueOptions has correct queue_name and workflow_name."""
        from src.dbos_workflows.rechunk_workflow import enqueue_single_fact_check_chunk

        fact_check_id = uuid4()

        with patch("src.dbos_workflows.rechunk_workflow.get_dbos_client") as mock_get_client:
            mock_client = MagicMock()
            mock_handle = MagicMock()
            mock_handle.workflow_id = "test-workflow-id"
            mock_client.enqueue.return_value = mock_handle
            mock_get_client.return_value = mock_client

            await enqueue_single_fact_check_chunk(
                fact_check_id=fact_check_id,
            )

        call_args = mock_client.enqueue.call_args
        options = call_args.args[0]
        assert options["queue_name"] == "rechunk"
        assert "chunk_single_fact_check_workflow" in options["workflow_name"]


class TestCircuitBreakerIntegration:
    """Tests for circuit breaker behavior in the workflow."""

    def test_circuit_trips_after_consecutive_failures(self) -> None:
        """Circuit breaker trips after 5 consecutive failures."""
        from src.dbos_workflows.rechunk_workflow import rechunk_fact_check_workflow

        batch_job_id = str(uuid4())
        item_ids = [str(uuid4()) for _ in range(10)]

        call_count = 0

        def fail_always(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise RuntimeError("Always fail")

        with (
            patch("src.dbos_workflows.rechunk_workflow.process_fact_check_item") as mock_process,
            patch(
                "src.dbos_workflows.rechunk_workflow.update_batch_job_progress_sync"
            ) as mock_progress,
            patch("src.dbos_workflows.rechunk_workflow.finalize_batch_job_sync"),
            patch("src.dbos_workflows.rechunk_workflow.DBOS") as mock_dbos,
        ):
            mock_dbos.workflow_id = "test-workflow-id"
            mock_process.side_effect = fail_always
            mock_progress.return_value = True

            with pytest.raises(CircuitOpenError):
                rechunk_fact_check_workflow.__wrapped__(  # type: ignore[attr-defined]
                    batch_job_id=batch_job_id,
                    community_server_id=None,
                    item_ids=item_ids,
                )

            assert call_count == 5

    def test_circuit_resets_after_success(self) -> None:
        """Circuit breaker resets failure count after success."""
        from src.dbos_workflows.rechunk_workflow import rechunk_fact_check_workflow

        batch_job_id = str(uuid4())
        item_ids = [str(uuid4()) for _ in range(10)]

        call_count = 0

        def intermittent_fail(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count % 3 == 0:
                return {"success": True, "chunks_created": 1}
            raise RuntimeError("Intermittent fail")

        with (
            patch("src.dbos_workflows.rechunk_workflow.process_fact_check_item") as mock_process,
            patch(
                "src.dbos_workflows.rechunk_workflow.update_batch_job_progress_sync"
            ) as mock_progress,
            patch("src.dbos_workflows.rechunk_workflow.finalize_batch_job_sync") as mock_finalize,
            patch("src.dbos_workflows.rechunk_workflow.DBOS") as mock_dbos,
        ):
            mock_dbos.workflow_id = "test-workflow-id"
            mock_process.side_effect = intermittent_fail
            mock_progress.return_value = True
            mock_finalize.return_value = True

            result = rechunk_fact_check_workflow.__wrapped__(  # type: ignore[attr-defined]
                batch_job_id=batch_job_id,
                community_server_id=None,
                item_ids=item_ids,
            )

            assert result["completed_count"] + result["failed_count"] == 10
