"""Unit tests for DBOS bulk approval workflow.

Tests cover:
- Deprecated TaskIQ stub returns {"status": "deprecated"}
- Workflow name constant matches __qualname__
- Workflow processes batches and finalizes correctly
- Empty candidate set completes immediately
- Circuit breaker trips on consecutive failures
- Circuit breaker trips mark job as FAILED (not completed)
- Error aggregation respects MAX_STORED_ERRORS
- Import service dispatches via wrapper function
- Bulk UPDATE failure triggers db.rollback()
- start_batch_job_sync failure aborts workflow
- Progress update guard skips total_scanned==0
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, call, patch
from uuid import uuid4

import pytest


class TestDeprecatedTaskIQStub:
    @pytest.mark.asyncio
    async def test_process_bulk_approval_returns_deprecated(self):
        from src.tasks.approval_tasks import process_bulk_approval

        result = await process_bulk_approval(
            job_id="fake-id",
            threshold=0.9,
            auto_promote=False,
            limit=100,
        )

        assert result["status"] == "deprecated"
        assert result["migrated_to"] == "dbos"

    def test_task_is_registered_with_correct_name(self):
        from src.tasks.broker import _all_registered_tasks

        assert "approve:candidates" in _all_registered_tasks

        _, labels = _all_registered_tasks["approve:candidates"]
        assert labels["component"] == "fact_checking"
        assert labels["task_type"] == "deprecated"


class TestWorkflowNameConstants:
    def test_workflow_name_matches_qualname(self) -> None:
        from src.dbos_workflows.approval_workflow import (
            BULK_APPROVAL_WORKFLOW_NAME,
            bulk_approval_workflow,
        )

        assert bulk_approval_workflow.__qualname__ == BULK_APPROVAL_WORKFLOW_NAME

    def test_workflow_name_is_nonempty_string(self) -> None:
        from src.dbos_workflows.approval_workflow import BULK_APPROVAL_WORKFLOW_NAME

        assert isinstance(BULK_APPROVAL_WORKFLOW_NAME, str)
        assert len(BULK_APPROVAL_WORKFLOW_NAME) > 0

    def test_workflow_name_is_bare_function_name(self) -> None:
        from src.dbos_workflows.approval_workflow import BULK_APPROVAL_WORKFLOW_NAME

        assert BULK_APPROVAL_WORKFLOW_NAME == "bulk_approval_workflow"


class TestBulkApprovalWorkflowEmptyCandidates:
    def test_empty_candidates_completes_immediately(self) -> None:
        from src.dbos_workflows.approval_workflow import bulk_approval_workflow

        batch_job_id = str(uuid4())

        with (
            patch(
                "src.dbos_workflows.approval_workflow.count_approval_candidates_step"
            ) as mock_count,
            patch("src.dbos_workflows.approval_workflow.start_batch_job_sync") as mock_start,
            patch("src.dbos_workflows.approval_workflow.finalize_batch_job_sync") as mock_finalize,
            patch("src.dbos_workflows.approval_workflow.DBOS") as mock_dbos,
        ):
            mock_dbos.workflow_id = "wf-test"
            mock_count.return_value = 0
            mock_start.return_value = True

            result = bulk_approval_workflow.__wrapped__(
                batch_job_id=batch_job_id,
                threshold=0.9,
                auto_promote=False,
                limit=100,
                status=None,
                dataset_name=None,
                dataset_tags=None,
                has_content=None,
                published_date_from=None,
                published_date_to=None,
            )

        assert result == {"updated_count": 0, "promoted_count": 0}
        mock_start.assert_called_once()
        mock_finalize.assert_called_once()
        finalize_kwargs = mock_finalize.call_args.kwargs
        assert finalize_kwargs["success"] is True
        assert finalize_kwargs["completed_tasks"] == 0
        assert finalize_kwargs["failed_tasks"] == 0


class TestBulkApprovalWorkflowProcessesBatches:
    def test_processes_batches_and_finalizes(self) -> None:
        from src.dbos_workflows.approval_workflow import bulk_approval_workflow

        batch_job_id = str(uuid4())

        batch_results = [
            {
                "updated": 5,
                "promoted": 3,
                "failed": 1,
                "processed": 5,
                "last_id": str(uuid4()),
                "scanned": 10,
                "errors": ["some error"],
                "empty": False,
            },
            {
                "updated": 0,
                "promoted": 0,
                "failed": 0,
                "processed": 0,
                "last_id": str(uuid4()),
                "scanned": 0,
                "errors": ["some error"],
                "empty": True,
            },
        ]
        batch_iter = iter(batch_results)

        with (
            patch(
                "src.dbos_workflows.approval_workflow.count_approval_candidates_step"
            ) as mock_count,
            patch("src.dbos_workflows.approval_workflow.start_batch_job_sync") as mock_start,
            patch("src.dbos_workflows.approval_workflow.process_approval_batch_step") as mock_batch,
            patch("src.dbos_workflows.approval_workflow.update_batch_job_progress_sync"),
            patch("src.dbos_workflows.approval_workflow.finalize_batch_job_sync") as mock_finalize,
            patch("src.dbos_workflows.approval_workflow.DBOS") as mock_dbos,
        ):
            mock_dbos.workflow_id = "wf-test"
            mock_count.return_value = 10
            mock_start.return_value = True
            mock_batch.side_effect = lambda **kw: next(batch_iter)

            result = bulk_approval_workflow.__wrapped__(
                batch_job_id=batch_job_id,
                threshold=0.9,
                auto_promote=True,
                limit=100,
                status=None,
                dataset_name=None,
                dataset_tags=None,
                has_content=None,
                published_date_from=None,
                published_date_to=None,
            )

        assert result["updated_count"] == 5
        assert result["promoted_count"] == 3
        assert result["threshold"] == 0.9
        assert result["total_scanned"] == 10
        assert mock_batch.call_count == 2
        mock_finalize.assert_called_once()
        finalize_kwargs = mock_finalize.call_args.kwargs
        assert finalize_kwargs["success"] is True
        assert finalize_kwargs["completed_tasks"] == 5
        assert finalize_kwargs["failed_tasks"] == 1

    def test_max_iterations_guard(self) -> None:
        from src.dbos_workflows.approval_workflow import bulk_approval_workflow

        batch_job_id = str(uuid4())

        never_ending_batch = {
            "updated": 0,
            "promoted": 0,
            "failed": 0,
            "processed": 0,
            "last_id": str(uuid4()),
            "scanned": 0,
            "errors": [],
            "empty": False,
        }

        with (
            patch(
                "src.dbos_workflows.approval_workflow.count_approval_candidates_step"
            ) as mock_count,
            patch("src.dbos_workflows.approval_workflow.start_batch_job_sync") as mock_start,
            patch("src.dbos_workflows.approval_workflow.process_approval_batch_step") as mock_batch,
            patch("src.dbos_workflows.approval_workflow.update_batch_job_progress_sync"),
            patch("src.dbos_workflows.approval_workflow.finalize_batch_job_sync"),
            patch("src.dbos_workflows.approval_workflow.DBOS") as mock_dbos,
        ):
            mock_dbos.workflow_id = "wf-test"
            mock_count.return_value = 50
            mock_start.return_value = True
            mock_batch.return_value = never_ending_batch

            result = bulk_approval_workflow.__wrapped__(
                batch_job_id=batch_job_id,
                threshold=0.9,
                auto_promote=False,
                limit=10,
                status=None,
                dataset_name=None,
                dataset_tags=None,
                has_content=None,
                published_date_from=None,
                published_date_to=None,
            )

        max_expected = (10 // 100) * 10 + 20
        assert result["iterations"] == max_expected
        assert mock_batch.call_count == max_expected


class TestBulkApprovalWorkflowCircuitBreaker:
    def test_circuit_breaker_trips_on_consecutive_failures(self) -> None:
        from src.dbos_workflows.approval_workflow import bulk_approval_workflow

        batch_job_id = str(uuid4())

        with (
            patch(
                "src.dbos_workflows.approval_workflow.count_approval_candidates_step"
            ) as mock_count,
            patch("src.dbos_workflows.approval_workflow.start_batch_job_sync") as mock_start,
            patch("src.dbos_workflows.approval_workflow.process_approval_batch_step") as mock_batch,
            patch("src.dbos_workflows.approval_workflow.update_batch_job_progress_sync"),
            patch("src.dbos_workflows.approval_workflow.finalize_batch_job_sync") as mock_finalize,
            patch("src.dbos_workflows.approval_workflow.DBOS") as mock_dbos,
        ):
            mock_dbos.workflow_id = "wf-test"
            mock_count.return_value = 1000
            mock_start.return_value = True
            mock_batch.side_effect = RuntimeError("DB connection lost")

            result = bulk_approval_workflow.__wrapped__(
                batch_job_id=batch_job_id,
                threshold=0.9,
                auto_promote=False,
                limit=1000,
                status=None,
                dataset_name=None,
                dataset_tags=None,
                has_content=None,
                published_date_from=None,
                published_date_to=None,
            )

        assert mock_batch.call_count == 5
        assert result["updated_count"] == 0
        assert result["total_errors"] == 5
        assert result["circuit_breaker_tripped"] is True

        mock_finalize.assert_called_once()
        finalize_kwargs = mock_finalize.call_args.kwargs
        assert finalize_kwargs["success"] is False

    def test_circuit_breaker_with_partial_success_marks_failed(self) -> None:
        """When circuit breaker trips after some successes, job is still FAILED."""
        from src.dbos_workflows.approval_workflow import bulk_approval_workflow

        batch_job_id = str(uuid4())
        call_count = 0

        def alternate_success_failure(**kw):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                return {
                    "updated": 5,
                    "promoted": 0,
                    "failed": 0,
                    "processed": 5,
                    "last_id": str(uuid4()),
                    "scanned": 10,
                    "errors": list(kw.get("errors_so_far", [])),
                    "empty": False,
                }
            raise RuntimeError("Service down")

        with (
            patch(
                "src.dbos_workflows.approval_workflow.count_approval_candidates_step"
            ) as mock_count,
            patch("src.dbos_workflows.approval_workflow.start_batch_job_sync") as mock_start,
            patch("src.dbos_workflows.approval_workflow.process_approval_batch_step") as mock_batch,
            patch("src.dbos_workflows.approval_workflow.update_batch_job_progress_sync"),
            patch("src.dbos_workflows.approval_workflow.finalize_batch_job_sync") as mock_finalize,
            patch("src.dbos_workflows.approval_workflow.DBOS") as mock_dbos,
        ):
            mock_dbos.workflow_id = "wf-test"
            mock_count.return_value = 1000
            mock_start.return_value = True
            mock_batch.side_effect = alternate_success_failure

            result = bulk_approval_workflow.__wrapped__(
                batch_job_id=batch_job_id,
                threshold=0.9,
                auto_promote=False,
                limit=1000,
                status=None,
                dataset_name=None,
                dataset_tags=None,
                has_content=None,
                published_date_from=None,
                published_date_to=None,
            )

        assert result["updated_count"] == 10
        assert result["circuit_breaker_tripped"] is True

        mock_finalize.assert_called_once()
        finalize_kwargs = mock_finalize.call_args.kwargs
        assert finalize_kwargs["success"] is False
        assert finalize_kwargs["error_summary"]["circuit_breaker_tripped"] is True


class TestBulkApprovalWorkflowErrorAggregation:
    def test_error_aggregation_respects_max_stored_errors(self) -> None:
        from src.dbos_workflows.approval_workflow import MAX_STORED_ERRORS, bulk_approval_workflow

        batch_job_id = str(uuid4())
        call_count = 0

        def make_failing_batch(**kw):
            nonlocal call_count
            call_count += 1
            new_errors = list(kw.get("errors_so_far", []))
            for i in range(10):
                if len(new_errors) < MAX_STORED_ERRORS:
                    new_errors.append(f"Error {call_count}-{i}")
            return {
                "updated": 0,
                "promoted": 0,
                "failed": 10,
                "processed": 10,
                "last_id": str(uuid4()),
                "scanned": 10,
                "errors": new_errors,
                "empty": False,
            }

        with (
            patch(
                "src.dbos_workflows.approval_workflow.count_approval_candidates_step"
            ) as mock_count,
            patch("src.dbos_workflows.approval_workflow.start_batch_job_sync") as mock_start,
            patch("src.dbos_workflows.approval_workflow.process_approval_batch_step") as mock_batch,
            patch("src.dbos_workflows.approval_workflow.update_batch_job_progress_sync"),
            patch("src.dbos_workflows.approval_workflow.finalize_batch_job_sync"),
            patch("src.dbos_workflows.approval_workflow.DBOS") as mock_dbos,
        ):
            mock_dbos.workflow_id = "wf-test"
            mock_count.return_value = 200
            mock_start.return_value = True
            mock_batch.side_effect = make_failing_batch

            result = bulk_approval_workflow.__wrapped__(
                batch_job_id=batch_job_id,
                threshold=0.5,
                auto_promote=False,
                limit=200,
                status=None,
                dataset_name=None,
                dataset_tags=None,
                has_content=None,
                published_date_from=None,
                published_date_to=None,
            )

        assert "errors" in result
        assert len(result["errors"]) <= MAX_STORED_ERRORS


class TestBulkApprovalWorkflowWithFailedResult:
    def test_all_failed_marks_job_as_failed(self) -> None:
        from src.dbos_workflows.approval_workflow import bulk_approval_workflow

        batch_job_id = str(uuid4())

        batch_result = {
            "updated": 0,
            "promoted": 0,
            "failed": 10,
            "processed": 10,
            "last_id": str(uuid4()),
            "scanned": 10,
            "errors": ["fail1", "fail2"],
            "empty": False,
        }

        batch_results = [
            batch_result,
            {**batch_result, "empty": True, "scanned": 0, "processed": 0, "failed": 0},
        ]
        batch_iter = iter(batch_results)

        with (
            patch(
                "src.dbos_workflows.approval_workflow.count_approval_candidates_step"
            ) as mock_count,
            patch("src.dbos_workflows.approval_workflow.start_batch_job_sync") as mock_start,
            patch("src.dbos_workflows.approval_workflow.process_approval_batch_step") as mock_batch,
            patch("src.dbos_workflows.approval_workflow.update_batch_job_progress_sync"),
            patch("src.dbos_workflows.approval_workflow.finalize_batch_job_sync") as mock_finalize,
            patch("src.dbos_workflows.approval_workflow.DBOS") as mock_dbos,
        ):
            mock_dbos.workflow_id = "wf-test"
            mock_count.return_value = 10
            mock_start.return_value = True
            mock_batch.side_effect = lambda **kw: next(batch_iter)

            result = bulk_approval_workflow.__wrapped__(
                batch_job_id=batch_job_id,
                threshold=0.9,
                auto_promote=False,
                limit=100,
                status=None,
                dataset_name=None,
                dataset_tags=None,
                has_content=None,
                published_date_from=None,
                published_date_to=None,
            )

        assert result["updated_count"] == 0
        finalize_kwargs = mock_finalize.call_args.kwargs
        assert finalize_kwargs["success"] is False
        assert finalize_kwargs["failed_tasks"] == 10


class TestStartBatchJobSyncCheck:
    def test_workflow_aborts_when_start_batch_job_fails(self) -> None:
        from src.dbos_workflows.approval_workflow import bulk_approval_workflow

        batch_job_id = str(uuid4())

        with (
            patch(
                "src.dbos_workflows.approval_workflow.count_approval_candidates_step"
            ) as mock_count,
            patch("src.dbos_workflows.approval_workflow.start_batch_job_sync") as mock_start,
            patch("src.dbos_workflows.approval_workflow.finalize_batch_job_sync") as mock_finalize,
            patch("src.dbos_workflows.approval_workflow.process_approval_batch_step") as mock_batch,
            patch("src.dbos_workflows.approval_workflow.DBOS") as mock_dbos,
        ):
            mock_dbos.workflow_id = "wf-test"
            mock_count.return_value = 50
            mock_start.return_value = False

            result = bulk_approval_workflow.__wrapped__(
                batch_job_id=batch_job_id,
                threshold=0.9,
                auto_promote=False,
                limit=100,
                status=None,
                dataset_name=None,
                dataset_tags=None,
                has_content=None,
                published_date_from=None,
                published_date_to=None,
            )

        assert result["error"] == "job_start_failed"
        assert result["updated_count"] == 0
        mock_batch.assert_not_called()
        mock_finalize.assert_called_once()
        finalize_kwargs = mock_finalize.call_args.kwargs
        assert finalize_kwargs["success"] is False
        assert (
            finalize_kwargs["error_summary"]["error"] == "Failed to transition job to IN_PROGRESS"
        )


class TestProcessSingleBatchRollback:
    @pytest.mark.asyncio
    async def test_bulk_update_failure_triggers_rollback(self) -> None:
        from src.dbos_workflows.approval_workflow import _process_single_batch

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=RuntimeError("DB constraint violation"))
        mock_db.rollback = AsyncMock()
        mock_db.commit = AsyncMock()

        mock_candidate = MagicMock()
        mock_candidate.id = uuid4()
        mock_candidate.predicted_ratings = {"true": 0.95, "false": 0.05}

        errors: list[str] = []

        with patch(
            "src.dbos_workflows.approval_workflow.extract_high_confidence_rating",
            return_value="true",
        ):
            updated, _promoted, failed, _processed = await _process_single_batch(
                db=mock_db,
                batch=[mock_candidate],
                threshold=0.9,
                auto_promote=False,
                errors=errors,
            )

        assert failed == 1
        assert updated == 0
        mock_db.rollback.assert_awaited_once()
        mock_db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_bulk_update_failure_skips_promotion(self) -> None:
        """After rollback, promotions must not run on rolled-back candidates."""
        from src.dbos_workflows.approval_workflow import _process_single_batch

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=RuntimeError("DB constraint violation"))
        mock_db.rollback = AsyncMock()
        mock_db.commit = AsyncMock()

        mock_candidate = MagicMock()
        mock_candidate.id = uuid4()
        mock_candidate.predicted_ratings = {"true": 0.95, "false": 0.05}

        errors: list[str] = []

        mock_promote = AsyncMock(return_value=True)

        with (
            patch(
                "src.dbos_workflows.approval_workflow.extract_high_confidence_rating",
                return_value="true",
            ),
            patch(
                "src.fact_checking.import_pipeline.promotion.promote_candidate",
                mock_promote,
            ),
        ):
            updated, promoted, failed, _processed = await _process_single_batch(
                db=mock_db,
                batch=[mock_candidate],
                threshold=0.9,
                auto_promote=True,
                errors=errors,
            )

        assert updated == 0
        assert failed == 1
        assert promoted == 0
        mock_db.rollback.assert_awaited_once()
        mock_db.commit.assert_not_awaited()
        mock_promote.assert_not_awaited()


class TestProgressUpdateGuard:
    def test_progress_not_updated_when_total_scanned_zero(self) -> None:
        """When total_scanned==0, modulo check should not trigger progress update."""
        from src.dbos_workflows.approval_workflow import bulk_approval_workflow

        batch_job_id = str(uuid4())

        with (
            patch(
                "src.dbos_workflows.approval_workflow.count_approval_candidates_step"
            ) as mock_count,
            patch("src.dbos_workflows.approval_workflow.start_batch_job_sync") as mock_start,
            patch("src.dbos_workflows.approval_workflow.process_approval_batch_step") as mock_batch,
            patch(
                "src.dbos_workflows.approval_workflow.update_batch_job_progress_sync"
            ) as mock_progress,
            patch("src.dbos_workflows.approval_workflow.finalize_batch_job_sync"),
            patch("src.dbos_workflows.approval_workflow.DBOS") as mock_dbos,
        ):
            mock_dbos.workflow_id = "wf-test"
            mock_count.return_value = 10
            mock_start.return_value = True
            mock_batch.side_effect = RuntimeError("fail")

            bulk_approval_workflow.__wrapped__(
                batch_job_id=batch_job_id,
                threshold=0.9,
                auto_promote=False,
                limit=1000,
                status=None,
                dataset_name=None,
                dataset_tags=None,
                has_content=None,
                published_date_from=None,
                published_date_to=None,
            )

        for progress_call in mock_progress.call_args_list:
            if progress_call == call(
                mock_progress.call_args_list[0].args[0],
                completed_tasks=0,
                failed_tasks=mock_progress.call_args_list[0].kwargs.get("failed_tasks", 0),
            ):
                continue
            kwargs = progress_call.kwargs
            if "current_item" in kwargs:
                assert "Scanned 0" not in kwargs["current_item"]


class TestDispatchFromImportService:
    @pytest.mark.asyncio
    async def test_start_bulk_approval_job_calls_dispatch_wrapper(self) -> None:
        from src.batch_jobs.import_service import ImportBatchJobService

        mock_session = AsyncMock()

        service = ImportBatchJobService(mock_session)

        mock_job = MagicMock()
        mock_job.id = uuid4()
        mock_job.job_type = "approve:candidates"
        mock_job.metadata_ = {}

        mock_batch_service = AsyncMock()
        mock_batch_service.create_job.return_value = mock_job
        mock_batch_service.set_workflow_id.return_value = None
        service._batch_job_service = mock_batch_service

        with patch(
            "src.dbos_workflows.approval_workflow.dispatch_bulk_approval_workflow",
            new_callable=AsyncMock,
            return_value="dbos-wf-123",
        ) as mock_dispatch:
            result = await service.start_bulk_approval_job(
                threshold=0.9,
                auto_promote=True,
                limit=200,
            )

        assert result is mock_job
        mock_dispatch.assert_called_once()
        dispatch_kwargs = mock_dispatch.call_args.kwargs
        assert dispatch_kwargs["batch_job_id"] == mock_job.id
        assert dispatch_kwargs["threshold"] == 0.9
        assert dispatch_kwargs["auto_promote"] is True
        assert dispatch_kwargs["limit"] == 200

        mock_batch_service.set_workflow_id.assert_called_once_with(mock_job.id, "dbos-wf-123")


class TestDispatchBulkApprovalWorkflow:
    @pytest.mark.asyncio
    async def test_dispatch_enqueues_via_dbos_client(self) -> None:
        from src.dbos_workflows.approval_workflow import dispatch_bulk_approval_workflow

        mock_client = MagicMock()
        mock_handle = MagicMock()
        mock_handle.workflow_id = "dbos-wf-456"
        mock_client.enqueue.return_value = mock_handle

        job_id = uuid4()

        with (
            patch(
                "src.dbos_workflows.config.get_dbos_client",
                return_value=mock_client,
            ),
            patch("asyncio.to_thread", side_effect=lambda fn, *args: fn(*args)),
        ):
            workflow_id = await dispatch_bulk_approval_workflow(
                batch_job_id=job_id,
                threshold=0.9,
                auto_promote=True,
                limit=200,
            )

        assert workflow_id == "dbos-wf-456"
        mock_client.enqueue.assert_called_once()
        enqueue_args = mock_client.enqueue.call_args
        options = enqueue_args.args[0]
        assert options["queue_name"] == "approval"
        assert options["workflow_name"] == "bulk_approval_workflow"

        (
            batch_job_id,
            threshold,
            auto_promote,
            limit,
            status,
            dataset_name,
            dataset_tags,
            has_content,
            published_date_from,
            published_date_to,
        ) = enqueue_args.args[1:]
        assert batch_job_id == str(job_id)
        assert threshold == 0.9
        assert auto_promote is True
        assert limit == 200
        assert status is None
        assert dataset_name is None
        assert dataset_tags is None
        assert has_content is None
        assert published_date_from is None
        assert published_date_to is None
