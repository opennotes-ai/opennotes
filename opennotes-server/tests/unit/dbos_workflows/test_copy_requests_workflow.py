from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


class TestCopyRequestsQueueConfiguration:
    def test_queue_exists_with_correct_name(self) -> None:
        from src.dbos_workflows.copy_requests_workflow import copy_requests_queue

        assert copy_requests_queue.name == "copy_requests"

    def test_queue_worker_concurrency(self) -> None:
        from src.dbos_workflows.copy_requests_workflow import copy_requests_queue

        assert copy_requests_queue.worker_concurrency == 2

    def test_queue_global_concurrency(self) -> None:
        from src.dbos_workflows.copy_requests_workflow import copy_requests_queue

        assert copy_requests_queue.concurrency == 5


class TestConstants:
    def test_failure_threshold(self) -> None:
        from src.dbos_workflows.copy_requests_workflow import FAILURE_THRESHOLD

        assert FAILURE_THRESHOLD == 0.5

    def test_copy_batch_size(self) -> None:
        from src.dbos_workflows.copy_requests_workflow import COPY_BATCH_SIZE

        assert COPY_BATCH_SIZE == 50

    def test_workflow_name_constant(self) -> None:
        from src.dbos_workflows.copy_requests_workflow import (
            COPY_REQUESTS_WORKFLOW_NAME,
        )

        assert COPY_REQUESTS_WORKFLOW_NAME == "copy_requests_workflow"


class TestComputeBatchSuccess:
    def test_returns_true_when_no_failures(self) -> None:
        from src.dbos_workflows.copy_requests_workflow import _compute_batch_success

        assert _compute_batch_success(10, 0) is True

    def test_returns_false_when_all_failed(self) -> None:
        from src.dbos_workflows.copy_requests_workflow import _compute_batch_success

        assert _compute_batch_success(0, 10) is False

    def test_returns_false_when_no_items(self) -> None:
        from src.dbos_workflows.copy_requests_workflow import _compute_batch_success

        assert _compute_batch_success(0, 0) is False

    def test_returns_true_below_threshold(self) -> None:
        from src.dbos_workflows.copy_requests_workflow import _compute_batch_success

        assert _compute_batch_success(6, 4) is True

    def test_returns_false_at_threshold(self) -> None:
        from src.dbos_workflows.copy_requests_workflow import _compute_batch_success

        assert _compute_batch_success(5, 5) is False


class TestCopyRequestsStep:
    def test_calls_copy_request_service_and_returns_result(self) -> None:
        from src.dbos_workflows.copy_requests_workflow import copy_requests_step

        batch_job_id = str(uuid4())
        source_id = str(uuid4())
        target_id = str(uuid4())

        mock_copy_result = MagicMock()
        mock_copy_result.total_copied = 10
        mock_copy_result.total_skipped = 2
        mock_copy_result.total_failed = 1

        with (
            patch("src.dbos_workflows.copy_requests_workflow.run_sync") as mock_run_sync,
        ):
            mock_run_sync.return_value = {
                "total_copied": 10,
                "total_skipped": 2,
                "total_failed": 1,
            }

            result = copy_requests_step.__wrapped__(
                batch_job_id=batch_job_id,
                source_community_server_id=source_id,
                target_community_server_id=target_id,
            )

        assert result["total_copied"] == 10
        assert result["total_skipped"] == 2
        assert result["total_failed"] == 1

    def test_step_raises_on_service_error(self) -> None:
        from src.dbos_workflows.copy_requests_workflow import copy_requests_step

        batch_job_id = str(uuid4())
        source_id = str(uuid4())
        target_id = str(uuid4())

        with (
            patch(
                "src.dbos_workflows.copy_requests_workflow.run_sync",
                side_effect=RuntimeError("DB connection lost"),
            ),
            pytest.raises(RuntimeError, match="DB connection lost"),
        ):
            copy_requests_step.__wrapped__(
                batch_job_id=batch_job_id,
                source_community_server_id=source_id,
                target_community_server_id=target_id,
            )


class TestCopyRequestsWorkflow:
    def test_calls_step_and_finalizes_success(self) -> None:
        from src.dbos_workflows.copy_requests_workflow import copy_requests_workflow

        batch_job_id = str(uuid4())
        source_id = str(uuid4())
        target_id = str(uuid4())

        with (
            patch("src.dbos_workflows.copy_requests_workflow.copy_requests_step") as mock_step,
            patch(
                "src.dbos_workflows.copy_requests_workflow.finalize_batch_job_sync"
            ) as mock_finalize,
            patch("src.dbos_workflows.copy_requests_workflow.DBOS") as mock_dbos,
        ):
            mock_dbos.workflow_id = "test-workflow-id"
            mock_step.return_value = {
                "total_copied": 10,
                "total_skipped": 2,
                "total_failed": 0,
            }
            mock_finalize.return_value = True

            result = copy_requests_workflow.__wrapped__(
                batch_job_id=batch_job_id,
                source_community_server_id=source_id,
                target_community_server_id=target_id,
            )

        assert result["total_copied"] == 10
        assert result["total_skipped"] == 2
        assert result["total_failed"] == 0

        mock_step.assert_called_once_with(
            batch_job_id,
            source_id,
            target_id,
        )
        mock_finalize.assert_called_once()
        call_kwargs = mock_finalize.call_args
        assert call_kwargs[1]["success"] is True
        assert call_kwargs[1]["completed_tasks"] == 10
        assert call_kwargs[1]["failed_tasks"] == 0

    def test_finalizes_as_failed_when_many_failures(self) -> None:
        from src.dbos_workflows.copy_requests_workflow import copy_requests_workflow

        batch_job_id = str(uuid4())
        source_id = str(uuid4())
        target_id = str(uuid4())

        with (
            patch("src.dbos_workflows.copy_requests_workflow.copy_requests_step") as mock_step,
            patch(
                "src.dbos_workflows.copy_requests_workflow.finalize_batch_job_sync"
            ) as mock_finalize,
            patch("src.dbos_workflows.copy_requests_workflow.DBOS") as mock_dbos,
        ):
            mock_dbos.workflow_id = "test-workflow-id"
            mock_step.return_value = {
                "total_copied": 3,
                "total_skipped": 0,
                "total_failed": 7,
            }
            mock_finalize.return_value = True

            result = copy_requests_workflow.__wrapped__(
                batch_job_id=batch_job_id,
                source_community_server_id=source_id,
                target_community_server_id=target_id,
            )

        assert result["total_failed"] == 7
        call_kwargs = mock_finalize.call_args
        assert call_kwargs[1]["success"] is False

    def test_returns_step_result(self) -> None:
        from src.dbos_workflows.copy_requests_workflow import copy_requests_workflow

        batch_job_id = str(uuid4())
        source_id = str(uuid4())
        target_id = str(uuid4())

        with (
            patch("src.dbos_workflows.copy_requests_workflow.copy_requests_step") as mock_step,
            patch(
                "src.dbos_workflows.copy_requests_workflow.finalize_batch_job_sync"
            ) as mock_finalize,
            patch("src.dbos_workflows.copy_requests_workflow.DBOS") as mock_dbos,
        ):
            mock_dbos.workflow_id = "test-workflow-id"
            mock_step.return_value = {
                "total_copied": 5,
                "total_skipped": 1,
                "total_failed": 0,
            }
            mock_finalize.return_value = True

            result = copy_requests_workflow.__wrapped__(
                batch_job_id=batch_job_id,
                source_community_server_id=source_id,
                target_community_server_id=target_id,
            )

        assert result == {
            "total_copied": 5,
            "total_skipped": 1,
            "total_failed": 0,
        }


class TestDispatchCopyRequests:
    @pytest.mark.asyncio
    async def test_creates_batch_job_and_enqueues_workflow(self) -> None:
        from src.dbos_workflows.copy_requests_workflow import dispatch_copy_requests

        source_id = uuid4()
        target_id = uuid4()

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = 25
        mock_db.execute = AsyncMock(return_value=mock_result)

        mock_job = MagicMock()
        mock_job.id = uuid4()

        mock_handle = MagicMock()
        mock_handle.workflow_id = "wf-123"

        with (
            patch(
                "src.dbos_workflows.copy_requests_workflow.BatchJobService"
            ) as mock_batch_job_cls,
            patch(
                "src.dbos_workflows.copy_requests_workflow.safe_enqueue",
                new_callable=AsyncMock,
                return_value=mock_handle,
            ) as mock_safe_enqueue,
        ):
            mock_service = AsyncMock()
            mock_service.create_job = AsyncMock(return_value=mock_job)
            mock_service.start_job = AsyncMock()
            mock_service.set_workflow_id = AsyncMock()
            mock_batch_job_cls.return_value = mock_service

            result = await dispatch_copy_requests(
                db=mock_db,
                source_community_server_id=source_id,
                target_community_server_id=target_id,
            )

        assert result == mock_job.id
        mock_service.create_job.assert_called_once()
        create_arg = mock_service.create_job.call_args[0][0]
        assert create_arg.job_type == "copy:requests"
        assert create_arg.total_tasks == 25

        mock_service.start_job.assert_called_once_with(mock_job.id)
        mock_safe_enqueue.assert_called_once()
        mock_service.set_workflow_id.assert_called_once_with(mock_job.id, "wf-123")

    @pytest.mark.asyncio
    async def test_completes_immediately_when_zero_requests(self) -> None:
        from src.dbos_workflows.copy_requests_workflow import dispatch_copy_requests

        source_id = uuid4()
        target_id = uuid4()

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = 0
        mock_db.execute = AsyncMock(return_value=mock_result)

        mock_job = MagicMock()
        mock_job.id = uuid4()

        with (
            patch(
                "src.dbos_workflows.copy_requests_workflow.BatchJobService"
            ) as mock_batch_job_cls,
            patch(
                "src.dbos_workflows.copy_requests_workflow.safe_enqueue",
                new_callable=AsyncMock,
            ) as mock_safe_enqueue,
        ):
            mock_service = AsyncMock()
            mock_service.create_job = AsyncMock(return_value=mock_job)
            mock_service.start_job = AsyncMock()
            mock_service.complete_job = AsyncMock()
            mock_batch_job_cls.return_value = mock_service

            result = await dispatch_copy_requests(
                db=mock_db,
                source_community_server_id=source_id,
                target_community_server_id=target_id,
            )

        assert result == mock_job.id
        mock_service.start_job.assert_called_once_with(mock_job.id)
        mock_service.complete_job.assert_called_once_with(
            mock_job.id, completed_tasks=0, failed_tasks=0
        )
        mock_safe_enqueue.assert_not_called()

    @pytest.mark.asyncio
    async def test_fails_job_on_enqueue_error(self) -> None:
        from src.dbos_workflows.copy_requests_workflow import dispatch_copy_requests

        source_id = uuid4()
        target_id = uuid4()

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = 10
        mock_db.execute = AsyncMock(return_value=mock_result)

        mock_job = MagicMock()
        mock_job.id = uuid4()

        with (
            patch(
                "src.dbos_workflows.copy_requests_workflow.BatchJobService"
            ) as mock_batch_job_cls,
            patch(
                "src.dbos_workflows.copy_requests_workflow.safe_enqueue",
                new_callable=AsyncMock,
                side_effect=RuntimeError("DBOS unavailable"),
            ),
        ):
            mock_service = AsyncMock()
            mock_service.create_job = AsyncMock(return_value=mock_job)
            mock_service.start_job = AsyncMock()
            mock_service.fail_job = AsyncMock()
            mock_batch_job_cls.return_value = mock_service

            with pytest.raises(RuntimeError, match="DBOS unavailable"):
                await dispatch_copy_requests(
                    db=mock_db,
                    source_community_server_id=source_id,
                    target_community_server_id=target_id,
                )

        mock_service.fail_job.assert_called_once()
        fail_kwargs = mock_service.fail_job.call_args
        assert fail_kwargs[0][0] == mock_job.id

    @pytest.mark.asyncio
    async def test_job_metadata_includes_expected_fields(self) -> None:
        from src.dbos_workflows.copy_requests_workflow import dispatch_copy_requests

        source_id = uuid4()
        target_id = uuid4()

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = 5
        mock_db.execute = AsyncMock(return_value=mock_result)

        mock_job = MagicMock()
        mock_job.id = uuid4()

        mock_handle = MagicMock()
        mock_handle.workflow_id = "wf-456"

        with (
            patch(
                "src.dbos_workflows.copy_requests_workflow.BatchJobService"
            ) as mock_batch_job_cls,
            patch(
                "src.dbos_workflows.copy_requests_workflow.safe_enqueue",
                new_callable=AsyncMock,
                return_value=mock_handle,
            ),
        ):
            mock_service = AsyncMock()
            mock_service.create_job = AsyncMock(return_value=mock_job)
            mock_service.start_job = AsyncMock()
            mock_service.set_workflow_id = AsyncMock()
            mock_batch_job_cls.return_value = mock_service

            await dispatch_copy_requests(
                db=mock_db,
                source_community_server_id=source_id,
                target_community_server_id=target_id,
            )

        create_arg = mock_service.create_job.call_args[0][0]
        metadata = create_arg.metadata_
        assert metadata["source_community_server_id"] == str(source_id)
        assert metadata["target_community_server_id"] == str(target_id)
        assert metadata["execution_backend"] == "dbos"
