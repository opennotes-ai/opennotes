"""Integration tests for DBOS infrastructure with mocked DBOS classes.

Tests cover:
- AC #5: DBOS worker mode startup and graceful shutdown lifecycle
- AC #6: Rechunk DBOS workflow end-to-end (single-item chunking)
- AC #7: DBOS queue enqueueing via DBOSClient

These are unit tests with mocked DBOS infrastructure, verifying the
calling patterns and lifecycle management without requiring a real
DBOS server.

Note: Tests for _init_dbos/_destroy_dbos (src.main) exist in
test_worker_registration.py. Those tests have a pre-existing torch
import failure in this worktree. The tests here exercise the same
lifecycle through the underlying config module functions.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

pytestmark = pytest.mark.unit


class TestDbosWorkerLifecycle:
    """AC #5: DBOS worker mode startup and graceful shutdown.

    Tests the full create -> get -> launch -> validate -> destroy lifecycle
    through the config module functions that _init_dbos and _destroy_dbos call.
    """

    def test_worker_lifecycle_create_launch_destroy(self) -> None:
        """Full worker lifecycle: create instance, launch, then destroy."""
        with patch("src.dbos_workflows.config.DBOS") as mock_dbos_class:
            from src.dbos_workflows.config import (
                destroy_dbos,
                get_dbos,
                reset_dbos,
            )

            mock_instance = MagicMock()
            mock_dbos_class.return_value = mock_instance

            reset_dbos()

            instance = get_dbos()
            assert instance is mock_instance
            mock_dbos_class.assert_called_once()

            instance.launch()
            instance.launch.assert_called_once()

            destroy_dbos(workflow_completion_timeout_sec=5)
            mock_dbos_class.destroy.assert_called_once_with(
                workflow_completion_timeout_sec=5,
                destroy_registry=False,
            )

    def test_worker_lifecycle_second_get_returns_same_instance(self) -> None:
        """get_dbos() returns the same instance (singleton) on repeated calls."""
        with patch("src.dbos_workflows.config.DBOS") as mock_dbos_class:
            from src.dbos_workflows.config import get_dbos, reset_dbos

            mock_instance = MagicMock()
            mock_dbos_class.return_value = mock_instance

            reset_dbos()
            first = get_dbos()
            second = get_dbos()

            assert first is second
            assert mock_dbos_class.call_count == 1

    def test_worker_lifecycle_destroy_allows_recreation(self) -> None:
        """After destroy_dbos, get_dbos creates a fresh instance."""
        with patch("src.dbos_workflows.config.DBOS") as mock_dbos_class:
            from src.dbos_workflows.config import destroy_dbos, get_dbos, reset_dbos

            mock_instance_1 = MagicMock()
            mock_instance_2 = MagicMock()
            mock_dbos_class.side_effect = [mock_instance_1, mock_instance_2]

            reset_dbos()
            first = get_dbos()
            destroy_dbos()
            second = get_dbos()

            assert first is not second
            assert first is mock_instance_1
            assert second is mock_instance_2

    def test_worker_lifecycle_destroy_is_noop_when_not_created(self) -> None:
        """destroy_dbos() is safe to call when no instance exists."""
        with patch("src.dbos_workflows.config.DBOS") as mock_dbos_class:
            from src.dbos_workflows.config import destroy_dbos, reset_dbos

            reset_dbos()
            destroy_dbos()

            mock_dbos_class.destroy.assert_not_called()

    def test_server_mode_lifecycle_client_create_destroy(self) -> None:
        """Server mode lifecycle: create client, use, then destroy."""
        with (
            patch("src.dbos_workflows.config.DBOSClient") as mock_client_class,
            patch("src.dbos_workflows.config.settings") as mock_settings,
        ):
            from src.dbos_workflows.config import (
                destroy_dbos_client,
                get_dbos_client,
                reset_dbos_client,
            )

            mock_settings.DATABASE_URL = "postgresql+asyncpg://u:p@host/db"
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            reset_dbos_client()

            client = get_dbos_client()
            assert client is mock_client

            destroy_dbos_client()
            mock_client.destroy.assert_called_once()

    def test_server_mode_lifecycle_client_recreatable_after_destroy(self) -> None:
        """After destroy_dbos_client, get_dbos_client creates a new client."""
        with (
            patch("src.dbos_workflows.config.DBOSClient") as mock_client_class,
            patch("src.dbos_workflows.config.settings") as mock_settings,
        ):
            from src.dbos_workflows.config import (
                destroy_dbos_client,
                get_dbos_client,
                reset_dbos_client,
            )

            mock_settings.DATABASE_URL = "postgresql+asyncpg://u:p@host/db"
            mock_client_1 = MagicMock()
            mock_client_2 = MagicMock()
            mock_client_class.side_effect = [mock_client_1, mock_client_2]

            reset_dbos_client()
            first = get_dbos_client()
            destroy_dbos_client()
            second = get_dbos_client()

            assert first is not second
            assert mock_client_class.call_count == 2

    def test_validate_dbos_connection_success(self) -> None:
        """validate_dbos_connection returns True when schema exists."""
        with (
            patch("src.dbos_workflows.config.get_dbos_config") as mock_config,
            patch("psycopg.connect") as mock_connect,
        ):
            mock_config.return_value = {"system_database_url": "postgresql://u:p@host/db"}
            mock_cursor = MagicMock()
            mock_cursor.fetchone.return_value = (True,)
            mock_conn = MagicMock()
            mock_conn.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn.__exit__ = MagicMock(return_value=False)
            mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
            mock_connect.return_value = mock_conn

            from src.dbos_workflows.config import validate_dbos_connection

            result = validate_dbos_connection()
            assert result is True

    def test_validate_dbos_connection_raises_on_missing_schema(self) -> None:
        """validate_dbos_connection raises when DBOS schema is missing."""
        with (
            patch("src.dbos_workflows.config.get_dbos_config") as mock_config,
            patch("psycopg.connect") as mock_connect,
        ):
            mock_config.return_value = {"system_database_url": "postgresql://u:p@host/db"}
            mock_cursor = MagicMock()
            mock_cursor.fetchone.return_value = (False,)
            mock_conn = MagicMock()
            mock_conn.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn.__exit__ = MagicMock(return_value=False)
            mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
            mock_connect.return_value = mock_conn

            from src.dbos_workflows.config import validate_dbos_connection

            with pytest.raises(RuntimeError, match="DBOS system tables not found"):
                validate_dbos_connection()

    def test_conductor_key_passed_to_config_when_set(self) -> None:
        """create_dbos_instance includes conductor_key in config when configured."""
        with (
            patch("src.dbos_workflows.config.DBOS") as mock_dbos_class,
            patch("src.dbos_workflows.config.get_dbos_config") as mock_get_config,
            patch("src.dbos_workflows.config.settings") as mock_settings,
        ):
            mock_config: dict[str, Any] = {
                "name": "test-app",
                "system_database_url": "postgresql://host/db",
            }
            mock_get_config.return_value = mock_config
            mock_settings.DBOS_CONDUCTOR_KEY = "conductor-key-abc"

            from src.dbos_workflows.config import create_dbos_instance

            create_dbos_instance()

            assert mock_config["conductor_key"] == "conductor-key-abc"
            mock_dbos_class.assert_called_once_with(config=mock_config)

    def test_concurrent_get_dbos_returns_same_instance(self) -> None:
        """Thread-safe: concurrent get_dbos() calls return the same instance."""
        import threading

        with patch("src.dbos_workflows.config.DBOS") as mock_dbos_class:
            from src.dbos_workflows.config import get_dbos, reset_dbos

            mock_instance = MagicMock()
            mock_dbos_class.return_value = mock_instance

            reset_dbos()
            results: list[Any] = []

            def call_get() -> None:
                results.append(get_dbos())

            threads = [threading.Thread(target=call_get) for _ in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            assert len(results) == 10
            assert all(r is mock_instance for r in results)
            assert mock_dbos_class.call_count == 1


class TestRechunkWorkflowEndToEnd:
    """AC #6: Rechunk DBOS workflow end-to-end (single-item chunking).

    Verifies the complete flow from chunk_single_fact_check_workflow
    through process_fact_check_item step to chunk_and_embed_fact_check_sync.
    """

    def test_single_item_workflow_calls_step_and_returns_result(self) -> None:
        """chunk_single_fact_check_workflow delegates to process_fact_check_item."""
        from src.dbos_workflows.rechunk_workflow import chunk_single_fact_check_workflow

        fact_check_id = str(uuid4())
        community_server_id = str(uuid4())

        with (
            patch("src.dbos_workflows.rechunk_workflow.process_fact_check_item") as mock_step,
            patch("src.dbos_workflows.rechunk_workflow.DBOS") as mock_dbos,
        ):
            mock_dbos.workflow_id = "wf-e2e-test"
            mock_step.return_value = {
                "success": True,
                "item_id": fact_check_id,
                "chunks_created": 4,
            }

            result = chunk_single_fact_check_workflow.__wrapped__(  # type: ignore[attr-defined]
                fact_check_id=fact_check_id,
                community_server_id=community_server_id,
            )

        assert result["success"] is True
        assert result["chunks_created"] == 4
        mock_step.assert_called_once_with(
            item_id=fact_check_id,
            community_server_id=community_server_id,
        )

    def test_single_item_step_invokes_sync_wrapper(self) -> None:
        """process_fact_check_item calls chunk_and_embed_fact_check_sync."""
        from src.dbos_workflows.rechunk_workflow import process_fact_check_item

        item_id = str(uuid4())
        community_server_id = str(uuid4())

        with patch(
            "src.dbos_workflows.rechunk_workflow.chunk_and_embed_fact_check_sync"
        ) as mock_sync:
            mock_sync.return_value = {"chunks_created": 3}

            result = process_fact_check_item.__wrapped__(  # type: ignore[attr-defined]
                item_id=item_id,
                community_server_id=community_server_id,
            )

        assert result["success"] is True
        assert result["chunks_created"] == 3
        mock_sync.assert_called_once()

    def test_end_to_end_single_item_chunking_pipeline(self) -> None:
        """Full pipeline: workflow -> step -> sync wrapper -> services.

        Mocks at the lowest level (run_sync and chunking_service) to verify
        the complete call chain without touching real DB or LLM services.
        """
        from src.dbos_workflows.rechunk_workflow import chunk_single_fact_check_workflow

        fact_check_id = str(uuid4())
        community_server_id = str(uuid4())

        mock_service = MagicMock()
        mock_chunking = MagicMock()
        mock_chunking.chunk_text.return_value = ["chunk-A", "chunk-B", "chunk-C"]

        @contextmanager
        def mock_use_chunking_sync():
            yield mock_chunking

        with (
            patch("src.dbos_workflows.rechunk_workflow.DBOS") as mock_dbos,
            patch("src.dbos_workflows.rechunk_workflow.run_sync") as mock_run_sync,
            patch(
                "src.dbos_workflows.rechunk_workflow.get_chunk_embedding_service",
                return_value=mock_service,
            ),
            patch(
                "src.dbos_workflows.rechunk_workflow.use_chunking_service_sync",
                side_effect=mock_use_chunking_sync,
            ),
        ):
            mock_dbos.workflow_id = "wf-e2e-pipeline"
            mock_run_sync.side_effect = [
                "Some fact-check content to chunk",
                {"chunks_created": 3},
            ]

            result = chunk_single_fact_check_workflow.__wrapped__(  # type: ignore[attr-defined]
                fact_check_id=fact_check_id,
                community_server_id=community_server_id,
            )

        assert result["success"] is True
        assert result["chunks_created"] == 3
        assert mock_run_sync.call_count == 2
        mock_chunking.chunk_text.assert_called_once_with("Some fact-check content to chunk")

    def test_single_item_workflow_catches_step_exception(self) -> None:
        """Workflow returns failure dict when step raises (does not propagate)."""
        from src.dbos_workflows.rechunk_workflow import chunk_single_fact_check_workflow

        fact_check_id = str(uuid4())

        with (
            patch("src.dbos_workflows.rechunk_workflow.process_fact_check_item") as mock_step,
            patch("src.dbos_workflows.rechunk_workflow.DBOS") as mock_dbos,
        ):
            mock_dbos.workflow_id = "wf-e2e-fail"
            mock_step.side_effect = RuntimeError("Embedding API rate limited")

            result = chunk_single_fact_check_workflow.__wrapped__(  # type: ignore[attr-defined]
                fact_check_id=fact_check_id,
                community_server_id=None,
            )

        assert result["success"] is False
        assert "Embedding API rate limited" in result["error"]

    def test_single_item_workflow_with_none_community_server(self) -> None:
        """Workflow handles None community_server_id through the pipeline."""
        from src.dbos_workflows.rechunk_workflow import chunk_single_fact_check_workflow

        fact_check_id = str(uuid4())

        with (
            patch("src.dbos_workflows.rechunk_workflow.process_fact_check_item") as mock_step,
            patch("src.dbos_workflows.rechunk_workflow.DBOS") as mock_dbos,
        ):
            mock_dbos.workflow_id = "wf-null-community"
            mock_step.return_value = {
                "success": True,
                "item_id": fact_check_id,
                "chunks_created": 1,
            }

            result = chunk_single_fact_check_workflow.__wrapped__(  # type: ignore[attr-defined]
                fact_check_id=fact_check_id,
                community_server_id=None,
            )

        assert result["success"] is True
        mock_step.assert_called_once_with(
            item_id=fact_check_id,
            community_server_id=None,
        )

    def test_batch_workflow_processes_all_items_and_finalizes(self) -> None:
        """rechunk_fact_check_workflow processes items and calls finalize."""
        from src.dbos_workflows.rechunk_workflow import rechunk_fact_check_workflow

        batch_job_id = str(uuid4())
        item_ids = [str(uuid4()) for _ in range(5)]

        with (
            patch("src.dbos_workflows.rechunk_workflow.process_fact_check_item") as mock_process,
            patch(
                "src.dbos_workflows.rechunk_workflow.update_batch_job_progress_sync"
            ) as mock_progress,
            patch("src.dbos_workflows.rechunk_workflow.finalize_batch_job_sync") as mock_finalize,
            patch("src.dbos_workflows.rechunk_workflow.DBOS") as mock_dbos,
        ):
            mock_dbos.workflow_id = "wf-batch-e2e"
            mock_process.return_value = {"success": True, "chunks_created": 2}
            mock_progress.return_value = True
            mock_finalize.return_value = True

            result = rechunk_fact_check_workflow.__wrapped__(  # type: ignore[attr-defined]
                batch_job_id=batch_job_id,
                community_server_id=None,
                item_ids=item_ids,
                batch_size=100,
            )

        assert result["completed_count"] == 5
        assert result["failed_count"] == 0
        assert result["errors"] == []
        assert mock_process.call_count == 5
        mock_finalize.assert_called_once()
        call_kwargs = mock_finalize.call_args.kwargs
        assert call_kwargs["success"] is True

    def test_step_raises_to_trigger_dbos_retry(self) -> None:
        """process_fact_check_item raises on failure for DBOS retry."""
        from src.dbos_workflows.rechunk_workflow import process_fact_check_item

        with patch(
            "src.dbos_workflows.rechunk_workflow.chunk_and_embed_fact_check_sync"
        ) as mock_sync:
            mock_sync.side_effect = RuntimeError("LLM timeout")

            with pytest.raises(RuntimeError, match="LLM timeout"):
                process_fact_check_item.__wrapped__(  # type: ignore[attr-defined]
                    item_id=str(uuid4()),
                    community_server_id=None,
                )


class TestDbosQueueEnqueueing:
    """AC #7: DBOS queue enqueueing via DBOSClient.

    Verifies the enqueueing flow through DBOSClient for both single-item
    and batch workflows, including error handling.
    """

    @pytest.mark.asyncio
    async def test_enqueue_single_fact_check_returns_workflow_id(self) -> None:
        """enqueue_single_fact_check_chunk returns workflow_id on success."""
        from src.dbos_workflows.rechunk_workflow import enqueue_single_fact_check_chunk

        fact_check_id = uuid4()
        community_server_id = uuid4()

        with patch("src.dbos_workflows.rechunk_workflow.get_dbos_client") as mock_get_client:
            mock_client = MagicMock()
            mock_handle = MagicMock()
            mock_handle.workflow_id = "wf-enqueue-test"
            mock_client.enqueue.return_value = mock_handle
            mock_get_client.return_value = mock_client

            result = await enqueue_single_fact_check_chunk(
                fact_check_id=fact_check_id,
                community_server_id=community_server_id,
            )

        assert result == "wf-enqueue-test"

    @pytest.mark.asyncio
    async def test_enqueue_passes_correct_options_and_args(self) -> None:
        """Verifies EnqueueOptions and positional args passed to client.enqueue."""
        from src.dbos_workflows.rechunk_workflow import (
            CHUNK_SINGLE_FACT_CHECK_WORKFLOW_NAME,
            enqueue_single_fact_check_chunk,
        )

        fact_check_id = uuid4()
        community_server_id = uuid4()

        with patch("src.dbos_workflows.rechunk_workflow.get_dbos_client") as mock_get_client:
            mock_client = MagicMock()
            mock_handle = MagicMock()
            mock_handle.workflow_id = "wf-args-test"
            mock_client.enqueue.return_value = mock_handle
            mock_get_client.return_value = mock_client

            await enqueue_single_fact_check_chunk(
                fact_check_id=fact_check_id,
                community_server_id=community_server_id,
            )

        call_args = mock_client.enqueue.call_args
        options = call_args.args[0]
        assert options["queue_name"] == "rechunk"
        assert options["workflow_name"] == CHUNK_SINGLE_FACT_CHECK_WORKFLOW_NAME

        passed_fact_check_id = call_args.args[1]
        passed_community_id = call_args.args[2]
        assert passed_fact_check_id == str(fact_check_id)
        assert passed_community_id == str(community_server_id)

    @pytest.mark.asyncio
    async def test_enqueue_with_none_community_server_passes_none(self) -> None:
        """Passes None (not 'None' string) for community_server_id."""
        from src.dbos_workflows.rechunk_workflow import enqueue_single_fact_check_chunk

        fact_check_id = uuid4()

        with patch("src.dbos_workflows.rechunk_workflow.get_dbos_client") as mock_get_client:
            mock_client = MagicMock()
            mock_handle = MagicMock()
            mock_handle.workflow_id = "wf-none-test"
            mock_client.enqueue.return_value = mock_handle
            mock_get_client.return_value = mock_client

            await enqueue_single_fact_check_chunk(
                fact_check_id=fact_check_id,
                community_server_id=None,
            )

        call_args = mock_client.enqueue.call_args
        assert call_args.args[2] is None

    @pytest.mark.asyncio
    async def test_enqueue_returns_none_on_client_error(self) -> None:
        """Returns None when DBOSClient.enqueue() raises."""
        from src.dbos_workflows.rechunk_workflow import enqueue_single_fact_check_chunk

        with patch("src.dbos_workflows.rechunk_workflow.get_dbos_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.enqueue.side_effect = ConnectionError("DBOS database unavailable")
            mock_get_client.return_value = mock_client

            result = await enqueue_single_fact_check_chunk(
                fact_check_id=uuid4(),
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_enqueue_returns_none_on_client_creation_error(self) -> None:
        """Returns None when get_dbos_client() itself fails."""
        from src.dbos_workflows.rechunk_workflow import enqueue_single_fact_check_chunk

        with patch("src.dbos_workflows.rechunk_workflow.get_dbos_client") as mock_get_client:
            mock_get_client.side_effect = RuntimeError("Cannot connect to system DB")

            result = await enqueue_single_fact_check_chunk(
                fact_check_id=uuid4(),
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_batch_dispatch_enqueues_workflow_with_item_ids(self) -> None:
        """dispatch_dbos_rechunk_workflow enqueues via DBOSClient with item IDs."""
        from src.dbos_workflows.rechunk_workflow import dispatch_dbos_rechunk_workflow

        item_ids_raw = [uuid4() for _ in range(5)]

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [(item_id,) for item_id in item_ids_raw]
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        mock_job = MagicMock()
        mock_job.id = uuid4()
        mock_db.refresh = AsyncMock()

        with (
            patch("src.dbos_workflows.rechunk_workflow.BatchJobService") as mock_service_cls,
            patch("src.dbos_workflows.rechunk_workflow.get_dbos_client") as mock_get_client,
            patch(
                "src.dbos_workflows.rechunk_workflow.asyncio.to_thread",
                new_callable=AsyncMock,
            ) as mock_to_thread,
        ):
            mock_service = MagicMock()
            mock_service.create_job = AsyncMock(return_value=mock_job)
            mock_service.start_job = AsyncMock()
            mock_service.set_workflow_id = AsyncMock()
            mock_service_cls.return_value = mock_service

            mock_client = MagicMock()
            mock_handle = MagicMock()
            mock_handle.workflow_id = "wf-batch-test"
            mock_to_thread.return_value = mock_handle
            mock_get_client.return_value = mock_client

            result = await dispatch_dbos_rechunk_workflow(
                db=mock_db,
                community_server_id=None,
                batch_size=50,
            )

        assert result == mock_job.id
        mock_service.create_job.assert_called_once()
        mock_service.start_job.assert_called_once_with(mock_job.id)
        mock_service.set_workflow_id.assert_called_once_with(mock_job.id, "wf-batch-test")

        enqueue_call_args = mock_to_thread.call_args
        assert enqueue_call_args.args[0] == mock_client.enqueue

    @pytest.mark.asyncio
    async def test_batch_dispatch_raises_on_no_items(self) -> None:
        """dispatch_dbos_rechunk_workflow raises ValueError with no items."""
        from src.dbos_workflows.rechunk_workflow import dispatch_dbos_rechunk_workflow

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(ValueError, match="No fact-check items to process"):
            await dispatch_dbos_rechunk_workflow(db=mock_db)

    @pytest.mark.asyncio
    async def test_batch_dispatch_marks_job_failed_on_enqueue_error(self) -> None:
        """BatchJob is marked FAILED when enqueue raises."""
        from src.dbos_workflows.rechunk_workflow import dispatch_dbos_rechunk_workflow

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [(uuid4(),)]
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        mock_job = MagicMock()
        mock_job.id = uuid4()

        with (
            patch("src.dbos_workflows.rechunk_workflow.BatchJobService") as mock_service_cls,
            patch("src.dbos_workflows.rechunk_workflow.get_dbos_client") as mock_get_client,
            patch(
                "src.dbos_workflows.rechunk_workflow.asyncio.to_thread",
                new_callable=AsyncMock,
            ) as mock_to_thread,
        ):
            mock_service = MagicMock()
            mock_service.create_job = AsyncMock(return_value=mock_job)
            mock_service.start_job = AsyncMock()
            mock_service.fail_job = AsyncMock()
            mock_service_cls.return_value = mock_service

            mock_client = MagicMock()
            mock_get_client.return_value = mock_client
            mock_to_thread.side_effect = ConnectionError("NATS unavailable")

            with pytest.raises(ConnectionError):
                await dispatch_dbos_rechunk_workflow(db=mock_db)

        mock_service.fail_job.assert_called_once()
        fail_call = mock_service.fail_job.call_args
        assert fail_call.args[0] == mock_job.id

    @pytest.mark.asyncio
    async def test_enqueue_uses_asyncio_to_thread_for_blocking_call(self) -> None:
        """enqueue_single_fact_check_chunk wraps blocking client.enqueue in asyncio.to_thread."""
        from src.dbos_workflows.rechunk_workflow import enqueue_single_fact_check_chunk

        fact_check_id = uuid4()

        with (
            patch("src.dbos_workflows.rechunk_workflow.get_dbos_client") as mock_get_client,
            patch(
                "src.dbos_workflows.rechunk_workflow.asyncio.to_thread",
                new_callable=AsyncMock,
            ) as mock_to_thread,
        ):
            mock_client = MagicMock()
            mock_get_client.return_value = mock_client
            mock_handle = MagicMock()
            mock_handle.workflow_id = "wf-thread-test"
            mock_to_thread.return_value = mock_handle

            result = await enqueue_single_fact_check_chunk(
                fact_check_id=fact_check_id,
            )

        assert result == "wf-thread-test"
        mock_to_thread.assert_called_once()
        assert mock_to_thread.call_args.args[0] == mock_client.enqueue

    @pytest.mark.asyncio
    async def test_previously_seen_dispatch_handles_empty_items(self) -> None:
        """dispatch_dbos_previously_seen_rechunk_workflow completes immediately with no items."""
        from src.dbos_workflows.rechunk_workflow import (
            dispatch_dbos_previously_seen_rechunk_workflow,
        )

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        mock_job = MagicMock()
        mock_job.id = uuid4()

        with patch("src.dbos_workflows.rechunk_workflow.BatchJobService") as mock_service_cls:
            mock_service = MagicMock()
            mock_service.create_job = AsyncMock(return_value=mock_job)
            mock_service.start_job = AsyncMock()
            mock_service.complete_job = AsyncMock()
            mock_service_cls.return_value = mock_service

            result = await dispatch_dbos_previously_seen_rechunk_workflow(
                db=mock_db,
                community_server_id=uuid4(),
            )

        assert result == mock_job.id
        mock_service.start_job.assert_called_once()
        mock_service.complete_job.assert_called_once_with(
            mock_job.id, completed_tasks=0, failed_tasks=0
        )
