"""Tests for DBOS rechunk previously-seen workflow.

Tests the rechunk previously-seen workflow components including
process_previously_seen_item step, the main workflow function,
the dispatch function, and the sync wrapper.

Note: Tests mock the synchronous helper functions that wrap async operations
since DBOS steps/workflows are synchronous. The actual DBOS decorators
add checkpointing and retry behavior.
"""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.dbos_workflows.circuit_breaker import CircuitOpenError


class TestProcessPreviouslySeenItem:
    def test_returns_success_on_successful_processing(self) -> None:
        from src.dbos_workflows.rechunk_workflow import process_previously_seen_item

        item_id = str(uuid4())
        community_server_id = str(uuid4())

        with patch(
            "src.dbos_workflows.rechunk_workflow.chunk_and_embed_previously_seen_sync"
        ) as mock_chunk:
            mock_chunk.return_value = {"chunks_created": 3}

            result = process_previously_seen_item.__wrapped__(
                item_id=item_id,
                community_server_id=community_server_id,
            )

        assert result["success"] is True
        assert result["item_id"] == item_id
        assert result["chunks_created"] == 3

    def test_raises_on_processing_failure(self) -> None:
        from src.dbos_workflows.rechunk_workflow import process_previously_seen_item

        item_id = str(uuid4())
        community_server_id = str(uuid4())

        with patch(
            "src.dbos_workflows.rechunk_workflow.chunk_and_embed_previously_seen_sync"
        ) as mock_chunk:
            mock_chunk.side_effect = RuntimeError("Embedding service unavailable")

            with pytest.raises(RuntimeError, match="Embedding service unavailable"):
                process_previously_seen_item.__wrapped__(
                    item_id=item_id,
                    community_server_id=community_server_id,
                )

    def test_returns_zero_chunks_for_empty_content(self) -> None:
        from src.dbos_workflows.rechunk_workflow import process_previously_seen_item

        item_id = str(uuid4())
        community_server_id = str(uuid4())

        with patch(
            "src.dbos_workflows.rechunk_workflow.chunk_and_embed_previously_seen_sync"
        ) as mock_chunk:
            mock_chunk.return_value = {"chunks_created": 0}

            result = process_previously_seen_item.__wrapped__(
                item_id=item_id,
                community_server_id=community_server_id,
            )

        assert result["success"] is True
        assert result["chunks_created"] == 0


class TestChunkAndEmbedPreviouslySeenSync:
    def test_wrapper_narrows_lock_to_chunking_only(self) -> None:
        from src.dbos_workflows.rechunk_workflow import (
            chunk_and_embed_previously_seen_sync,
        )

        previously_seen_id = uuid4()
        community_server_id = uuid4()

        mock_service = MagicMock()
        mock_chunking_service = MagicMock()
        mock_chunking_service.chunk_text.return_value = ["chunk1", "chunk2"]

        @contextmanager
        def mock_use_chunking_sync():
            yield mock_chunking_service

        with (
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
            mock_run_sync.side_effect = ["some text content", {"chunks_created": 3}]

            result = chunk_and_embed_previously_seen_sync(
                previously_seen_id=previously_seen_id,
                community_server_id=community_server_id,
            )

            assert result["chunks_created"] == 3
            assert mock_run_sync.call_count == 2
            mock_chunking_service.chunk_text.assert_called_once_with("some text content")
            mock_service.chunk_and_embed_previously_seen.assert_not_called()

    def test_returns_zero_chunks_for_empty_content(self) -> None:
        from src.dbos_workflows.rechunk_workflow import (
            chunk_and_embed_previously_seen_sync,
        )

        previously_seen_id = uuid4()
        community_server_id = uuid4()

        mock_service = MagicMock()

        with (
            patch("src.dbos_workflows.rechunk_workflow.run_sync") as mock_run_sync,
            patch(
                "src.dbos_workflows.rechunk_workflow.get_chunk_embedding_service",
                return_value=mock_service,
            ),
        ):
            mock_run_sync.return_value = ""

            result = chunk_and_embed_previously_seen_sync(
                previously_seen_id=previously_seen_id,
                community_server_id=community_server_id,
            )

            assert result["chunks_created"] == 0
            assert mock_run_sync.call_count == 1


class TestRechunkPreviouslySeenWorkflow:
    def test_workflow_processes_all_items(self) -> None:
        from src.dbos_workflows.rechunk_workflow import rechunk_previously_seen_workflow

        batch_job_id = str(uuid4())
        community_server_id = str(uuid4())
        item_ids = [str(uuid4()) for _ in range(3)]

        with (
            patch(
                "src.dbos_workflows.rechunk_workflow.process_previously_seen_item"
            ) as mock_process,
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

            result = rechunk_previously_seen_workflow.__wrapped__(
                batch_job_id=batch_job_id,
                community_server_id=community_server_id,
                item_ids=item_ids,
            )

            assert mock_process.call_count == 3
            assert result["completed_count"] == 3
            assert result["failed_count"] == 0

    def test_workflow_handles_item_failure(self) -> None:
        from src.dbos_workflows.rechunk_workflow import rechunk_previously_seen_workflow

        batch_job_id = str(uuid4())
        community_server_id = str(uuid4())
        item_ids = [str(uuid4()) for _ in range(3)]

        call_count = 0

        def mock_process_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RuntimeError("Failed")
            return {"success": True, "chunks_created": 1}

        with (
            patch(
                "src.dbos_workflows.rechunk_workflow.process_previously_seen_item"
            ) as mock_process,
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

            result = rechunk_previously_seen_workflow.__wrapped__(
                batch_job_id=batch_job_id,
                community_server_id=community_server_id,
                item_ids=item_ids,
            )

            assert result["completed_count"] == 2
            assert result["failed_count"] == 1
            assert len(result["errors"]) == 1

    def test_workflow_stops_on_circuit_breaker_open(self) -> None:
        from src.dbos_workflows.rechunk_workflow import rechunk_previously_seen_workflow

        batch_job_id = str(uuid4())
        community_server_id = str(uuid4())
        item_ids = [str(uuid4()) for _ in range(10)]

        with (
            patch(
                "src.dbos_workflows.rechunk_workflow.process_previously_seen_item"
            ) as mock_process,
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
                rechunk_previously_seen_workflow.__wrapped__(
                    batch_job_id=batch_job_id,
                    community_server_id=community_server_id,
                    item_ids=item_ids,
                )

    def test_workflow_finalizes_batch_job_on_success(self) -> None:
        from src.dbos_workflows.rechunk_workflow import rechunk_previously_seen_workflow

        batch_job_id = str(uuid4())
        community_server_id = str(uuid4())
        item_ids = [str(uuid4())]

        with (
            patch(
                "src.dbos_workflows.rechunk_workflow.process_previously_seen_item"
            ) as mock_process,
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

            rechunk_previously_seen_workflow.__wrapped__(
                batch_job_id=batch_job_id,
                community_server_id=community_server_id,
                item_ids=item_ids,
            )

            mock_finalize.assert_called_once()
            call_kwargs = mock_finalize.call_args.kwargs
            assert call_kwargs["success"] is True

    def test_workflow_updates_progress_periodically(self) -> None:
        from src.dbos_workflows.rechunk_workflow import rechunk_previously_seen_workflow

        batch_job_id = str(uuid4())
        community_server_id = str(uuid4())
        item_ids = [str(uuid4()) for _ in range(150)]

        with (
            patch(
                "src.dbos_workflows.rechunk_workflow.process_previously_seen_item"
            ) as mock_process,
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

            rechunk_previously_seen_workflow.__wrapped__(
                batch_job_id=batch_job_id,
                community_server_id=community_server_id,
                item_ids=item_ids,
                batch_size=100,
            )

            progress_calls = mock_progress.call_count
            assert progress_calls == 2


class TestRechunkPreviouslySeenWorkflowName:
    def test_workflow_name_matches_qualname(self) -> None:
        from src.dbos_workflows.rechunk_workflow import (
            RECHUNK_PREVIOUSLY_SEEN_WORKFLOW_NAME,
            rechunk_previously_seen_workflow,
        )

        assert (
            rechunk_previously_seen_workflow.__qualname__ == RECHUNK_PREVIOUSLY_SEEN_WORKFLOW_NAME
        )

    def test_workflow_name_is_nonempty_string(self) -> None:
        from src.dbos_workflows.rechunk_workflow import (
            RECHUNK_PREVIOUSLY_SEEN_WORKFLOW_NAME,
        )

        assert isinstance(RECHUNK_PREVIOUSLY_SEEN_WORKFLOW_NAME, str)
        assert len(RECHUNK_PREVIOUSLY_SEEN_WORKFLOW_NAME) > 0

    def test_workflow_name_is_bare_function_name(self) -> None:
        from src.dbos_workflows.rechunk_workflow import (
            RECHUNK_PREVIOUSLY_SEEN_WORKFLOW_NAME,
        )

        assert RECHUNK_PREVIOUSLY_SEEN_WORKFLOW_NAME == "rechunk_previously_seen_workflow"


class TestDispatchPreviouslySeenRechunkWorkflow:
    @pytest.mark.asyncio
    async def test_dispatches_workflow_with_correct_args(self) -> None:
        from src.dbos_workflows.rechunk_workflow import (
            dispatch_dbos_previously_seen_rechunk_workflow,
        )

        community_server_id = uuid4()
        item_id = uuid4()
        batch_size = 50

        mock_db = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [(item_id,)]
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        mock_job = MagicMock()
        mock_job.id = uuid4()

        with (
            patch("src.dbos_workflows.rechunk_workflow.BatchJobService") as mock_batch_job_cls,
            patch("src.dbos_workflows.rechunk_workflow.get_dbos_client") as mock_get_client,
        ):
            mock_service = mock_batch_job_cls.return_value
            mock_service.create_job = AsyncMock(return_value=mock_job)
            mock_service.start_job = AsyncMock()
            mock_service.set_workflow_id = AsyncMock()

            mock_client = MagicMock()
            mock_handle = MagicMock()
            mock_handle.workflow_id = "test-workflow-id"
            mock_client.enqueue.return_value = mock_handle
            mock_get_client.return_value = mock_client

            result = await dispatch_dbos_previously_seen_rechunk_workflow(
                db=mock_db,
                community_server_id=community_server_id,
                batch_size=batch_size,
            )

            assert result == mock_job.id
            mock_service.create_job.assert_called_once()
            mock_service.start_job.assert_called_once()
            mock_service.set_workflow_id.assert_called_once()

            stmt_arg = mock_db.execute.call_args[0][0]
            compiled = str(stmt_arg.compile(compile_kwargs={"literal_binds": True}))
            assert "community_server_id" in compiled
            assert community_server_id.hex in compiled

    @pytest.mark.asyncio
    async def test_returns_completed_job_when_no_items(self) -> None:
        from src.dbos_workflows.rechunk_workflow import (
            dispatch_dbos_previously_seen_rechunk_workflow,
        )

        community_server_id = uuid4()

        mock_db = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        mock_job = MagicMock()
        mock_job.id = uuid4()

        with patch("src.dbos_workflows.rechunk_workflow.BatchJobService") as mock_batch_job_cls:
            mock_service = mock_batch_job_cls.return_value
            mock_service.create_job = AsyncMock(return_value=mock_job)
            mock_service.start_job = AsyncMock()
            mock_service.complete_job = AsyncMock()

            result = await dispatch_dbos_previously_seen_rechunk_workflow(
                db=mock_db,
                community_server_id=community_server_id,
            )

            assert result == mock_job.id
            mock_service.create_job.assert_called_once()
            create_arg = mock_service.create_job.call_args[0][0]
            assert create_arg.total_tasks == 0
            mock_service.start_job.assert_called_once_with(mock_job.id)
            mock_service.complete_job.assert_called_once_with(
                mock_job.id, completed_tasks=0, failed_tasks=0
            )

    @pytest.mark.asyncio
    async def test_marks_job_failed_on_dispatch_error(self) -> None:
        from src.dbos_workflows.rechunk_workflow import (
            dispatch_dbos_previously_seen_rechunk_workflow,
        )

        community_server_id = uuid4()
        item_id = uuid4()

        mock_db = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [(item_id,)]
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        mock_job = MagicMock()
        mock_job.id = uuid4()

        with (
            patch("src.dbos_workflows.rechunk_workflow.BatchJobService") as mock_batch_job_cls,
            patch("src.dbos_workflows.rechunk_workflow.get_dbos_client") as mock_get_client,
        ):
            mock_service = mock_batch_job_cls.return_value
            mock_service.create_job = AsyncMock(return_value=mock_job)
            mock_service.start_job = AsyncMock()
            mock_service.fail_job = AsyncMock()

            mock_client = MagicMock()
            mock_client.enqueue.side_effect = RuntimeError("DBOS unavailable")
            mock_get_client.return_value = mock_client

            with pytest.raises(RuntimeError, match="DBOS unavailable"):
                await dispatch_dbos_previously_seen_rechunk_workflow(
                    db=mock_db,
                    community_server_id=community_server_id,
                )

            mock_service.fail_job.assert_called_once()


class TestCircuitBreakerInPreviouslySeenWorkflow:
    def test_circuit_trips_after_consecutive_failures(self) -> None:
        from src.dbos_workflows.rechunk_workflow import rechunk_previously_seen_workflow

        batch_job_id = str(uuid4())
        community_server_id = str(uuid4())
        item_ids = [str(uuid4()) for _ in range(10)]

        call_count = 0

        def fail_always(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise RuntimeError("Always fail")

        with (
            patch(
                "src.dbos_workflows.rechunk_workflow.process_previously_seen_item"
            ) as mock_process,
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
                rechunk_previously_seen_workflow.__wrapped__(
                    batch_job_id=batch_job_id,
                    community_server_id=community_server_id,
                    item_ids=item_ids,
                )

            assert call_count == 5

    def test_circuit_resets_after_success(self) -> None:
        from src.dbos_workflows.rechunk_workflow import rechunk_previously_seen_workflow

        batch_job_id = str(uuid4())
        community_server_id = str(uuid4())
        item_ids = [str(uuid4()) for _ in range(10)]

        call_count = 0

        def intermittent_fail(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count % 3 == 0:
                return {"success": True, "chunks_created": 1}
            raise RuntimeError("Intermittent fail")

        with (
            patch(
                "src.dbos_workflows.rechunk_workflow.process_previously_seen_item"
            ) as mock_process,
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

            result = rechunk_previously_seen_workflow.__wrapped__(
                batch_job_id=batch_job_id,
                community_server_id=community_server_id,
                item_ids=item_ids,
            )

            assert result["completed_count"] + result["failed_count"] == 10
