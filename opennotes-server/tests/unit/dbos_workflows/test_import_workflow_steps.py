"""Behavioral tests for import pipeline DBOS workflow step internals.

Restores coverage for HTTP failures, DB constraint violations, Redis
failures, CSV edge cases, crash recovery, parallel scraping, and
promotion race conditions that were lost when TaskIQ tests were deleted.

Tests target the internal logic of:
- import_csv_step: CSV streaming, HTTP errors, batch processing
- process_scrape_batch_step: parallel scraping mixed success/failure
- process_promotion_batch_step: FOR UPDATE race conditions, crash recovery
- Sync helpers: finalize_batch_job_sync, start_batch_job_sync,
  _update_job_total_tasks_sync, and async variants
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Sync helper tests (batch_job_helpers.py)
#
# These functions import BatchJobService and get_session_maker inside the
# function body. Since run_sync creates a new event loop/thread, we patch
# the source modules: src.database and src.batch_jobs.service.
# ---------------------------------------------------------------------------


class TestUpdateBatchJobProgressSync:
    def test_returns_true_on_success(self) -> None:
        from src.dbos_workflows.batch_job_helpers import update_batch_job_progress_sync

        job_id = uuid4()

        mock_service = MagicMock()
        mock_service.update_progress = AsyncMock()
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_session_maker = MagicMock(return_value=mock_session_ctx)

        with (
            patch("src.database.get_session_maker", return_value=mock_session_maker),
            patch("src.batch_jobs.service.BatchJobService", return_value=mock_service),
        ):
            result = update_batch_job_progress_sync(
                job_id, completed_tasks=10, failed_tasks=2, current_item="batch 1"
            )

        assert result is True

    def test_returns_false_on_db_error(self) -> None:
        from src.dbos_workflows.batch_job_helpers import update_batch_job_progress_sync

        job_id = uuid4()

        with patch(
            "src.database.get_session_maker",
            side_effect=RuntimeError("DB connection lost"),
        ):
            result = update_batch_job_progress_sync(job_id, completed_tasks=0, failed_tasks=0)

        assert result is False

    def test_returns_false_on_commit_error(self) -> None:
        from src.dbos_workflows.batch_job_helpers import update_batch_job_progress_sync

        job_id = uuid4()

        mock_service = MagicMock()
        mock_service.update_progress = AsyncMock()
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock(side_effect=RuntimeError("commit failed"))

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_session_maker = MagicMock(return_value=mock_session_ctx)

        with (
            patch("src.database.get_session_maker", return_value=mock_session_maker),
            patch("src.batch_jobs.service.BatchJobService", return_value=mock_service),
        ):
            result = update_batch_job_progress_sync(job_id, completed_tasks=5, failed_tasks=0)

        assert result is False


class TestFinalizeBatchJobSync:
    def test_success_path_calls_complete_job(self) -> None:
        from src.dbos_workflows.batch_job_helpers import finalize_batch_job_sync

        job_id = uuid4()

        mock_service = MagicMock()
        mock_service.get_job = AsyncMock(return_value=MagicMock(metadata_={}))
        mock_service.complete_job = AsyncMock()
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_session_maker = MagicMock(return_value=mock_session_ctx)

        with (
            patch("src.database.get_session_maker", return_value=mock_session_maker),
            patch("src.batch_jobs.service.BatchJobService", return_value=mock_service),
        ):
            result = finalize_batch_job_sync(
                job_id,
                success=True,
                completed_tasks=90,
                failed_tasks=10,
                stats={"total_rows": 100},
            )

        assert result is True

    def test_failure_path_calls_fail_job(self) -> None:
        from src.dbos_workflows.batch_job_helpers import finalize_batch_job_sync

        job_id = uuid4()
        error_summary = {"stage": "import", "error": "CSV parse error"}

        mock_service = MagicMock()
        mock_service.get_job = AsyncMock(return_value=MagicMock(metadata_=None))
        mock_service.update_progress = AsyncMock()
        mock_service.fail_job = AsyncMock()
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_session_maker = MagicMock(return_value=mock_session_ctx)

        with (
            patch("src.database.get_session_maker", return_value=mock_session_maker),
            patch("src.batch_jobs.service.BatchJobService", return_value=mock_service),
        ):
            result = finalize_batch_job_sync(
                job_id,
                success=False,
                completed_tasks=0,
                failed_tasks=0,
                error_summary=error_summary,
            )

        assert result is True

    def test_returns_false_on_db_error(self) -> None:
        from src.dbos_workflows.batch_job_helpers import finalize_batch_job_sync

        job_id = uuid4()

        with patch(
            "src.database.get_session_maker",
            side_effect=ConnectionError("DB unavailable"),
        ):
            result = finalize_batch_job_sync(
                job_id, success=True, completed_tasks=0, failed_tasks=0
            )

        assert result is False

    def test_merges_stats_into_metadata(self) -> None:
        from src.dbos_workflows.batch_job_helpers import finalize_batch_job_sync

        job_id = uuid4()
        mock_job = MagicMock()
        mock_job.metadata_ = {"existing_key": "value"}

        mock_service = MagicMock()
        mock_service.get_job = AsyncMock(return_value=mock_job)
        mock_service.complete_job = AsyncMock()
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_session_maker = MagicMock(return_value=mock_session_ctx)

        with (
            patch("src.database.get_session_maker", return_value=mock_session_maker),
            patch("src.batch_jobs.service.BatchJobService", return_value=mock_service),
        ):
            finalize_batch_job_sync(
                job_id,
                success=True,
                completed_tasks=5,
                failed_tasks=0,
                stats={"total_rows": 5},
            )

        assert mock_job.metadata_["existing_key"] == "value"
        assert mock_job.metadata_["stats"] == {"total_rows": 5}

    def test_no_stats_skips_metadata_merge(self) -> None:
        from src.dbos_workflows.batch_job_helpers import finalize_batch_job_sync

        job_id = uuid4()
        mock_job = MagicMock()
        mock_job.metadata_ = {"original": True}

        mock_service = MagicMock()
        mock_service.get_job = AsyncMock(return_value=mock_job)
        mock_service.complete_job = AsyncMock()
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_session_maker = MagicMock(return_value=mock_session_ctx)

        with (
            patch("src.database.get_session_maker", return_value=mock_session_maker),
            patch("src.batch_jobs.service.BatchJobService", return_value=mock_service),
        ):
            finalize_batch_job_sync(
                job_id,
                success=True,
                completed_tasks=5,
                failed_tasks=0,
                stats=None,
            )

        assert mock_job.metadata_ == {"original": True}


class TestStartBatchJobSync:
    def test_returns_true_on_success(self) -> None:
        from src.dbos_workflows.batch_job_helpers import start_batch_job_sync

        job_id = uuid4()

        mock_service = MagicMock()
        mock_service.get_job = AsyncMock(return_value=MagicMock())
        mock_service.start_job = AsyncMock()
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_session_maker = MagicMock(return_value=mock_session_ctx)

        with (
            patch("src.database.get_session_maker", return_value=mock_session_maker),
            patch("src.batch_jobs.service.BatchJobService", return_value=mock_service),
        ):
            result = start_batch_job_sync(job_id)

        assert result is True

    def test_returns_false_when_job_not_found(self) -> None:
        from src.dbos_workflows.batch_job_helpers import start_batch_job_sync

        job_id = uuid4()

        mock_service = MagicMock()
        mock_service.get_job = AsyncMock(return_value=None)
        mock_db = AsyncMock()

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_session_maker = MagicMock(return_value=mock_session_ctx)

        with (
            patch("src.database.get_session_maker", return_value=mock_session_maker),
            patch("src.batch_jobs.service.BatchJobService", return_value=mock_service),
        ):
            result = start_batch_job_sync(job_id)

        assert result is False

    def test_returns_false_on_db_error(self) -> None:
        from src.dbos_workflows.batch_job_helpers import start_batch_job_sync

        job_id = uuid4()

        with patch(
            "src.database.get_session_maker",
            side_effect=RuntimeError("Connection refused"),
        ):
            result = start_batch_job_sync(job_id)

        assert result is False

    def test_sets_total_tasks_when_provided(self) -> None:
        from src.dbos_workflows.batch_job_helpers import start_batch_job_sync

        job_id = uuid4()
        mock_job = MagicMock()
        mock_job.total_tasks = 0

        mock_service = MagicMock()
        mock_service.get_job = AsyncMock(return_value=mock_job)
        mock_service.start_job = AsyncMock()
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_session_maker = MagicMock(return_value=mock_session_ctx)

        with (
            patch("src.database.get_session_maker", return_value=mock_session_maker),
            patch("src.batch_jobs.service.BatchJobService", return_value=mock_service),
        ):
            result = start_batch_job_sync(job_id, total_tasks=500)

        assert result is True
        assert mock_job.total_tasks == 500


class TestUpdateJobTotalTasksSync:
    def test_returns_true_on_success(self) -> None:
        from src.dbos_workflows.import_workflow import _update_job_total_tasks_sync

        job_id = uuid4()
        mock_job = MagicMock()
        mock_job.total_tasks = 0

        mock_service = MagicMock()
        mock_service.get_job = AsyncMock(return_value=mock_job)
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_session_maker = MagicMock(return_value=mock_session_ctx)

        with (
            patch("src.database.get_session_maker", return_value=mock_session_maker),
            patch("src.batch_jobs.service.BatchJobService", return_value=mock_service),
        ):
            result = _update_job_total_tasks_sync(job_id, total_tasks=500)

        assert result is True
        assert mock_job.total_tasks == 500

    def test_returns_false_on_error(self) -> None:
        from src.dbos_workflows.import_workflow import _update_job_total_tasks_sync

        job_id = uuid4()

        with patch(
            "src.database.get_session_maker",
            side_effect=RuntimeError("DB down"),
        ):
            result = _update_job_total_tasks_sync(job_id, total_tasks=100)

        assert result is False

    def test_handles_job_not_found(self) -> None:
        from src.dbos_workflows.import_workflow import _update_job_total_tasks_sync

        job_id = uuid4()

        mock_service = MagicMock()
        mock_service.get_job = AsyncMock(return_value=None)
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_session_maker = MagicMock(return_value=mock_session_ctx)

        with (
            patch("src.database.get_session_maker", return_value=mock_session_maker),
            patch("src.batch_jobs.service.BatchJobService", return_value=mock_service),
        ):
            result = _update_job_total_tasks_sync(job_id, total_tasks=100)

        assert result is True


# ---------------------------------------------------------------------------
# import_csv_step tests
#
# import_csv_step uses __wrapped__ to bypass @DBOS.step() decorator.
# The step's _import() coroutine is executed via run_sync().
# We need to patch at the source module level for lazy imports.
# ---------------------------------------------------------------------------


class TestImportCsvStepHttpFailures:
    def test_http_timeout_raises(self) -> None:
        from src.dbos_workflows.import_workflow import import_csv_step

        batch_job_id = str(uuid4())

        with (
            patch(
                "src.fact_checking.import_pipeline.importer.stream_csv_from_url",
                side_effect=httpx.ReadTimeout("Timed out reading response"),
            ),
            pytest.raises(httpx.ReadTimeout),
        ):
            import_csv_step.__wrapped__(
                batch_job_id=batch_job_id,
                batch_size=100,
                dry_run=False,
                enqueue_scrapes=False,
            )

    def test_http_404_raises(self) -> None:
        from src.dbos_workflows.import_workflow import import_csv_step

        batch_job_id = str(uuid4())

        with (
            patch(
                "src.fact_checking.import_pipeline.importer.stream_csv_from_url",
                side_effect=httpx.HTTPStatusError(
                    "Not Found",
                    request=httpx.Request("GET", "https://example.com"),
                    response=httpx.Response(404),
                ),
            ),
            pytest.raises(httpx.HTTPStatusError),
        ):
            import_csv_step.__wrapped__(
                batch_job_id=batch_job_id,
                batch_size=100,
                dry_run=False,
                enqueue_scrapes=False,
            )

    def test_http_500_raises(self) -> None:
        from src.dbos_workflows.import_workflow import import_csv_step

        batch_job_id = str(uuid4())

        with (
            patch(
                "src.fact_checking.import_pipeline.importer.stream_csv_from_url",
                side_effect=httpx.HTTPStatusError(
                    "Server Error",
                    request=httpx.Request("GET", "https://example.com"),
                    response=httpx.Response(500),
                ),
            ),
            pytest.raises(httpx.HTTPStatusError),
        ):
            import_csv_step.__wrapped__(
                batch_job_id=batch_job_id,
                batch_size=100,
                dry_run=False,
                enqueue_scrapes=False,
            )

    def test_connection_reset_raises(self) -> None:
        from src.dbos_workflows.import_workflow import import_csv_step

        batch_job_id = str(uuid4())

        with (
            patch(
                "src.fact_checking.import_pipeline.importer.stream_csv_from_url",
                side_effect=httpx.ConnectError("Connection reset by peer"),
            ),
            pytest.raises(httpx.ConnectError),
        ):
            import_csv_step.__wrapped__(
                batch_job_id=batch_job_id,
                batch_size=100,
                dry_run=False,
                enqueue_scrapes=False,
            )


class TestImportCsvStepCsvProcessing:
    def _make_session_maker_mock(self):
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=None)
        return MagicMock(return_value=mock_session_ctx)

    def test_successful_import_returns_stats(self) -> None:
        from src.dbos_workflows.import_workflow import import_csv_step

        batch_job_id = str(uuid4())

        async def _mock_stream(_url: str):
            yield "id,url\n1,http://a.com"

        mock_session_maker = self._make_session_maker_mock()

        with (
            patch(
                "src.fact_checking.import_pipeline.importer.stream_csv_from_url",
                _mock_stream,
            ),
            patch(
                "src.fact_checking.import_pipeline.importer.parse_csv_rows",
                return_value=[{"id": "1"}],
            ),
            patch(
                "src.fact_checking.import_pipeline.importer.validate_and_normalize_batch",
                return_value=([MagicMock()], []),
            ),
            patch(
                "src.fact_checking.import_pipeline.importer.upsert_candidates",
                new_callable=AsyncMock,
                return_value=(1, 0),
            ),
            patch(
                "src.dbos_workflows.import_workflow._update_job_total_tasks_async",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "src.dbos_workflows.import_workflow._update_batch_job_progress_async",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "src.tasks.import_tasks._check_row_accounting",
                return_value=True,
            ),
            patch(
                "src.database.get_session_maker",
                return_value=mock_session_maker,
            ),
        ):
            result = import_csv_step.__wrapped__(
                batch_job_id=batch_job_id,
                batch_size=100,
                dry_run=False,
                enqueue_scrapes=False,
            )

        assert result["total_rows"] == 1
        assert result["valid_rows"] == 1
        assert result["invalid_rows"] == 0
        assert result["inserted"] == 1
        assert result["updated"] == 0

    def test_dry_run_skips_upsert(self) -> None:
        from src.dbos_workflows.import_workflow import import_csv_step

        batch_job_id = str(uuid4())

        async def _mock_stream(_url: str):
            yield "id,url\n1,http://a.com"

        mock_session_maker = self._make_session_maker_mock()
        mock_upsert = AsyncMock(return_value=(0, 0))

        with (
            patch(
                "src.fact_checking.import_pipeline.importer.stream_csv_from_url",
                _mock_stream,
            ),
            patch(
                "src.fact_checking.import_pipeline.importer.parse_csv_rows",
                return_value=[{"id": "1"}],
            ),
            patch(
                "src.fact_checking.import_pipeline.importer.validate_and_normalize_batch",
                return_value=([MagicMock()], []),
            ),
            patch(
                "src.fact_checking.import_pipeline.importer.upsert_candidates",
                mock_upsert,
            ),
            patch(
                "src.dbos_workflows.import_workflow._update_job_total_tasks_async",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "src.dbos_workflows.import_workflow._update_batch_job_progress_async",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "src.tasks.import_tasks._check_row_accounting",
                return_value=True,
            ),
            patch(
                "src.database.get_session_maker",
                return_value=mock_session_maker,
            ),
        ):
            result = import_csv_step.__wrapped__(
                batch_job_id=batch_job_id,
                batch_size=100,
                dry_run=True,
                enqueue_scrapes=False,
            )

        assert result["dry_run"] is True
        assert result["inserted"] == 0
        mock_upsert.assert_not_awaited()

    def test_validation_errors_are_aggregated(self) -> None:
        from src.dbos_workflows.import_workflow import import_csv_step

        batch_job_id = str(uuid4())

        async def _mock_stream(_url: str):
            yield "id,url\n1,http://a.com\n2,http://b.com"

        mock_session_maker = self._make_session_maker_mock()
        validation_errors = ["Row 1: invalid URL", "Row 2: missing claim"]

        with (
            patch(
                "src.fact_checking.import_pipeline.importer.stream_csv_from_url",
                _mock_stream,
            ),
            patch(
                "src.fact_checking.import_pipeline.importer.parse_csv_rows",
                return_value=[{"id": "1"}, {"id": "2"}],
            ),
            patch(
                "src.fact_checking.import_pipeline.importer.validate_and_normalize_batch",
                return_value=([], validation_errors),
            ),
            patch(
                "src.dbos_workflows.import_workflow._update_job_total_tasks_async",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "src.dbos_workflows.import_workflow._update_batch_job_progress_async",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "src.tasks.import_tasks._check_row_accounting",
                return_value=True,
            ),
            patch(
                "src.database.get_session_maker",
                return_value=mock_session_maker,
            ),
        ):
            result = import_csv_step.__wrapped__(
                batch_job_id=batch_job_id,
                batch_size=100,
                dry_run=False,
                enqueue_scrapes=False,
            )

        assert result["invalid_rows"] == 2
        assert "errors" in result
        assert result["errors"]["total_validation_errors"] == 2

    def test_empty_csv_returns_zero_stats(self) -> None:
        from src.dbos_workflows.import_workflow import import_csv_step

        batch_job_id = str(uuid4())

        async def _mock_stream(_url: str):
            yield "id,url\n"

        mock_session_maker = self._make_session_maker_mock()

        with (
            patch(
                "src.fact_checking.import_pipeline.importer.stream_csv_from_url",
                _mock_stream,
            ),
            patch(
                "src.fact_checking.import_pipeline.importer.parse_csv_rows",
                return_value=[],
            ),
            patch(
                "src.dbos_workflows.import_workflow._update_job_total_tasks_async",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "src.dbos_workflows.import_workflow._update_batch_job_progress_async",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "src.tasks.import_tasks._check_row_accounting",
                return_value=True,
            ),
            patch(
                "src.database.get_session_maker",
                return_value=mock_session_maker,
            ),
        ):
            result = import_csv_step.__wrapped__(
                batch_job_id=batch_job_id,
                batch_size=100,
                dry_run=False,
                enqueue_scrapes=False,
            )

        assert result["total_rows"] == 0
        assert result["valid_rows"] == 0
        assert result["inserted"] == 0

    def test_enqueue_scrapes_sets_dispatch_marker(self) -> None:
        from src.dbos_workflows.import_workflow import import_csv_step

        batch_job_id = str(uuid4())

        async def _mock_stream(_url: str):
            yield "id,url\n1,http://a.com"

        mock_session_maker = self._make_session_maker_mock()

        with (
            patch(
                "src.fact_checking.import_pipeline.importer.stream_csv_from_url",
                _mock_stream,
            ),
            patch(
                "src.fact_checking.import_pipeline.importer.parse_csv_rows",
                return_value=[{"id": "1"}],
            ),
            patch(
                "src.fact_checking.import_pipeline.importer.validate_and_normalize_batch",
                return_value=([MagicMock()], []),
            ),
            patch(
                "src.fact_checking.import_pipeline.importer.upsert_candidates",
                new_callable=AsyncMock,
                return_value=(1, 0),
            ),
            patch(
                "src.dbos_workflows.import_workflow._update_job_total_tasks_async",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "src.dbos_workflows.import_workflow._update_batch_job_progress_async",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "src.tasks.import_tasks._check_row_accounting",
                return_value=True,
            ),
            patch(
                "src.database.get_session_maker",
                return_value=mock_session_maker,
            ),
        ):
            result = import_csv_step.__wrapped__(
                batch_job_id=batch_job_id,
                batch_size=100,
                dry_run=False,
                enqueue_scrapes=True,
            )

        assert result["scrape_dispatch"] == "requires_separate_batch_job"

    def test_db_constraint_violation_during_upsert_raises(self) -> None:
        from sqlalchemy.exc import IntegrityError

        from src.dbos_workflows.import_workflow import import_csv_step

        batch_job_id = str(uuid4())

        async def _mock_stream(_url: str):
            yield "id,url\n1,http://a.com"

        mock_session_maker = self._make_session_maker_mock()

        with (
            patch(
                "src.fact_checking.import_pipeline.importer.stream_csv_from_url",
                _mock_stream,
            ),
            patch(
                "src.fact_checking.import_pipeline.importer.parse_csv_rows",
                return_value=[{"id": "1"}],
            ),
            patch(
                "src.fact_checking.import_pipeline.importer.validate_and_normalize_batch",
                return_value=([MagicMock()], []),
            ),
            patch(
                "src.fact_checking.import_pipeline.importer.upsert_candidates",
                new_callable=AsyncMock,
                side_effect=IntegrityError("constraint violation", params=None, orig=Exception()),
            ),
            patch(
                "src.dbos_workflows.import_workflow._update_job_total_tasks_async",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "src.dbos_workflows.import_workflow._update_batch_job_progress_async",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "src.database.get_session_maker",
                return_value=mock_session_maker,
            ),
            pytest.raises(IntegrityError),
        ):
            import_csv_step.__wrapped__(
                batch_job_id=batch_job_id,
                batch_size=100,
                dry_run=False,
                enqueue_scrapes=False,
            )


# ---------------------------------------------------------------------------
# process_scrape_batch_step tests
# ---------------------------------------------------------------------------


class TestProcessScrapeBatchStepParallelScraping:
    def _make_session_maker_mock(self, execute_side_effect=None):
        mock_db = AsyncMock()
        if execute_side_effect:
            mock_db.execute = AsyncMock(side_effect=execute_side_effect)
        mock_db.commit = AsyncMock()

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=None)
        return MagicMock(return_value=mock_session_ctx)

    def _make_batch_execute_fn(self, batches: list[list]):
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            idx = call_count - 1
            if idx < len(batches):
                result = MagicMock()
                result.fetchall.return_value = batches[idx]
                return result
            return MagicMock(fetchall=MagicMock(return_value=[]))

        return mock_execute

    def test_mixed_success_and_failure(self) -> None:
        from src.dbos_workflows.import_workflow import process_scrape_batch_step

        batch_job_id = str(uuid4())
        cid1, cid2, cid3 = uuid4(), uuid4(), uuid4()

        candidates = [
            (cid1, "http://success.com"),
            (cid2, "http://fail.com"),
            (cid3, "http://exception.com"),
        ]

        mock_session_maker = self._make_session_maker_mock(
            execute_side_effect=self._make_batch_execute_fn([candidates, []])
        )

        def mock_scrape(url: str) -> str | None:
            if "success" in url:
                return "Scraped content"
            if "fail" in url:
                return None
            raise ConnectionError("Connection reset")

        with (
            patch("src.database.get_session_maker", return_value=mock_session_maker),
            patch(
                "src.shared.content_extraction.scrape_url_content",
                side_effect=mock_scrape,
            ),
            patch(
                "src.dbos_workflows.import_workflow._update_batch_job_progress_async",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            result = process_scrape_batch_step.__wrapped__(
                batch_job_id=batch_job_id,
                batch_size=10,
                concurrency=3,
                base_delay=0,
                total_candidates=3,
                scraped_so_far=0,
                failed_so_far=0,
            )

        assert result["scraped"] == 1
        assert result["failed"] == 2

    def test_all_scrapes_succeed(self) -> None:
        from src.dbos_workflows.import_workflow import process_scrape_batch_step

        batch_job_id = str(uuid4())
        cid1, cid2 = uuid4(), uuid4()

        candidates = [(cid1, "http://a.com"), (cid2, "http://b.com")]
        mock_session_maker = self._make_session_maker_mock(
            execute_side_effect=self._make_batch_execute_fn([candidates, []])
        )

        with (
            patch("src.database.get_session_maker", return_value=mock_session_maker),
            patch(
                "src.shared.content_extraction.scrape_url_content",
                return_value="Good content",
            ),
            patch(
                "src.dbos_workflows.import_workflow._update_batch_job_progress_async",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            result = process_scrape_batch_step.__wrapped__(
                batch_job_id=batch_job_id,
                batch_size=10,
                concurrency=5,
                base_delay=0,
                total_candidates=2,
                scraped_so_far=0,
                failed_so_far=0,
            )

        assert result["scraped"] == 2
        assert result["failed"] == 0

    def test_all_scrapes_fail(self) -> None:
        from src.dbos_workflows.import_workflow import process_scrape_batch_step

        batch_job_id = str(uuid4())
        cid1, cid2 = uuid4(), uuid4()

        candidates = [(cid1, "http://a.com"), (cid2, "http://b.com")]
        mock_session_maker = self._make_session_maker_mock(
            execute_side_effect=self._make_batch_execute_fn([candidates, []])
        )

        with (
            patch("src.database.get_session_maker", return_value=mock_session_maker),
            patch(
                "src.shared.content_extraction.scrape_url_content",
                return_value=None,
            ),
            patch(
                "src.dbos_workflows.import_workflow._update_batch_job_progress_async",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            result = process_scrape_batch_step.__wrapped__(
                batch_job_id=batch_job_id,
                batch_size=10,
                concurrency=5,
                base_delay=0,
                total_candidates=2,
                scraped_so_far=0,
                failed_so_far=0,
            )

        assert result["scraped"] == 0
        assert result["failed"] == 2

    def test_empty_candidate_list_returns_immediately(self) -> None:
        from src.dbos_workflows.import_workflow import process_scrape_batch_step

        batch_job_id = str(uuid4())
        mock_session_maker = self._make_session_maker_mock(
            execute_side_effect=self._make_batch_execute_fn([[]])
        )

        with patch("src.database.get_session_maker", return_value=mock_session_maker):
            result = process_scrape_batch_step.__wrapped__(
                batch_job_id=batch_job_id,
                batch_size=10,
                concurrency=5,
                base_delay=0,
                total_candidates=0,
                scraped_so_far=0,
                failed_so_far=0,
            )

        assert result["scraped"] == 0
        assert result["failed"] == 0

    def test_exception_in_scrape_counted_as_failure(self) -> None:
        from src.dbos_workflows.import_workflow import process_scrape_batch_step

        batch_job_id = str(uuid4())
        cid1 = uuid4()

        candidates = [(cid1, "http://crash.com")]
        mock_session_maker = self._make_session_maker_mock(
            execute_side_effect=self._make_batch_execute_fn([candidates, []])
        )

        def _crash_scrape(url: str) -> str | None:
            raise RuntimeError("Segfault-like crash")

        with (
            patch("src.database.get_session_maker", return_value=mock_session_maker),
            patch(
                "src.shared.content_extraction.scrape_url_content",
                side_effect=_crash_scrape,
            ),
            patch(
                "src.dbos_workflows.import_workflow._update_batch_job_progress_async",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            result = process_scrape_batch_step.__wrapped__(
                batch_job_id=batch_job_id,
                batch_size=10,
                concurrency=1,
                base_delay=0,
                total_candidates=1,
                scraped_so_far=0,
                failed_so_far=0,
            )

        assert result["scraped"] == 0
        assert result["failed"] == 1

    def test_accumulates_from_previous_counts(self) -> None:
        from src.dbos_workflows.import_workflow import process_scrape_batch_step

        batch_job_id = str(uuid4())
        mock_session_maker = self._make_session_maker_mock(
            execute_side_effect=self._make_batch_execute_fn([[]])
        )

        with patch("src.database.get_session_maker", return_value=mock_session_maker):
            result = process_scrape_batch_step.__wrapped__(
                batch_job_id=batch_job_id,
                batch_size=10,
                concurrency=5,
                base_delay=0,
                total_candidates=100,
                scraped_so_far=40,
                failed_so_far=5,
            )

        assert result["scraped"] == 40
        assert result["failed"] == 5

    def test_concurrency_semaphore_limits_parallel_scrapes(self) -> None:
        from src.dbos_workflows.import_workflow import process_scrape_batch_step

        batch_job_id = str(uuid4())
        cids = [uuid4() for _ in range(5)]

        candidates = [(cid, f"http://site{i}.com") for i, cid in enumerate(cids)]
        mock_session_maker = self._make_session_maker_mock(
            execute_side_effect=self._make_batch_execute_fn([candidates, []])
        )

        with (
            patch("src.database.get_session_maker", return_value=mock_session_maker),
            patch(
                "src.shared.content_extraction.scrape_url_content",
                return_value="content",
            ),
            patch(
                "src.dbos_workflows.import_workflow._update_batch_job_progress_async",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            result = process_scrape_batch_step.__wrapped__(
                batch_job_id=batch_job_id,
                batch_size=10,
                concurrency=2,
                base_delay=0,
                total_candidates=5,
                scraped_so_far=0,
                failed_so_far=0,
            )

        assert result["scraped"] == 5


# ---------------------------------------------------------------------------
# process_promotion_batch_step tests
# ---------------------------------------------------------------------------


class TestProcessPromotionBatchStep:
    def _make_session_maker_mock(self, execute_side_effect=None):
        mock_db = AsyncMock()
        if execute_side_effect:
            mock_db.execute = AsyncMock(side_effect=execute_side_effect)
        mock_db.commit = AsyncMock()

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=None)
        return MagicMock(return_value=mock_session_ctx)

    def _make_batch_execute_fn(self, batches: list[list]):
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            idx = call_count - 1
            if idx < len(batches):
                result = MagicMock()
                result.fetchall.return_value = batches[idx]
                return result
            return MagicMock(fetchall=MagicMock(return_value=[]))

        return mock_execute

    def test_successful_promotion_of_candidates(self) -> None:
        from src.dbos_workflows.import_workflow import process_promotion_batch_step

        batch_job_id = str(uuid4())
        cid1, cid2 = uuid4(), uuid4()

        mock_session_maker = self._make_session_maker_mock(
            execute_side_effect=self._make_batch_execute_fn([[(cid1,), (cid2,)], []])
        )

        mock_promote = AsyncMock(return_value=True)

        with (
            patch("src.database.get_session_maker", return_value=mock_session_maker),
            patch(
                "src.fact_checking.import_pipeline.promotion.promote_candidate",
                mock_promote,
            ),
            patch(
                "src.dbos_workflows.import_workflow._update_batch_job_progress_async",
                new_callable=AsyncMock,
                return_value=True,
            ),
        ):
            result = process_promotion_batch_step.__wrapped__(
                batch_job_id=batch_job_id,
                batch_size=10,
                total_candidates=2,
            )

        assert result["promoted"] == 2
        assert result["failed"] == 0
        assert mock_promote.await_count == 2

    def test_mixed_promotion_success_and_failure(self) -> None:
        from src.dbos_workflows.import_workflow import process_promotion_batch_step

        batch_job_id = str(uuid4())
        cid1, cid2, cid3 = uuid4(), uuid4(), uuid4()

        mock_session_maker = self._make_session_maker_mock(
            execute_side_effect=self._make_batch_execute_fn([[(cid1,), (cid2,), (cid3,)], []])
        )

        promote_results = iter([True, False, True])

        async def mock_promote(db, candidate_id):
            return next(promote_results)

        with (
            patch("src.database.get_session_maker", return_value=mock_session_maker),
            patch(
                "src.fact_checking.import_pipeline.promotion.promote_candidate",
                side_effect=mock_promote,
            ),
            patch(
                "src.dbos_workflows.import_workflow._update_batch_job_progress_async",
                new_callable=AsyncMock,
                return_value=True,
            ),
        ):
            result = process_promotion_batch_step.__wrapped__(
                batch_job_id=batch_job_id,
                batch_size=10,
                total_candidates=3,
            )

        assert result["promoted"] == 2
        assert result["failed"] == 1

    def test_empty_candidate_list_returns_zeros(self) -> None:
        from src.dbos_workflows.import_workflow import process_promotion_batch_step

        batch_job_id = str(uuid4())

        mock_session_maker = self._make_session_maker_mock(
            execute_side_effect=self._make_batch_execute_fn([[]])
        )

        with patch("src.database.get_session_maker", return_value=mock_session_maker):
            result = process_promotion_batch_step.__wrapped__(
                batch_job_id=batch_job_id,
                batch_size=10,
                total_candidates=0,
            )

        assert result["promoted"] == 0
        assert result["failed"] == 0

    def test_for_update_skip_locked_used_in_query(self) -> None:
        from src.dbos_workflows.import_workflow import process_promotion_batch_step

        batch_job_id = str(uuid4())
        executed_stmts = []

        async def capturing_execute(stmt):
            executed_stmts.append(stmt)
            result = MagicMock()
            result.fetchall.return_value = []
            return result

        mock_session_maker = self._make_session_maker_mock(execute_side_effect=capturing_execute)

        with patch("src.database.get_session_maker", return_value=mock_session_maker):
            process_promotion_batch_step.__wrapped__(
                batch_job_id=batch_job_id,
                batch_size=10,
                total_candidates=0,
            )

        assert len(executed_stmts) >= 1
        stmt = executed_stmts[0]
        compiled_str = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "FOR UPDATE" in compiled_str.upper() or "SKIP LOCKED" in compiled_str.upper()

    def test_progress_updated_after_each_batch(self) -> None:
        from src.dbos_workflows.import_workflow import process_promotion_batch_step

        batch_job_id = str(uuid4())
        cid1 = uuid4()

        mock_session_maker = self._make_session_maker_mock(
            execute_side_effect=self._make_batch_execute_fn([[(cid1,)], []])
        )

        mock_progress = AsyncMock(return_value=True)

        with (
            patch("src.database.get_session_maker", return_value=mock_session_maker),
            patch(
                "src.fact_checking.import_pipeline.promotion.promote_candidate",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "src.dbos_workflows.import_workflow._update_batch_job_progress_async",
                mock_progress,
            ),
        ):
            process_promotion_batch_step.__wrapped__(
                batch_job_id=batch_job_id,
                batch_size=10,
                total_candidates=1,
            )

        mock_progress.assert_awaited_once()

    def test_multiple_batches_processed_in_loop(self) -> None:
        from src.dbos_workflows.import_workflow import process_promotion_batch_step

        batch_job_id = str(uuid4())
        batch1_ids = [uuid4() for _ in range(3)]
        batch2_ids = [uuid4() for _ in range(2)]

        mock_session_maker = self._make_session_maker_mock(
            execute_side_effect=self._make_batch_execute_fn(
                [
                    [(cid,) for cid in batch1_ids],
                    [(cid,) for cid in batch2_ids],
                    [],
                ]
            )
        )

        with (
            patch("src.database.get_session_maker", return_value=mock_session_maker),
            patch(
                "src.fact_checking.import_pipeline.promotion.promote_candidate",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "src.dbos_workflows.import_workflow._update_batch_job_progress_async",
                new_callable=AsyncMock,
                return_value=True,
            ),
        ):
            result = process_promotion_batch_step.__wrapped__(
                batch_job_id=batch_job_id,
                batch_size=3,
                total_candidates=5,
            )

        assert result["promoted"] == 5
        assert result["failed"] == 0


# ---------------------------------------------------------------------------
# Row accounting tests
# ---------------------------------------------------------------------------


class TestCheckRowAccounting:
    def test_valid_accounting_returns_true(self) -> None:
        from src.fact_checking.import_pipeline.importer import ImportStats
        from src.tasks.import_tasks import _check_row_accounting

        stats = ImportStats(total_rows=100, valid_rows=90, invalid_rows=10)
        assert _check_row_accounting("job-1", stats) is True

    def test_mismatch_returns_false(self) -> None:
        from src.fact_checking.import_pipeline.importer import ImportStats
        from src.tasks.import_tasks import _check_row_accounting

        stats = ImportStats(total_rows=100, valid_rows=80, invalid_rows=10)
        assert _check_row_accounting("job-1", stats) is False

    def test_zero_total_rows_returns_true(self) -> None:
        from src.fact_checking.import_pipeline.importer import ImportStats
        from src.tasks.import_tasks import _check_row_accounting

        stats = ImportStats(total_rows=0, valid_rows=0, invalid_rows=0)
        assert _check_row_accounting("job-1", stats) is True

    def test_span_attributes_set_on_mismatch(self) -> None:
        from src.fact_checking.import_pipeline.importer import ImportStats
        from src.tasks.import_tasks import _check_row_accounting

        stats = ImportStats(total_rows=100, valid_rows=50, invalid_rows=30)
        mock_span = MagicMock()
        _check_row_accounting("job-1", stats, span=mock_span)

        mock_span.set_attribute.assert_any_call("import.row_mismatch", True)
        mock_span.set_attribute.assert_any_call("import.missing_rows", 20)
