"""Tests for DBOS import pipeline workflows.

Tests the three import pipeline workflows:
1. fact_check_import_workflow: CSV import from HuggingFace
2. scrape_candidates_workflow: Batch URL scraping
3. promote_candidates_workflow: Batch candidate promotion

Tests use __wrapped__ to bypass DBOS decorators and mock external
dependencies (database, HTTP, DBOS client).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


class TestImportPipelineQueueConfiguration:
    def test_queue_exists(self) -> None:
        from src.dbos_workflows.import_workflow import import_pipeline_queue

        assert import_pipeline_queue.name == "import_pipeline"

    def test_queue_worker_concurrency(self) -> None:
        from src.dbos_workflows.import_workflow import import_pipeline_queue

        assert import_pipeline_queue.worker_concurrency == 1

    def test_queue_global_concurrency(self) -> None:
        from src.dbos_workflows.import_workflow import import_pipeline_queue

        assert import_pipeline_queue.concurrency == 3


class TestWorkflowNameConstants:
    def test_fact_check_import_workflow_name(self) -> None:
        from src.dbos_workflows.import_workflow import (
            FACT_CHECK_IMPORT_WORKFLOW_NAME,
            fact_check_import_workflow,
        )

        assert fact_check_import_workflow.__qualname__ == FACT_CHECK_IMPORT_WORKFLOW_NAME

    def test_scrape_candidates_workflow_name(self) -> None:
        from src.dbos_workflows.import_workflow import (
            SCRAPE_CANDIDATES_WORKFLOW_NAME,
            scrape_candidates_workflow,
        )

        assert scrape_candidates_workflow.__qualname__ == SCRAPE_CANDIDATES_WORKFLOW_NAME

    def test_promote_candidates_workflow_name(self) -> None:
        from src.dbos_workflows.import_workflow import (
            PROMOTE_CANDIDATES_WORKFLOW_NAME,
            promote_candidates_workflow,
        )

        assert promote_candidates_workflow.__qualname__ == PROMOTE_CANDIDATES_WORKFLOW_NAME


class TestAggregateErrors:
    def test_returns_all_errors_within_limit(self) -> None:
        from src.dbos_workflows.import_workflow import _aggregate_errors

        errors = ["error1", "error2", "error3"]
        result = _aggregate_errors(errors)

        assert result["validation_errors"] == errors
        assert result["total_validation_errors"] == 3
        assert result["truncated"] is False

    def test_truncates_errors_over_limit(self) -> None:
        from src.dbos_workflows.import_workflow import _aggregate_errors

        errors = [f"error_{i}" for i in range(100)]
        result = _aggregate_errors(errors, max_errors=10)

        assert len(result["validation_errors"]) == 10
        assert result["total_validation_errors"] == 100
        assert result["truncated"] is True

    def test_empty_errors(self) -> None:
        from src.dbos_workflows.import_workflow import _aggregate_errors

        result = _aggregate_errors([])

        assert result["validation_errors"] == []
        assert result["total_validation_errors"] == 0
        assert result["truncated"] is False


class TestStartImportStep:
    def test_calls_start_batch_job_sync(self) -> None:
        from src.dbos_workflows.import_workflow import start_import_step

        batch_job_id = str(uuid4())

        with patch("src.dbos_workflows.import_workflow._start_batch_job_sync") as mock_start:
            mock_start.return_value = True

            result = start_import_step.__wrapped__(batch_job_id)  # type: ignore[attr-defined]

        assert result is True
        mock_start.assert_called_once()


class TestFactCheckImportWorkflow:
    def test_successful_import(self) -> None:
        from src.dbos_workflows.import_workflow import fact_check_import_workflow

        batch_job_id = str(uuid4())
        final_stats = {
            "total_rows": 100,
            "valid_rows": 95,
            "invalid_rows": 5,
            "inserted": 90,
            "updated": 5,
            "dry_run": False,
        }

        with (
            patch("src.dbos_workflows.import_workflow.start_import_step") as mock_start,
            patch("src.dbos_workflows.import_workflow.import_csv_step") as mock_import,
            patch("src.dbos_workflows.import_workflow._finalize_batch_job_sync") as mock_finalize,
            patch("src.dbos_workflows.import_workflow.DBOS") as mock_dbos,
        ):
            mock_dbos.workflow_id = "test-workflow-id"
            mock_start.return_value = True
            mock_import.return_value = final_stats
            mock_finalize.return_value = True

            result = fact_check_import_workflow.__wrapped__(  # type: ignore[attr-defined]
                batch_job_id=batch_job_id,
                batch_size=1000,
                dry_run=False,
                enqueue_scrapes=False,
            )

        assert result["status"] == "completed"
        assert result["valid_rows"] == 95
        assert result["invalid_rows"] == 5
        mock_finalize.assert_called_once()
        call_kwargs = mock_finalize.call_args.kwargs
        assert call_kwargs["success"] is True
        assert call_kwargs["completed_tasks"] == 95
        assert call_kwargs["failed_tasks"] == 5

    def test_fails_when_start_fails(self) -> None:
        from src.dbos_workflows.import_workflow import fact_check_import_workflow

        batch_job_id = str(uuid4())

        with (
            patch("src.dbos_workflows.import_workflow.start_import_step") as mock_start,
            patch("src.dbos_workflows.import_workflow._finalize_batch_job_sync") as mock_finalize,
            patch("src.dbos_workflows.import_workflow.DBOS") as mock_dbos,
        ):
            mock_dbos.workflow_id = "test-workflow-id"
            mock_start.return_value = False
            mock_finalize.return_value = True

            result = fact_check_import_workflow.__wrapped__(  # type: ignore[attr-defined]
                batch_job_id=batch_job_id,
                batch_size=1000,
                dry_run=False,
                enqueue_scrapes=False,
            )

        assert result["status"] == "failed"
        mock_finalize.assert_called_once()
        call_kwargs = mock_finalize.call_args.kwargs
        assert call_kwargs["success"] is False

    def test_handles_csv_step_exception(self) -> None:
        from src.dbos_workflows.import_workflow import fact_check_import_workflow

        batch_job_id = str(uuid4())

        with (
            patch("src.dbos_workflows.import_workflow.start_import_step") as mock_start,
            patch("src.dbos_workflows.import_workflow.import_csv_step") as mock_import,
            patch("src.dbos_workflows.import_workflow._finalize_batch_job_sync") as mock_finalize,
            patch("src.dbos_workflows.import_workflow.DBOS") as mock_dbos,
        ):
            mock_dbos.workflow_id = "test-workflow-id"
            mock_start.return_value = True
            mock_import.side_effect = RuntimeError("CSV download failed")
            mock_finalize.return_value = True

            with pytest.raises(RuntimeError, match="CSV download failed"):
                fact_check_import_workflow.__wrapped__(  # type: ignore[attr-defined]
                    batch_job_id=batch_job_id,
                    batch_size=1000,
                    dry_run=False,
                    enqueue_scrapes=False,
                )

        mock_finalize.assert_called_once()
        call_kwargs = mock_finalize.call_args.kwargs
        assert call_kwargs["success"] is False
        assert "import_csv" in call_kwargs["error_summary"]["stage"]


class TestScrapeCandidatesWorkflow:
    def test_successful_scrape(self) -> None:
        from src.dbos_workflows.import_workflow import scrape_candidates_workflow

        batch_job_id = str(uuid4())

        with (
            patch("src.dbos_workflows.import_workflow.recover_and_count_scrape_step") as mock_init,
            patch("src.dbos_workflows.import_workflow.process_scrape_batch_step") as mock_process,
            patch("src.dbos_workflows.import_workflow._finalize_batch_job_sync") as mock_finalize,
            patch("src.dbos_workflows.import_workflow.DBOS") as mock_dbos,
        ):
            mock_dbos.workflow_id = "test-workflow-id"
            mock_init.return_value = {"recovered": 2, "total_candidates": 50}
            mock_process.return_value = {"scraped": 45, "failed": 5}
            mock_finalize.return_value = True

            result = scrape_candidates_workflow.__wrapped__(  # type: ignore[attr-defined]
                batch_job_id=batch_job_id,
                batch_size=100,
                dry_run=False,
                concurrency=5,
                base_delay=1.0,
            )

        assert result["status"] == "completed"
        assert result["scraped"] == 45
        assert result["failed"] == 5
        assert result["recovered_stuck"] == 2
        assert result["total_candidates"] == 50
        mock_finalize.assert_called_once()
        call_kwargs = mock_finalize.call_args.kwargs
        assert call_kwargs["success"] is True

    def test_dry_run_skips_scraping(self) -> None:
        from src.dbos_workflows.import_workflow import scrape_candidates_workflow

        batch_job_id = str(uuid4())

        with (
            patch("src.dbos_workflows.import_workflow.recover_and_count_scrape_step") as mock_init,
            patch("src.dbos_workflows.import_workflow.process_scrape_batch_step") as mock_process,
            patch("src.dbos_workflows.import_workflow._finalize_batch_job_sync") as mock_finalize,
            patch("src.dbos_workflows.import_workflow.DBOS") as mock_dbos,
        ):
            mock_dbos.workflow_id = "test-workflow-id"
            mock_init.return_value = {"recovered": 0, "total_candidates": 50}
            mock_finalize.return_value = True

            result = scrape_candidates_workflow.__wrapped__(  # type: ignore[attr-defined]
                batch_job_id=batch_job_id,
                batch_size=100,
                dry_run=True,
            )

        assert result["status"] == "completed"
        assert result["dry_run"] is True
        assert result["scraped"] == 0
        mock_process.assert_not_called()

    def test_handles_scrape_exception(self) -> None:
        from src.dbos_workflows.import_workflow import scrape_candidates_workflow

        batch_job_id = str(uuid4())

        with (
            patch("src.dbos_workflows.import_workflow.recover_and_count_scrape_step") as mock_init,
            patch("src.dbos_workflows.import_workflow.process_scrape_batch_step") as mock_process,
            patch("src.dbos_workflows.import_workflow._finalize_batch_job_sync") as mock_finalize,
            patch("src.dbos_workflows.import_workflow.DBOS") as mock_dbos,
        ):
            mock_dbos.workflow_id = "test-workflow-id"
            mock_init.return_value = {"recovered": 0, "total_candidates": 50}
            mock_process.side_effect = RuntimeError("Connection refused")
            mock_finalize.return_value = True

            with pytest.raises(RuntimeError, match="Connection refused"):
                scrape_candidates_workflow.__wrapped__(  # type: ignore[attr-defined]
                    batch_job_id=batch_job_id,
                    batch_size=100,
                    dry_run=False,
                )

        mock_finalize.assert_called_once()
        call_kwargs = mock_finalize.call_args.kwargs
        assert call_kwargs["success"] is False
        assert call_kwargs["error_summary"]["stage"] == "scrape"


class TestPromoteCandidatesWorkflow:
    def test_successful_promotion(self) -> None:
        from src.dbos_workflows.import_workflow import promote_candidates_workflow

        batch_job_id = str(uuid4())

        with (
            patch("src.dbos_workflows.import_workflow.recover_and_count_promote_step") as mock_init,
            patch(
                "src.dbos_workflows.import_workflow.process_promotion_batch_step"
            ) as mock_process,
            patch("src.dbos_workflows.import_workflow._finalize_batch_job_sync") as mock_finalize,
            patch("src.dbos_workflows.import_workflow.DBOS") as mock_dbos,
        ):
            mock_dbos.workflow_id = "test-workflow-id"
            mock_init.return_value = {"recovered": 1, "total_candidates": 30}
            mock_process.return_value = {"promoted": 28, "failed": 2}
            mock_finalize.return_value = True

            result = promote_candidates_workflow.__wrapped__(  # type: ignore[attr-defined]
                batch_job_id=batch_job_id,
                batch_size=100,
                dry_run=False,
            )

        assert result["status"] == "completed"
        assert result["promoted"] == 28
        assert result["failed"] == 2
        assert result["recovered_stuck"] == 1
        mock_finalize.assert_called_once()
        call_kwargs = mock_finalize.call_args.kwargs
        assert call_kwargs["success"] is True
        assert call_kwargs["completed_tasks"] == 28
        assert call_kwargs["failed_tasks"] == 2

    def test_dry_run_skips_promotion(self) -> None:
        from src.dbos_workflows.import_workflow import promote_candidates_workflow

        batch_job_id = str(uuid4())

        with (
            patch("src.dbos_workflows.import_workflow.recover_and_count_promote_step") as mock_init,
            patch(
                "src.dbos_workflows.import_workflow.process_promotion_batch_step"
            ) as mock_process,
            patch("src.dbos_workflows.import_workflow._finalize_batch_job_sync") as mock_finalize,
            patch("src.dbos_workflows.import_workflow.DBOS") as mock_dbos,
        ):
            mock_dbos.workflow_id = "test-workflow-id"
            mock_init.return_value = {"recovered": 0, "total_candidates": 30}
            mock_finalize.return_value = True

            result = promote_candidates_workflow.__wrapped__(  # type: ignore[attr-defined]
                batch_job_id=batch_job_id,
                batch_size=100,
                dry_run=True,
            )

        assert result["status"] == "completed"
        assert result["dry_run"] is True
        assert result["promoted"] == 0
        mock_process.assert_not_called()

    def test_handles_promote_exception(self) -> None:
        from src.dbos_workflows.import_workflow import promote_candidates_workflow

        batch_job_id = str(uuid4())

        with (
            patch("src.dbos_workflows.import_workflow.recover_and_count_promote_step") as mock_init,
            patch(
                "src.dbos_workflows.import_workflow.process_promotion_batch_step"
            ) as mock_process,
            patch("src.dbos_workflows.import_workflow._finalize_batch_job_sync") as mock_finalize,
            patch("src.dbos_workflows.import_workflow.DBOS") as mock_dbos,
        ):
            mock_dbos.workflow_id = "test-workflow-id"
            mock_init.return_value = {"recovered": 0, "total_candidates": 30}
            mock_process.side_effect = RuntimeError("Database error")
            mock_finalize.return_value = True

            with pytest.raises(RuntimeError, match="Database error"):
                promote_candidates_workflow.__wrapped__(  # type: ignore[attr-defined]
                    batch_job_id=batch_job_id,
                    batch_size=100,
                    dry_run=False,
                )

        mock_finalize.assert_called_once()
        call_kwargs = mock_finalize.call_args.kwargs
        assert call_kwargs["success"] is False
        assert call_kwargs["error_summary"]["stage"] == "promote"


class TestDispatchImportWorkflow:
    @pytest.mark.asyncio
    async def test_dispatches_via_dbos_client(self) -> None:
        from src.dbos_workflows.import_workflow import dispatch_import_workflow

        batch_job_id = uuid4()
        mock_handle = MagicMock()
        mock_handle.workflow_id = "wf-123"
        mock_client = MagicMock()
        mock_client.enqueue.return_value = mock_handle

        mock_to_thread = AsyncMock(return_value=mock_handle)

        with (
            patch(
                "src.dbos_workflows.config.get_dbos_client",
                return_value=mock_client,
            ),
            patch(
                "src.dbos_workflows.import_workflow.asyncio.to_thread",
                mock_to_thread,
            ),
        ):
            result = await dispatch_import_workflow(
                batch_job_id=batch_job_id,
                batch_size=1000,
                dry_run=False,
                enqueue_scrapes=True,
            )

        assert result == "wf-123"
        mock_to_thread.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_none_on_failure(self) -> None:
        from src.dbos_workflows.import_workflow import dispatch_import_workflow

        batch_job_id = uuid4()

        with patch(
            "src.dbos_workflows.config.get_dbos_client",
            side_effect=ConnectionError("DBOS unavailable"),
        ):
            result = await dispatch_import_workflow(
                batch_job_id=batch_job_id,
                batch_size=1000,
                dry_run=False,
                enqueue_scrapes=False,
            )

        assert result is None


class TestDispatchScrapeWorkflow:
    @pytest.mark.asyncio
    async def test_dispatches_via_dbos_client(self) -> None:
        from src.dbos_workflows.import_workflow import dispatch_scrape_workflow

        batch_job_id = uuid4()
        mock_handle = MagicMock()
        mock_handle.workflow_id = "wf-456"
        mock_client = MagicMock()
        mock_client.enqueue.return_value = mock_handle

        mock_to_thread = AsyncMock(return_value=mock_handle)

        with (
            patch(
                "src.dbos_workflows.config.get_dbos_client",
                return_value=mock_client,
            ),
            patch(
                "src.dbos_workflows.import_workflow.asyncio.to_thread",
                mock_to_thread,
            ),
        ):
            result = await dispatch_scrape_workflow(
                batch_job_id=batch_job_id,
                batch_size=500,
                dry_run=False,
                concurrency=5,
                base_delay=2.0,
            )

        assert result == "wf-456"

    @pytest.mark.asyncio
    async def test_returns_none_on_failure(self) -> None:
        from src.dbos_workflows.import_workflow import dispatch_scrape_workflow

        batch_job_id = uuid4()

        with patch(
            "src.dbos_workflows.config.get_dbos_client",
            side_effect=RuntimeError("Connection refused"),
        ):
            result = await dispatch_scrape_workflow(
                batch_job_id=batch_job_id,
                batch_size=500,
                dry_run=False,
            )

        assert result is None


class TestDispatchPromoteWorkflow:
    @pytest.mark.asyncio
    async def test_dispatches_via_dbos_client(self) -> None:
        from src.dbos_workflows.import_workflow import dispatch_promote_workflow

        batch_job_id = uuid4()
        mock_handle = MagicMock()
        mock_handle.workflow_id = "wf-789"
        mock_client = MagicMock()
        mock_client.enqueue.return_value = mock_handle

        mock_to_thread = AsyncMock(return_value=mock_handle)

        with (
            patch(
                "src.dbos_workflows.config.get_dbos_client",
                return_value=mock_client,
            ),
            patch(
                "src.dbos_workflows.import_workflow.asyncio.to_thread",
                mock_to_thread,
            ),
        ):
            result = await dispatch_promote_workflow(
                batch_job_id=batch_job_id,
                batch_size=500,
                dry_run=False,
            )

        assert result == "wf-789"

    @pytest.mark.asyncio
    async def test_returns_none_on_failure(self) -> None:
        from src.dbos_workflows.import_workflow import dispatch_promote_workflow

        batch_job_id = uuid4()

        with patch(
            "src.dbos_workflows.config.get_dbos_client",
            side_effect=TimeoutError("DBOS timeout"),
        ):
            result = await dispatch_promote_workflow(
                batch_job_id=batch_job_id,
                batch_size=500,
                dry_run=False,
            )

        assert result is None


class TestDeprecatedTaskIQStubs:
    @pytest.mark.asyncio
    async def test_import_stub_runs_without_error(self) -> None:
        from src.tasks.import_tasks import process_fact_check_import

        await process_fact_check_import("arg1", key="val")

    @pytest.mark.asyncio
    async def test_scrape_stub_runs_without_error(self) -> None:
        from src.tasks.import_tasks import process_scrape_batch

        await process_scrape_batch("arg1", key="val")

    @pytest.mark.asyncio
    async def test_promote_stub_runs_without_error(self) -> None:
        from src.tasks.import_tasks import process_promotion_batch

        await process_promotion_batch("arg1", key="val")
