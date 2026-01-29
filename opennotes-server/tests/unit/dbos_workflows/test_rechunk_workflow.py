"""Tests for DBOS rechunk workflow.

Tests the rechunk workflow components including queue configuration,
process_fact_check_item step, and the main workflow function.

Note: Tests use the _impl functions directly to avoid DBOS initialization
requirements. The DBOS decorators are thin wrappers around these functions.
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


class TestProcessFactCheckItemImpl:
    """Tests for _process_fact_check_item_impl (core logic without DBOS)."""

    def test_returns_success_on_successful_processing(self) -> None:
        """Returns success result when processing succeeds."""
        from src.dbos_workflows.rechunk_workflow import _process_fact_check_item_impl

        item_id = str(uuid4())
        community_server_id = str(uuid4())

        with patch(
            "src.dbos_workflows.rechunk_workflow.chunk_and_embed_fact_check_sync"
        ) as mock_chunk:
            mock_chunk.return_value = {"chunks_created": 5}

            result = _process_fact_check_item_impl(
                item_id=item_id,
                community_server_id=community_server_id,
            )

        assert result["success"] is True
        assert result["item_id"] == item_id
        assert result["chunks_created"] == 5

    def test_raises_on_processing_failure(self) -> None:
        """Raises exception to trigger DBOS retry."""
        from src.dbos_workflows.rechunk_workflow import _process_fact_check_item_impl

        item_id = str(uuid4())

        with patch(
            "src.dbos_workflows.rechunk_workflow.chunk_and_embed_fact_check_sync"
        ) as mock_chunk:
            mock_chunk.side_effect = RuntimeError("Embedding service unavailable")

            with pytest.raises(RuntimeError, match="Embedding service unavailable"):
                _process_fact_check_item_impl(
                    item_id=item_id,
                    community_server_id=None,
                )


class TestChunkAndEmbedSyncWrapper:
    """Tests for the synchronous wrapper around async chunking logic."""

    def test_wrapper_calls_async_service(self) -> None:
        """Sync wrapper calls async service correctly."""
        from src.dbos_workflows.rechunk_workflow import chunk_and_embed_fact_check_sync

        fact_check_id = uuid4()
        community_server_id = uuid4()

        with patch(
            "src.dbos_workflows.rechunk_workflow._run_async_chunk_and_embed"
        ) as mock_async:
            mock_async.return_value = {"chunks_created": 3}

            result = chunk_and_embed_fact_check_sync(
                fact_check_id=fact_check_id,
                community_server_id=community_server_id,
            )

        assert result["chunks_created"] == 3
        mock_async.assert_called_once_with(fact_check_id, community_server_id)


class TestRechunkWorkflowImpl:
    """Tests for _rechunk_workflow_impl (core logic without DBOS)."""

    def test_workflow_updates_batch_job_status_on_start(self) -> None:
        """Workflow updates BatchJob to IN_PROGRESS at start."""
        from src.dbos_workflows.rechunk_workflow import _rechunk_workflow_impl

        batch_job_id = str(uuid4())
        item_ids = [str(uuid4())]

        mock_process = MagicMock(return_value={"success": True})

        with patch(
            "src.dbos_workflows.rechunk_workflow.get_batch_job_adapter"
        ) as mock_get_adapter:
            mock_adapter = MagicMock()
            mock_get_adapter.return_value = mock_adapter

            _rechunk_workflow_impl(
                batch_job_id=batch_job_id,
                community_server_id=None,
                item_ids=item_ids,
                process_item_func=mock_process,
            )

            mock_adapter.update_status_sync.assert_called()

    def test_workflow_processes_all_items(self) -> None:
        """Workflow processes each item via process_item_func."""
        from src.dbos_workflows.rechunk_workflow import _rechunk_workflow_impl

        batch_job_id = str(uuid4())
        item_ids = [str(uuid4()) for _ in range(3)]

        mock_process = MagicMock(return_value={"success": True})

        with patch(
            "src.dbos_workflows.rechunk_workflow.get_batch_job_adapter"
        ) as mock_get_adapter:
            mock_adapter = MagicMock()
            mock_get_adapter.return_value = mock_adapter

            result = _rechunk_workflow_impl(
                batch_job_id=batch_job_id,
                community_server_id=None,
                item_ids=item_ids,
                process_item_func=mock_process,
            )

            assert mock_process.call_count == 3
            assert result["completed_count"] == 3
            assert result["failed_count"] == 0

    def test_workflow_handles_item_failure(self) -> None:
        """Workflow tracks failed items and continues processing."""
        from src.dbos_workflows.rechunk_workflow import _rechunk_workflow_impl

        batch_job_id = str(uuid4())
        item_ids = [str(uuid4()) for _ in range(3)]

        mock_process = MagicMock(
            side_effect=[
                {"success": True},
                RuntimeError("Failed"),
                {"success": True},
            ]
        )

        with patch(
            "src.dbos_workflows.rechunk_workflow.get_batch_job_adapter"
        ) as mock_get_adapter:
            mock_adapter = MagicMock()
            mock_get_adapter.return_value = mock_adapter

            result = _rechunk_workflow_impl(
                batch_job_id=batch_job_id,
                community_server_id=None,
                item_ids=item_ids,
                process_item_func=mock_process,
            )

            assert result["completed_count"] == 2
            assert result["failed_count"] == 1
            assert len(result["errors"]) == 1

    def test_workflow_stops_on_circuit_breaker_open(self) -> None:
        """Workflow raises CircuitOpenError when circuit breaker trips."""
        from src.dbos_workflows.rechunk_workflow import _rechunk_workflow_impl

        batch_job_id = str(uuid4())
        item_ids = [str(uuid4()) for _ in range(10)]

        mock_process = MagicMock(side_effect=RuntimeError("Fail"))

        with patch(
            "src.dbos_workflows.rechunk_workflow.get_batch_job_adapter"
        ) as mock_get_adapter:
            mock_adapter = MagicMock()
            mock_get_adapter.return_value = mock_adapter

            with pytest.raises(CircuitOpenError):
                _rechunk_workflow_impl(
                    batch_job_id=batch_job_id,
                    community_server_id=None,
                    item_ids=item_ids,
                    process_item_func=mock_process,
                )

    def test_workflow_finalizes_batch_job_on_success(self) -> None:
        """Workflow calls finalize_job on successful completion."""
        from src.dbos_workflows.rechunk_workflow import _rechunk_workflow_impl

        batch_job_id = str(uuid4())
        item_ids = [str(uuid4())]

        mock_process = MagicMock(return_value={"success": True})

        with patch(
            "src.dbos_workflows.rechunk_workflow.get_batch_job_adapter"
        ) as mock_get_adapter:
            mock_adapter = MagicMock()
            mock_get_adapter.return_value = mock_adapter

            _rechunk_workflow_impl(
                batch_job_id=batch_job_id,
                community_server_id=None,
                item_ids=item_ids,
                process_item_func=mock_process,
            )

            mock_adapter.finalize_job.assert_called_once()
            call_args = mock_adapter.finalize_job.call_args
            assert call_args.kwargs["success"] is True

    def test_workflow_updates_progress_periodically(self) -> None:
        """Workflow updates progress every batch_size items."""
        from src.dbos_workflows.rechunk_workflow import _rechunk_workflow_impl

        batch_job_id = str(uuid4())
        item_ids = [str(uuid4()) for _ in range(150)]

        mock_process = MagicMock(return_value={"success": True})

        with patch(
            "src.dbos_workflows.rechunk_workflow.get_batch_job_adapter"
        ) as mock_get_adapter:
            mock_adapter = MagicMock()
            mock_get_adapter.return_value = mock_adapter

            _rechunk_workflow_impl(
                batch_job_id=batch_job_id,
                community_server_id=None,
                item_ids=item_ids,
                batch_size=100,
                process_item_func=mock_process,
            )

            progress_calls = mock_adapter.update_progress_sync.call_count
            assert progress_calls == 2


class TestCircuitBreakerIntegration:
    """Tests for circuit breaker behavior in the workflow."""

    def test_circuit_trips_after_consecutive_failures(self) -> None:
        """Circuit breaker trips after 5 consecutive failures."""
        from src.dbos_workflows.rechunk_workflow import _rechunk_workflow_impl

        batch_job_id = str(uuid4())
        item_ids = [str(uuid4()) for _ in range(10)]

        call_count = 0

        def fail_always(**kwargs: object) -> dict[str, bool]:
            nonlocal call_count
            call_count += 1
            raise RuntimeError("Always fail")

        with patch(
            "src.dbos_workflows.rechunk_workflow.get_batch_job_adapter"
        ) as mock_get_adapter:
            mock_adapter = MagicMock()
            mock_get_adapter.return_value = mock_adapter

            with pytest.raises(CircuitOpenError):
                _rechunk_workflow_impl(
                    batch_job_id=batch_job_id,
                    community_server_id=None,
                    item_ids=item_ids,
                    process_item_func=fail_always,
                )

            assert call_count == 5

    def test_circuit_resets_after_success(self) -> None:
        """Circuit breaker resets failure count after success."""
        from src.dbos_workflows.rechunk_workflow import _rechunk_workflow_impl

        batch_job_id = str(uuid4())
        item_ids = [str(uuid4()) for _ in range(10)]

        call_count = 0

        def intermittent_fail(**kwargs: object) -> dict[str, bool]:
            nonlocal call_count
            call_count += 1
            if call_count % 3 == 0:
                return {"success": True}
            raise RuntimeError("Intermittent fail")

        with patch(
            "src.dbos_workflows.rechunk_workflow.get_batch_job_adapter"
        ) as mock_get_adapter:
            mock_adapter = MagicMock()
            mock_get_adapter.return_value = mock_adapter

            result = _rechunk_workflow_impl(
                batch_job_id=batch_job_id,
                community_server_id=None,
                item_ids=item_ids,
                process_item_func=intermittent_fail,
            )

            assert result["completed_count"] + result["failed_count"] == 10
