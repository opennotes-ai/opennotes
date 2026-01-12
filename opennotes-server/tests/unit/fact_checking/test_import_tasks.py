"""
Unit tests for TaskIQ import tasks using BatchJob infrastructure.

Task: task-986.07 - Fix error handling and add tests for import_tasks.py

Tests cover:
- Helper function behavior (_update_job_total_tasks, _start_job, _update_progress, etc.)
- Stream/HTTP failure scenarios
- Batch validation failures
- Database and Redis failure scenarios
- End-to-end task flow
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest


class TestHelperFunctions:
    """Test helper functions for job state management."""

    @pytest.mark.asyncio
    async def test_update_job_total_tasks_success(self):
        """Successfully updates total_tasks on a BatchJob."""
        from src.tasks.import_tasks import _update_job_total_tasks

        job_id = uuid4()
        total_tasks = 1000

        mock_job = MagicMock()
        mock_job.total_tasks = 0

        mock_service = MagicMock()
        mock_service.get_job = AsyncMock(return_value=mock_job)

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()

        mock_session_maker = MagicMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch("src.tasks.import_tasks.BatchJobService", return_value=mock_service):
            await _update_job_total_tasks(mock_session_maker, job_id, total_tasks)

        mock_service.get_job.assert_called_once_with(job_id)
        assert mock_job.total_tasks == total_tasks
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_job_total_tasks_job_not_found_logs_error(self):
        """Logs error when job not found but does not raise."""
        from src.tasks.import_tasks import _update_job_total_tasks

        job_id = uuid4()

        mock_service = MagicMock()
        mock_service.get_job = AsyncMock(return_value=None)

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()

        mock_session_maker = MagicMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch("src.tasks.import_tasks.BatchJobService", return_value=mock_service):
            await _update_job_total_tasks(mock_session_maker, job_id, 100)

    @pytest.mark.asyncio
    async def test_update_job_total_tasks_db_failure_logs_error(self):
        """Logs error on database failure but does not raise."""
        from src.tasks.import_tasks import _update_job_total_tasks

        job_id = uuid4()

        mock_session_maker = MagicMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(
            side_effect=Exception("Database connection lost")
        )
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

        await _update_job_total_tasks(mock_session_maker, job_id, 100)

    @pytest.mark.asyncio
    async def test_start_job_success(self):
        """Successfully transitions job from PENDING to IN_PROGRESS."""
        from src.tasks.import_tasks import _start_job

        job_id = uuid4()

        mock_service = MagicMock()
        mock_service.start_job = AsyncMock()

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()

        mock_session_maker = MagicMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_progress_tracker = MagicMock()

        with patch("src.tasks.import_tasks.BatchJobService", return_value=mock_service):
            await _start_job(mock_session_maker, mock_progress_tracker, job_id)

        mock_service.start_job.assert_called_once_with(job_id)
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_job_db_failure_raises(self):
        """Database failure during start_job raises exception."""
        from src.tasks.import_tasks import _start_job

        job_id = uuid4()

        mock_service = MagicMock()
        mock_service.start_job = AsyncMock(side_effect=Exception("DB failure"))

        mock_db = AsyncMock()

        mock_session_maker = MagicMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_progress_tracker = MagicMock()

        with (
            patch("src.tasks.import_tasks.BatchJobService", return_value=mock_service),
            pytest.raises(Exception, match="DB failure"),
        ):
            await _start_job(mock_session_maker, mock_progress_tracker, job_id)

    @pytest.mark.asyncio
    async def test_update_progress_success(self):
        """Successfully updates job progress."""
        from src.tasks.import_tasks import _update_progress

        job_id = uuid4()

        mock_service = MagicMock()
        mock_service.update_progress = AsyncMock()

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()

        mock_session_maker = MagicMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_progress_tracker = MagicMock()

        with patch("src.tasks.import_tasks.BatchJobService", return_value=mock_service):
            await _update_progress(
                mock_session_maker,
                mock_progress_tracker,
                job_id,
                completed_tasks=50,
                failed_tasks=5,
                current_item="Batch 1 (100/1000)",
            )

        mock_service.update_progress.assert_called_once_with(
            job_id,
            completed_tasks=50,
            failed_tasks=5,
            current_item="Batch 1 (100/1000)",
        )
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_complete_job_success(self):
        """Successfully completes job with final stats."""
        from src.tasks.import_tasks import _complete_job

        job_id = uuid4()

        mock_job = MagicMock()
        mock_job.metadata_ = {"existing": "data"}

        mock_service = MagicMock()
        mock_service.get_job = AsyncMock(return_value=mock_job)
        mock_service.complete_job = AsyncMock()

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()

        mock_session_maker = MagicMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_progress_tracker = MagicMock()

        stats = {"total_rows": 1000, "valid_rows": 950}

        with patch("src.tasks.import_tasks.BatchJobService", return_value=mock_service):
            await _complete_job(
                mock_session_maker,
                mock_progress_tracker,
                job_id,
                completed_tasks=950,
                failed_tasks=50,
                stats=stats,
            )

        assert mock_job.metadata_["stats"] == stats
        assert mock_job.metadata_["existing"] == "data"
        mock_service.complete_job.assert_called_once_with(job_id, 950, 50)

    @pytest.mark.asyncio
    async def test_fail_job_success(self):
        """Successfully marks job as failed with error summary."""
        from src.tasks.import_tasks import _fail_job

        job_id = uuid4()

        mock_service = MagicMock()
        mock_service.fail_job = AsyncMock()

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()

        mock_session_maker = MagicMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_progress_tracker = MagicMock()

        error_summary = {"exception": "Test error", "exception_type": "ValueError"}

        with patch("src.tasks.import_tasks.BatchJobService", return_value=mock_service):
            await _fail_job(
                mock_session_maker,
                mock_progress_tracker,
                job_id,
                error_summary=error_summary,
                completed_tasks=100,
                failed_tasks=10,
            )

        mock_service.fail_job.assert_called_once_with(job_id, error_summary, 100, 10)


class TestAggregateErrors:
    """Test error aggregation helper."""

    def test_aggregate_errors_under_max_limit(self):
        """Errors under max limit are all included."""
        from src.tasks.import_tasks import _aggregate_errors

        errors = [f"Error {i}" for i in range(10)]
        result = _aggregate_errors(errors, max_errors=50)

        assert len(result["validation_errors"]) == 10
        assert result["total_validation_errors"] == 10
        assert result["truncated"] is False

    def test_aggregate_errors_truncates_at_max(self):
        """Errors exceeding max limit are truncated."""
        from src.tasks.import_tasks import _aggregate_errors

        errors = [f"Error {i}" for i in range(100)]
        result = _aggregate_errors(errors, max_errors=50)

        assert len(result["validation_errors"]) == 50
        assert result["total_validation_errors"] == 100
        assert result["truncated"] is True

    def test_aggregate_errors_empty_list(self):
        """Empty error list produces valid result."""
        from src.tasks.import_tasks import _aggregate_errors

        result = _aggregate_errors([])

        assert result["validation_errors"] == []
        assert result["total_validation_errors"] == 0
        assert result["truncated"] is False


class TestStreamHttpFailures:
    """Test HTTP/stream failure scenarios."""

    @pytest.mark.asyncio
    async def test_http_timeout_fails_job(self):
        """HTTP timeout causes job failure."""
        job_id = str(uuid4())

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()

        mock_session_maker = MagicMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_redis = AsyncMock()
        mock_redis.connect = AsyncMock()
        mock_redis.disconnect = AsyncMock()

        mock_progress_tracker = MagicMock()

        mock_batch_job_service = MagicMock()
        mock_batch_job_service.start_job = AsyncMock()
        mock_batch_job_service.fail_job = AsyncMock()

        async def timeout_error(*args, **kwargs):
            raise httpx.TimeoutException("Connection timed out")
            yield  # pragma: no cover - makes this an async generator

        with (
            patch("src.tasks.import_tasks.create_async_engine") as mock_engine,
            patch("src.tasks.import_tasks.async_sessionmaker", return_value=mock_session_maker),
            patch("src.tasks.import_tasks.RedisClient", return_value=mock_redis),
            patch(
                "src.tasks.import_tasks.BatchJobProgressTracker",
                return_value=mock_progress_tracker,
            ),
            patch("src.tasks.import_tasks.BatchJobService", return_value=mock_batch_job_service),
            patch("src.tasks.import_tasks.stream_csv_from_url", timeout_error),
            patch("src.tasks.import_tasks.get_settings") as mock_settings,
        ):
            mock_engine.return_value = MagicMock()
            mock_engine.return_value.dispose = AsyncMock()
            settings = MagicMock()
            settings.DB_POOL_SIZE = 5
            settings.DB_POOL_MAX_OVERFLOW = 10
            settings.DB_POOL_TIMEOUT = 30
            settings.DB_POOL_RECYCLE = 1800
            mock_settings.return_value = settings

            from src.tasks.import_tasks import process_fact_check_import

            with pytest.raises(httpx.TimeoutException):
                await process_fact_check_import(
                    job_id=job_id,
                    batch_size=100,
                    dry_run=False,
                    enqueue_scrapes=False,
                    db_url="postgresql+asyncpg://test:test@localhost/test",
                    redis_url="redis://localhost:6379",
                )

            mock_batch_job_service.fail_job.assert_called_once()

    @pytest.mark.asyncio
    async def test_http_404_error_fails_job(self):
        """HTTP 404 error causes job failure."""
        job_id = str(uuid4())

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()

        mock_session_maker = MagicMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_redis = AsyncMock()
        mock_redis.connect = AsyncMock()
        mock_redis.disconnect = AsyncMock()

        mock_progress_tracker = MagicMock()

        mock_batch_job_service = MagicMock()
        mock_batch_job_service.start_job = AsyncMock()
        mock_batch_job_service.fail_job = AsyncMock()

        async def http_404_error(*args, **kwargs):
            response = MagicMock()
            response.status_code = 404
            request = MagicMock()
            raise httpx.HTTPStatusError("Not Found", request=request, response=response)
            yield  # pragma: no cover - makes this an async generator

        with (
            patch("src.tasks.import_tasks.create_async_engine") as mock_engine,
            patch("src.tasks.import_tasks.async_sessionmaker", return_value=mock_session_maker),
            patch("src.tasks.import_tasks.RedisClient", return_value=mock_redis),
            patch(
                "src.tasks.import_tasks.BatchJobProgressTracker",
                return_value=mock_progress_tracker,
            ),
            patch("src.tasks.import_tasks.BatchJobService", return_value=mock_batch_job_service),
            patch("src.tasks.import_tasks.stream_csv_from_url", http_404_error),
            patch("src.tasks.import_tasks.get_settings") as mock_settings,
        ):
            mock_engine.return_value = MagicMock()
            mock_engine.return_value.dispose = AsyncMock()
            settings = MagicMock()
            settings.DB_POOL_SIZE = 5
            settings.DB_POOL_MAX_OVERFLOW = 10
            settings.DB_POOL_TIMEOUT = 30
            settings.DB_POOL_RECYCLE = 1800
            mock_settings.return_value = settings

            from src.tasks.import_tasks import process_fact_check_import

            with pytest.raises(httpx.HTTPStatusError):
                await process_fact_check_import(
                    job_id=job_id,
                    batch_size=100,
                    dry_run=False,
                    enqueue_scrapes=False,
                    db_url="postgresql+asyncpg://test:test@localhost/test",
                    redis_url="redis://localhost:6379",
                )

            mock_batch_job_service.fail_job.assert_called_once()

    @pytest.mark.asyncio
    async def test_http_500_error_fails_job(self):
        """HTTP 500 error causes job failure."""
        job_id = str(uuid4())

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()

        mock_session_maker = MagicMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_redis = AsyncMock()
        mock_redis.connect = AsyncMock()
        mock_redis.disconnect = AsyncMock()

        mock_progress_tracker = MagicMock()

        mock_batch_job_service = MagicMock()
        mock_batch_job_service.start_job = AsyncMock()
        mock_batch_job_service.fail_job = AsyncMock()

        async def http_500_error(*args, **kwargs):
            response = MagicMock()
            response.status_code = 500
            request = MagicMock()
            raise httpx.HTTPStatusError("Internal Server Error", request=request, response=response)
            yield  # pragma: no cover - makes this an async generator

        with (
            patch("src.tasks.import_tasks.create_async_engine") as mock_engine,
            patch("src.tasks.import_tasks.async_sessionmaker", return_value=mock_session_maker),
            patch("src.tasks.import_tasks.RedisClient", return_value=mock_redis),
            patch(
                "src.tasks.import_tasks.BatchJobProgressTracker",
                return_value=mock_progress_tracker,
            ),
            patch("src.tasks.import_tasks.BatchJobService", return_value=mock_batch_job_service),
            patch("src.tasks.import_tasks.stream_csv_from_url", http_500_error),
            patch("src.tasks.import_tasks.get_settings") as mock_settings,
        ):
            mock_engine.return_value = MagicMock()
            mock_engine.return_value.dispose = AsyncMock()
            settings = MagicMock()
            settings.DB_POOL_SIZE = 5
            settings.DB_POOL_MAX_OVERFLOW = 10
            settings.DB_POOL_TIMEOUT = 30
            settings.DB_POOL_RECYCLE = 1800
            mock_settings.return_value = settings

            from src.tasks.import_tasks import process_fact_check_import

            with pytest.raises(httpx.HTTPStatusError):
                await process_fact_check_import(
                    job_id=job_id,
                    batch_size=100,
                    dry_run=False,
                    enqueue_scrapes=False,
                    db_url="postgresql+asyncpg://test:test@localhost/test",
                    redis_url="redis://localhost:6379",
                )

            mock_batch_job_service.fail_job.assert_called_once()

    @pytest.mark.asyncio
    async def test_connection_reset_during_stream(self):
        """Connection reset during streaming fails job."""
        job_id = str(uuid4())

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()

        mock_session_maker = MagicMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_redis = AsyncMock()
        mock_redis.connect = AsyncMock()
        mock_redis.disconnect = AsyncMock()

        mock_progress_tracker = MagicMock()

        mock_batch_job_service = MagicMock()
        mock_batch_job_service.start_job = AsyncMock()
        mock_batch_job_service.fail_job = AsyncMock()

        async def connection_reset(*args, **kwargs):
            raise httpx.RemoteProtocolError("Connection reset by peer")
            yield  # pragma: no cover - makes this an async generator

        with (
            patch("src.tasks.import_tasks.create_async_engine") as mock_engine,
            patch("src.tasks.import_tasks.async_sessionmaker", return_value=mock_session_maker),
            patch("src.tasks.import_tasks.RedisClient", return_value=mock_redis),
            patch(
                "src.tasks.import_tasks.BatchJobProgressTracker",
                return_value=mock_progress_tracker,
            ),
            patch("src.tasks.import_tasks.BatchJobService", return_value=mock_batch_job_service),
            patch("src.tasks.import_tasks.stream_csv_from_url", connection_reset),
            patch("src.tasks.import_tasks.get_settings") as mock_settings,
        ):
            mock_engine.return_value = MagicMock()
            mock_engine.return_value.dispose = AsyncMock()
            settings = MagicMock()
            settings.DB_POOL_SIZE = 5
            settings.DB_POOL_MAX_OVERFLOW = 10
            settings.DB_POOL_TIMEOUT = 30
            settings.DB_POOL_RECYCLE = 1800
            mock_settings.return_value = settings

            from src.tasks.import_tasks import process_fact_check_import

            with pytest.raises(httpx.RemoteProtocolError):
                await process_fact_check_import(
                    job_id=job_id,
                    batch_size=100,
                    dry_run=False,
                    enqueue_scrapes=False,
                    db_url="postgresql+asyncpg://test:test@localhost/test",
                    redis_url="redis://localhost:6379",
                )

            mock_batch_job_service.fail_job.assert_called_once()


class TestBatchValidationFailures:
    """Test batch validation failure scenarios."""

    @pytest.mark.asyncio
    async def test_partial_validation_failures_continues(self):
        """Partial validation failures don't stop the import."""
        job_id = str(uuid4())

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()

        mock_session_maker = MagicMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_redis = AsyncMock()
        mock_redis.connect = AsyncMock()
        mock_redis.disconnect = AsyncMock()

        mock_progress_tracker = MagicMock()
        mock_progress_tracker.update_progress = AsyncMock()

        mock_batch_job_service = MagicMock()
        mock_batch_job_service.start_job = AsyncMock()
        mock_batch_job_service.complete_job = AsyncMock()
        mock_batch_job_service.update_progress = AsyncMock()
        mock_job = MagicMock()
        mock_job.metadata_ = {}
        mock_batch_job_service.get_job = AsyncMock(return_value=mock_job)

        csv_content = "id,claim,url,title,claim_id,fact_check_id,publisher_name,publisher_site\n"
        csv_content += "1,Valid claim,https://example.com,Test,100,200,Publisher,example.com\n"
        csv_content += "2,Another valid,https://example2.com,Test2,101,201,Publisher,example.com\n"

        async def mock_stream_csv(*args, **kwargs):
            yield csv_content

        with (
            patch("src.tasks.import_tasks.create_async_engine") as mock_engine,
            patch("src.tasks.import_tasks.async_sessionmaker", return_value=mock_session_maker),
            patch("src.tasks.import_tasks.RedisClient", return_value=mock_redis),
            patch(
                "src.tasks.import_tasks.BatchJobProgressTracker",
                return_value=mock_progress_tracker,
            ),
            patch("src.tasks.import_tasks.BatchJobService", return_value=mock_batch_job_service),
            patch("src.tasks.import_tasks.stream_csv_from_url", mock_stream_csv),
            patch("src.tasks.import_tasks.validate_and_normalize_batch") as mock_validate,
            patch("src.tasks.import_tasks.upsert_candidates") as mock_upsert,
            patch("src.tasks.import_tasks.get_settings") as mock_settings,
        ):
            mock_engine.return_value = MagicMock()
            mock_engine.return_value.dispose = AsyncMock()
            settings = MagicMock()
            settings.DB_POOL_SIZE = 5
            settings.DB_POOL_MAX_OVERFLOW = 10
            settings.DB_POOL_TIMEOUT = 30
            settings.DB_POOL_RECYCLE = 1800
            mock_settings.return_value = settings

            mock_candidates = [MagicMock()]
            mock_errors = ["Row 2: Validation error"]
            mock_validate.return_value = (mock_candidates, mock_errors)
            mock_upsert.return_value = (1, 0)

            from src.tasks.import_tasks import process_fact_check_import

            result = await process_fact_check_import(
                job_id=job_id,
                batch_size=100,
                dry_run=False,
                enqueue_scrapes=False,
                db_url="postgresql+asyncpg://test:test@localhost/test",
                redis_url="redis://localhost:6379",
            )

            assert result["status"] == "completed"
            assert result["valid_rows"] == 1
            assert result["invalid_rows"] == 1
            mock_batch_job_service.complete_job.assert_called_once()

    @pytest.mark.asyncio
    async def test_all_rows_invalid_completes_with_error_summary(self):
        """All rows invalid still completes job with error summary."""
        job_id = str(uuid4())

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()

        mock_session_maker = MagicMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_redis = AsyncMock()
        mock_redis.connect = AsyncMock()
        mock_redis.disconnect = AsyncMock()

        mock_progress_tracker = MagicMock()
        mock_progress_tracker.update_progress = AsyncMock()

        mock_batch_job_service = MagicMock()
        mock_batch_job_service.start_job = AsyncMock()
        mock_batch_job_service.complete_job = AsyncMock()
        mock_batch_job_service.update_progress = AsyncMock()
        mock_job = MagicMock()
        mock_job.metadata_ = {}
        mock_batch_job_service.get_job = AsyncMock(return_value=mock_job)

        csv_content = "id,claim,url\n1,Bad row,invalid\n"

        async def mock_stream_csv(*args, **kwargs):
            yield csv_content

        with (
            patch("src.tasks.import_tasks.create_async_engine") as mock_engine,
            patch("src.tasks.import_tasks.async_sessionmaker", return_value=mock_session_maker),
            patch("src.tasks.import_tasks.RedisClient", return_value=mock_redis),
            patch(
                "src.tasks.import_tasks.BatchJobProgressTracker",
                return_value=mock_progress_tracker,
            ),
            patch("src.tasks.import_tasks.BatchJobService", return_value=mock_batch_job_service),
            patch("src.tasks.import_tasks.stream_csv_from_url", mock_stream_csv),
            patch("src.tasks.import_tasks.validate_and_normalize_batch") as mock_validate,
            patch("src.tasks.import_tasks.get_settings") as mock_settings,
        ):
            mock_engine.return_value = MagicMock()
            mock_engine.return_value.dispose = AsyncMock()
            settings = MagicMock()
            settings.DB_POOL_SIZE = 5
            settings.DB_POOL_MAX_OVERFLOW = 10
            settings.DB_POOL_TIMEOUT = 30
            settings.DB_POOL_RECYCLE = 1800
            mock_settings.return_value = settings

            mock_validate.return_value = ([], ["Row 1: Missing required fields"])

            from src.tasks.import_tasks import process_fact_check_import

            result = await process_fact_check_import(
                job_id=job_id,
                batch_size=100,
                dry_run=False,
                enqueue_scrapes=False,
                db_url="postgresql+asyncpg://test:test@localhost/test",
                redis_url="redis://localhost:6379",
            )

            assert result["status"] == "completed"
            assert result["valid_rows"] == 0
            assert result["invalid_rows"] == 1
            assert "errors" in result
            mock_batch_job_service.complete_job.assert_called_once()

    @pytest.mark.asyncio
    async def test_validation_error_aggregation(self):
        """Validation errors are properly aggregated and limited."""
        job_id = str(uuid4())

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()

        mock_session_maker = MagicMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_redis = AsyncMock()
        mock_redis.connect = AsyncMock()
        mock_redis.disconnect = AsyncMock()

        mock_progress_tracker = MagicMock()
        mock_progress_tracker.update_progress = AsyncMock()

        mock_batch_job_service = MagicMock()
        mock_batch_job_service.start_job = AsyncMock()
        mock_batch_job_service.complete_job = AsyncMock()
        mock_batch_job_service.update_progress = AsyncMock()
        mock_job = MagicMock()
        mock_job.metadata_ = {}
        mock_batch_job_service.get_job = AsyncMock(return_value=mock_job)

        csv_content = "id,claim,url\n" + "\n".join(f"{i},row,url" for i in range(100))

        async def mock_stream_csv(*args, **kwargs):
            yield csv_content

        errors = [f"Row {i}: Error" for i in range(100)]

        with (
            patch("src.tasks.import_tasks.create_async_engine") as mock_engine,
            patch("src.tasks.import_tasks.async_sessionmaker", return_value=mock_session_maker),
            patch("src.tasks.import_tasks.RedisClient", return_value=mock_redis),
            patch(
                "src.tasks.import_tasks.BatchJobProgressTracker",
                return_value=mock_progress_tracker,
            ),
            patch("src.tasks.import_tasks.BatchJobService", return_value=mock_batch_job_service),
            patch("src.tasks.import_tasks.stream_csv_from_url", mock_stream_csv),
            patch("src.tasks.import_tasks.validate_and_normalize_batch") as mock_validate,
            patch("src.tasks.import_tasks.get_settings") as mock_settings,
        ):
            mock_engine.return_value = MagicMock()
            mock_engine.return_value.dispose = AsyncMock()
            settings = MagicMock()
            settings.DB_POOL_SIZE = 5
            settings.DB_POOL_MAX_OVERFLOW = 10
            settings.DB_POOL_TIMEOUT = 30
            settings.DB_POOL_RECYCLE = 1800
            mock_settings.return_value = settings

            mock_validate.return_value = ([], errors)

            from src.tasks.import_tasks import process_fact_check_import

            result = await process_fact_check_import(
                job_id=job_id,
                batch_size=100,
                dry_run=False,
                enqueue_scrapes=False,
                db_url="postgresql+asyncpg://test:test@localhost/test",
                redis_url="redis://localhost:6379",
            )

            assert result["errors"]["truncated"] is True
            assert result["errors"]["total_validation_errors"] == 100
            assert len(result["errors"]["validation_errors"]) == 50


class TestDatabaseFailures:
    """Test database failure scenarios."""

    @pytest.mark.asyncio
    async def test_upsert_candidates_db_failure_fails_job(self):
        """Database failure during upsert fails the job."""
        job_id = str(uuid4())

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()

        mock_session_maker = MagicMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_redis = AsyncMock()
        mock_redis.connect = AsyncMock()
        mock_redis.disconnect = AsyncMock()

        mock_progress_tracker = MagicMock()

        mock_batch_job_service = MagicMock()
        mock_batch_job_service.start_job = AsyncMock()
        mock_batch_job_service.fail_job = AsyncMock()

        csv_content = "id,claim,url,title,claim_id,fact_check_id,publisher_name,publisher_site\n"
        csv_content += "1,Test claim,https://example.com,Test,100,200,Publisher,example.com\n"

        async def mock_stream_csv(*args, **kwargs):
            yield csv_content

        with (
            patch("src.tasks.import_tasks.create_async_engine") as mock_engine,
            patch("src.tasks.import_tasks.async_sessionmaker", return_value=mock_session_maker),
            patch("src.tasks.import_tasks.RedisClient", return_value=mock_redis),
            patch(
                "src.tasks.import_tasks.BatchJobProgressTracker",
                return_value=mock_progress_tracker,
            ),
            patch("src.tasks.import_tasks.BatchJobService", return_value=mock_batch_job_service),
            patch("src.tasks.import_tasks.stream_csv_from_url", mock_stream_csv),
            patch("src.tasks.import_tasks.validate_and_normalize_batch") as mock_validate,
            patch("src.tasks.import_tasks.upsert_candidates") as mock_upsert,
            patch("src.tasks.import_tasks.get_settings") as mock_settings,
        ):
            mock_engine.return_value = MagicMock()
            mock_engine.return_value.dispose = AsyncMock()
            settings = MagicMock()
            settings.DB_POOL_SIZE = 5
            settings.DB_POOL_MAX_OVERFLOW = 10
            settings.DB_POOL_TIMEOUT = 30
            settings.DB_POOL_RECYCLE = 1800
            mock_settings.return_value = settings

            mock_validate.return_value = ([MagicMock()], [])
            mock_upsert.side_effect = Exception("Database connection lost")

            from src.tasks.import_tasks import process_fact_check_import

            with pytest.raises(Exception, match="Database connection lost"):
                await process_fact_check_import(
                    job_id=job_id,
                    batch_size=100,
                    dry_run=False,
                    enqueue_scrapes=False,
                    db_url="postgresql+asyncpg://test:test@localhost/test",
                    redis_url="redis://localhost:6379",
                )

            mock_batch_job_service.fail_job.assert_called_once()

    @pytest.mark.asyncio
    async def test_db_constraint_violation(self):
        """Constraint violation during upsert fails the job."""
        from sqlalchemy.exc import IntegrityError

        job_id = str(uuid4())

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()

        mock_session_maker = MagicMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_redis = AsyncMock()
        mock_redis.connect = AsyncMock()
        mock_redis.disconnect = AsyncMock()

        mock_progress_tracker = MagicMock()

        mock_batch_job_service = MagicMock()
        mock_batch_job_service.start_job = AsyncMock()
        mock_batch_job_service.fail_job = AsyncMock()

        csv_content = "id,claim,url,title,claim_id,fact_check_id,publisher_name,publisher_site\n"
        csv_content += "1,Test claim,https://example.com,Test,100,200,Publisher,example.com\n"

        async def mock_stream_csv(*args, **kwargs):
            yield csv_content

        with (
            patch("src.tasks.import_tasks.create_async_engine") as mock_engine,
            patch("src.tasks.import_tasks.async_sessionmaker", return_value=mock_session_maker),
            patch("src.tasks.import_tasks.RedisClient", return_value=mock_redis),
            patch(
                "src.tasks.import_tasks.BatchJobProgressTracker",
                return_value=mock_progress_tracker,
            ),
            patch("src.tasks.import_tasks.BatchJobService", return_value=mock_batch_job_service),
            patch("src.tasks.import_tasks.stream_csv_from_url", mock_stream_csv),
            patch("src.tasks.import_tasks.validate_and_normalize_batch") as mock_validate,
            patch("src.tasks.import_tasks.upsert_candidates") as mock_upsert,
            patch("src.tasks.import_tasks.get_settings") as mock_settings,
        ):
            mock_engine.return_value = MagicMock()
            mock_engine.return_value.dispose = AsyncMock()
            settings = MagicMock()
            settings.DB_POOL_SIZE = 5
            settings.DB_POOL_MAX_OVERFLOW = 10
            settings.DB_POOL_TIMEOUT = 30
            settings.DB_POOL_RECYCLE = 1800
            mock_settings.return_value = settings

            mock_validate.return_value = ([MagicMock()], [])
            mock_upsert.side_effect = IntegrityError(
                "UNIQUE constraint failed", params=None, orig=None
            )

            from src.tasks.import_tasks import process_fact_check_import

            with pytest.raises(IntegrityError):
                await process_fact_check_import(
                    job_id=job_id,
                    batch_size=100,
                    dry_run=False,
                    enqueue_scrapes=False,
                    db_url="postgresql+asyncpg://test:test@localhost/test",
                    redis_url="redis://localhost:6379",
                )

            mock_batch_job_service.fail_job.assert_called_once()


class TestRedisFailures:
    """Test Redis failure scenarios."""

    @pytest.mark.asyncio
    async def test_redis_disconnect_during_progress(self):
        """Redis disconnect during progress update logs warning but continues."""
        job_id = str(uuid4())

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()

        mock_session_maker = MagicMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_redis = AsyncMock()
        mock_redis.connect = AsyncMock()
        mock_redis.disconnect = AsyncMock()

        mock_progress_tracker = MagicMock()
        mock_progress_tracker.update_progress = AsyncMock()

        mock_batch_job_service = MagicMock()
        mock_batch_job_service.start_job = AsyncMock()
        mock_batch_job_service.complete_job = AsyncMock()
        mock_batch_job_service.update_progress = AsyncMock(
            side_effect=ConnectionError("Redis connection lost")
        )
        mock_job = MagicMock()
        mock_job.metadata_ = {}
        mock_batch_job_service.get_job = AsyncMock(return_value=mock_job)

        csv_content = "id,claim,url,title,claim_id,fact_check_id,publisher_name,publisher_site\n"
        csv_content += "1,Test claim,https://example.com,Test,100,200,Publisher,example.com\n"

        async def mock_stream_csv(*args, **kwargs):
            yield csv_content

        with (
            patch("src.tasks.import_tasks.create_async_engine") as mock_engine,
            patch("src.tasks.import_tasks.async_sessionmaker", return_value=mock_session_maker),
            patch("src.tasks.import_tasks.RedisClient", return_value=mock_redis),
            patch(
                "src.tasks.import_tasks.BatchJobProgressTracker",
                return_value=mock_progress_tracker,
            ),
            patch("src.tasks.import_tasks.BatchJobService", return_value=mock_batch_job_service),
            patch("src.tasks.import_tasks.stream_csv_from_url", mock_stream_csv),
            patch("src.tasks.import_tasks.validate_and_normalize_batch") as mock_validate,
            patch("src.tasks.import_tasks.upsert_candidates") as mock_upsert,
            patch("src.tasks.import_tasks.get_settings") as mock_settings,
        ):
            mock_engine.return_value = MagicMock()
            mock_engine.return_value.dispose = AsyncMock()
            settings = MagicMock()
            settings.DB_POOL_SIZE = 5
            settings.DB_POOL_MAX_OVERFLOW = 10
            settings.DB_POOL_TIMEOUT = 30
            settings.DB_POOL_RECYCLE = 1800
            mock_settings.return_value = settings

            mock_validate.return_value = ([MagicMock()], [])
            mock_upsert.return_value = (1, 0)

            from src.tasks.import_tasks import process_fact_check_import

            result = await process_fact_check_import(
                job_id=job_id,
                batch_size=100,
                dry_run=False,
                enqueue_scrapes=False,
                db_url="postgresql+asyncpg://test:test@localhost/test",
                redis_url="redis://localhost:6379",
            )

            assert result["status"] == "completed"
            mock_batch_job_service.complete_job.assert_called_once()

    @pytest.mark.asyncio
    async def test_progress_tracker_operation_timeout(self):
        """Progress tracker timeout logs warning but import continues."""

        job_id = str(uuid4())

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()

        mock_session_maker = MagicMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_redis = AsyncMock()
        mock_redis.connect = AsyncMock()
        mock_redis.disconnect = AsyncMock()

        mock_progress_tracker = MagicMock()
        mock_progress_tracker.update_progress = AsyncMock()

        mock_batch_job_service = MagicMock()
        mock_batch_job_service.start_job = AsyncMock()
        mock_batch_job_service.complete_job = AsyncMock()
        mock_batch_job_service.update_progress = AsyncMock(
            side_effect=TimeoutError("Redis timeout")
        )
        mock_job = MagicMock()
        mock_job.metadata_ = {}
        mock_batch_job_service.get_job = AsyncMock(return_value=mock_job)

        csv_content = "id,claim,url,title,claim_id,fact_check_id,publisher_name,publisher_site\n"
        csv_content += "1,Test claim,https://example.com,Test,100,200,Publisher,example.com\n"

        async def mock_stream_csv(*args, **kwargs):
            yield csv_content

        with (
            patch("src.tasks.import_tasks.create_async_engine") as mock_engine,
            patch("src.tasks.import_tasks.async_sessionmaker", return_value=mock_session_maker),
            patch("src.tasks.import_tasks.RedisClient", return_value=mock_redis),
            patch(
                "src.tasks.import_tasks.BatchJobProgressTracker",
                return_value=mock_progress_tracker,
            ),
            patch("src.tasks.import_tasks.BatchJobService", return_value=mock_batch_job_service),
            patch("src.tasks.import_tasks.stream_csv_from_url", mock_stream_csv),
            patch("src.tasks.import_tasks.validate_and_normalize_batch") as mock_validate,
            patch("src.tasks.import_tasks.upsert_candidates") as mock_upsert,
            patch("src.tasks.import_tasks.get_settings") as mock_settings,
        ):
            mock_engine.return_value = MagicMock()
            mock_engine.return_value.dispose = AsyncMock()
            settings = MagicMock()
            settings.DB_POOL_SIZE = 5
            settings.DB_POOL_MAX_OVERFLOW = 10
            settings.DB_POOL_TIMEOUT = 30
            settings.DB_POOL_RECYCLE = 1800
            mock_settings.return_value = settings

            mock_validate.return_value = ([MagicMock()], [])
            mock_upsert.return_value = (1, 0)

            from src.tasks.import_tasks import process_fact_check_import

            result = await process_fact_check_import(
                job_id=job_id,
                batch_size=100,
                dry_run=False,
                enqueue_scrapes=False,
                db_url="postgresql+asyncpg://test:test@localhost/test",
                redis_url="redis://localhost:6379",
            )

            assert result["status"] == "completed"


class TestEndToEndFlow:
    """Test end-to-end task flow."""

    @pytest.mark.asyncio
    async def test_successful_import_full_flow(self):
        """Successful import completes with correct stats."""
        job_id = str(uuid4())

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()

        mock_session_maker = MagicMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_redis = AsyncMock()
        mock_redis.connect = AsyncMock()
        mock_redis.disconnect = AsyncMock()

        mock_progress_tracker = MagicMock()
        mock_progress_tracker.update_progress = AsyncMock()

        mock_batch_job_service = MagicMock()
        mock_batch_job_service.start_job = AsyncMock()
        mock_batch_job_service.complete_job = AsyncMock()
        mock_batch_job_service.update_progress = AsyncMock()
        mock_job = MagicMock()
        mock_job.metadata_ = {}
        mock_batch_job_service.get_job = AsyncMock(return_value=mock_job)

        csv_content = "id,claim,url,title,claim_id,fact_check_id,publisher_name,publisher_site\n"
        csv_content += "1,Claim 1,https://example.com/1,Test 1,100,200,Publisher,example.com\n"
        csv_content += "2,Claim 2,https://example.com/2,Test 2,101,201,Publisher,example.com\n"

        async def mock_stream_csv(*args, **kwargs):
            yield csv_content

        with (
            patch("src.tasks.import_tasks.create_async_engine") as mock_engine,
            patch("src.tasks.import_tasks.async_sessionmaker", return_value=mock_session_maker),
            patch("src.tasks.import_tasks.RedisClient", return_value=mock_redis),
            patch(
                "src.tasks.import_tasks.BatchJobProgressTracker",
                return_value=mock_progress_tracker,
            ),
            patch("src.tasks.import_tasks.BatchJobService", return_value=mock_batch_job_service),
            patch("src.tasks.import_tasks.stream_csv_from_url", mock_stream_csv),
            patch("src.tasks.import_tasks.validate_and_normalize_batch") as mock_validate,
            patch("src.tasks.import_tasks.upsert_candidates") as mock_upsert,
            patch("src.tasks.import_tasks.get_settings") as mock_settings,
        ):
            mock_engine.return_value = MagicMock()
            mock_engine.return_value.dispose = AsyncMock()
            settings = MagicMock()
            settings.DB_POOL_SIZE = 5
            settings.DB_POOL_MAX_OVERFLOW = 10
            settings.DB_POOL_TIMEOUT = 30
            settings.DB_POOL_RECYCLE = 1800
            mock_settings.return_value = settings

            mock_validate.return_value = ([MagicMock(), MagicMock()], [])
            mock_upsert.return_value = (1, 1)

            from src.tasks.import_tasks import process_fact_check_import

            result = await process_fact_check_import(
                job_id=job_id,
                batch_size=100,
                dry_run=False,
                enqueue_scrapes=False,
                db_url="postgresql+asyncpg://test:test@localhost/test",
                redis_url="redis://localhost:6379",
            )

            assert result["status"] == "completed"
            assert result["valid_rows"] == 2
            assert result["invalid_rows"] == 0
            assert result["inserted"] == 1
            assert result["updated"] == 1
            mock_batch_job_service.start_job.assert_called_once()
            mock_batch_job_service.complete_job.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_empty_csv(self):
        """Empty CSV completes with zero counts."""
        job_id = str(uuid4())

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()

        mock_session_maker = MagicMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_redis = AsyncMock()
        mock_redis.connect = AsyncMock()
        mock_redis.disconnect = AsyncMock()

        mock_progress_tracker = MagicMock()
        mock_progress_tracker.update_progress = AsyncMock()

        mock_batch_job_service = MagicMock()
        mock_batch_job_service.start_job = AsyncMock()
        mock_batch_job_service.complete_job = AsyncMock()
        mock_job = MagicMock()
        mock_job.metadata_ = {}
        mock_batch_job_service.get_job = AsyncMock(return_value=mock_job)

        csv_content = "id,claim,url\n"

        async def mock_stream_csv(*args, **kwargs):
            yield csv_content

        with (
            patch("src.tasks.import_tasks.create_async_engine") as mock_engine,
            patch("src.tasks.import_tasks.async_sessionmaker", return_value=mock_session_maker),
            patch("src.tasks.import_tasks.RedisClient", return_value=mock_redis),
            patch(
                "src.tasks.import_tasks.BatchJobProgressTracker",
                return_value=mock_progress_tracker,
            ),
            patch("src.tasks.import_tasks.BatchJobService", return_value=mock_batch_job_service),
            patch("src.tasks.import_tasks.stream_csv_from_url", mock_stream_csv),
            patch("src.tasks.import_tasks.get_settings") as mock_settings,
        ):
            mock_engine.return_value = MagicMock()
            mock_engine.return_value.dispose = AsyncMock()
            settings = MagicMock()
            settings.DB_POOL_SIZE = 5
            settings.DB_POOL_MAX_OVERFLOW = 10
            settings.DB_POOL_TIMEOUT = 30
            settings.DB_POOL_RECYCLE = 1800
            mock_settings.return_value = settings

            from src.tasks.import_tasks import process_fact_check_import

            result = await process_fact_check_import(
                job_id=job_id,
                batch_size=100,
                dry_run=False,
                enqueue_scrapes=False,
                db_url="postgresql+asyncpg://test:test@localhost/test",
                redis_url="redis://localhost:6379",
            )

            assert result["status"] == "completed"
            assert result["total_rows"] == 0
            assert result["valid_rows"] == 0
            mock_batch_job_service.complete_job.assert_called_once()

    @pytest.mark.asyncio
    async def test_dry_run_mode_no_inserts(self):
        """Dry run mode validates but does not insert."""
        job_id = str(uuid4())

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()

        mock_session_maker = MagicMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_redis = AsyncMock()
        mock_redis.connect = AsyncMock()
        mock_redis.disconnect = AsyncMock()

        mock_progress_tracker = MagicMock()
        mock_progress_tracker.update_progress = AsyncMock()

        mock_batch_job_service = MagicMock()
        mock_batch_job_service.start_job = AsyncMock()
        mock_batch_job_service.complete_job = AsyncMock()
        mock_batch_job_service.update_progress = AsyncMock()
        mock_job = MagicMock()
        mock_job.metadata_ = {}
        mock_batch_job_service.get_job = AsyncMock(return_value=mock_job)

        csv_content = "id,claim,url,title,claim_id,fact_check_id,publisher_name,publisher_site\n"
        csv_content += "1,Claim 1,https://example.com/1,Test 1,100,200,Publisher,example.com\n"

        async def mock_stream_csv(*args, **kwargs):
            yield csv_content

        with (
            patch("src.tasks.import_tasks.create_async_engine") as mock_engine,
            patch("src.tasks.import_tasks.async_sessionmaker", return_value=mock_session_maker),
            patch("src.tasks.import_tasks.RedisClient", return_value=mock_redis),
            patch(
                "src.tasks.import_tasks.BatchJobProgressTracker",
                return_value=mock_progress_tracker,
            ),
            patch("src.tasks.import_tasks.BatchJobService", return_value=mock_batch_job_service),
            patch("src.tasks.import_tasks.stream_csv_from_url", mock_stream_csv),
            patch("src.tasks.import_tasks.validate_and_normalize_batch") as mock_validate,
            patch("src.tasks.import_tasks.upsert_candidates") as mock_upsert,
            patch("src.tasks.import_tasks.get_settings") as mock_settings,
        ):
            mock_engine.return_value = MagicMock()
            mock_engine.return_value.dispose = AsyncMock()
            settings = MagicMock()
            settings.DB_POOL_SIZE = 5
            settings.DB_POOL_MAX_OVERFLOW = 10
            settings.DB_POOL_TIMEOUT = 30
            settings.DB_POOL_RECYCLE = 1800
            mock_settings.return_value = settings

            mock_validate.return_value = ([MagicMock()], [])

            from src.tasks.import_tasks import process_fact_check_import

            result = await process_fact_check_import(
                job_id=job_id,
                batch_size=100,
                dry_run=True,
                enqueue_scrapes=False,
                db_url="postgresql+asyncpg://test:test@localhost/test",
                redis_url="redis://localhost:6379",
            )

            assert result["status"] == "completed"
            assert result["dry_run"] is True
            assert result["inserted"] == 0
            assert result["updated"] == 0
            mock_upsert.assert_not_called()

    @pytest.mark.asyncio
    async def test_enqueue_scrapes_after_success(self):
        """Enqueues scrape tasks after successful import."""
        job_id = str(uuid4())

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()

        mock_session_maker = MagicMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_redis = AsyncMock()
        mock_redis.connect = AsyncMock()
        mock_redis.disconnect = AsyncMock()

        mock_progress_tracker = MagicMock()
        mock_progress_tracker.update_progress = AsyncMock()

        mock_batch_job_service = MagicMock()
        mock_batch_job_service.start_job = AsyncMock()
        mock_batch_job_service.complete_job = AsyncMock()
        mock_batch_job_service.update_progress = AsyncMock()
        mock_job = MagicMock()
        mock_job.metadata_ = {}
        mock_batch_job_service.get_job = AsyncMock(return_value=mock_job)

        csv_content = "id,claim,url,title,claim_id,fact_check_id,publisher_name,publisher_site\n"
        csv_content += "1,Claim 1,https://example.com/1,Test 1,100,200,Publisher,example.com\n"

        async def mock_stream_csv(*args, **kwargs):
            yield csv_content

        with (
            patch("src.tasks.import_tasks.create_async_engine") as mock_engine,
            patch("src.tasks.import_tasks.async_sessionmaker", return_value=mock_session_maker),
            patch("src.tasks.import_tasks.RedisClient", return_value=mock_redis),
            patch(
                "src.tasks.import_tasks.BatchJobProgressTracker",
                return_value=mock_progress_tracker,
            ),
            patch("src.tasks.import_tasks.BatchJobService", return_value=mock_batch_job_service),
            patch("src.tasks.import_tasks.stream_csv_from_url", mock_stream_csv),
            patch("src.tasks.import_tasks.validate_and_normalize_batch") as mock_validate,
            patch("src.tasks.import_tasks.upsert_candidates") as mock_upsert,
            patch(
                "src.tasks.import_tasks.enqueue_scrape_batch",
                new=AsyncMock(return_value={"enqueued": 10}),
            ) as mock_enqueue,
            patch("src.tasks.import_tasks.get_settings") as mock_settings,
        ):
            mock_engine.return_value = MagicMock()
            mock_engine.return_value.dispose = AsyncMock()
            settings = MagicMock()
            settings.DB_POOL_SIZE = 5
            settings.DB_POOL_MAX_OVERFLOW = 10
            settings.DB_POOL_TIMEOUT = 30
            settings.DB_POOL_RECYCLE = 1800
            mock_settings.return_value = settings

            mock_validate.return_value = ([MagicMock()], [])
            mock_upsert.return_value = (1, 0)

            from src.tasks.import_tasks import process_fact_check_import

            result = await process_fact_check_import(
                job_id=job_id,
                batch_size=100,
                dry_run=False,
                enqueue_scrapes=True,
                db_url="postgresql+asyncpg://test:test@localhost/test",
                redis_url="redis://localhost:6379",
            )

            assert result["status"] == "completed"
            assert result["scrapes_enqueued"] == 10
            mock_enqueue.assert_called_once_with(batch_size=100)

    @pytest.mark.asyncio
    async def test_enqueue_scrapes_failure_logged_not_fatal(self):
        """Enqueue scrape failure is logged but does not fail the job."""
        job_id = str(uuid4())

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()

        mock_session_maker = MagicMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_redis = AsyncMock()
        mock_redis.connect = AsyncMock()
        mock_redis.disconnect = AsyncMock()

        mock_progress_tracker = MagicMock()
        mock_progress_tracker.update_progress = AsyncMock()

        mock_batch_job_service = MagicMock()
        mock_batch_job_service.start_job = AsyncMock()
        mock_batch_job_service.complete_job = AsyncMock()
        mock_batch_job_service.update_progress = AsyncMock()
        mock_job = MagicMock()
        mock_job.metadata_ = {}
        mock_batch_job_service.get_job = AsyncMock(return_value=mock_job)

        csv_content = "id,claim,url,title,claim_id,fact_check_id,publisher_name,publisher_site\n"
        csv_content += "1,Claim 1,https://example.com/1,Test 1,100,200,Publisher,example.com\n"

        async def mock_stream_csv(*args, **kwargs):
            yield csv_content

        with (
            patch("src.tasks.import_tasks.create_async_engine") as mock_engine,
            patch("src.tasks.import_tasks.async_sessionmaker", return_value=mock_session_maker),
            patch("src.tasks.import_tasks.RedisClient", return_value=mock_redis),
            patch(
                "src.tasks.import_tasks.BatchJobProgressTracker",
                return_value=mock_progress_tracker,
            ),
            patch("src.tasks.import_tasks.BatchJobService", return_value=mock_batch_job_service),
            patch("src.tasks.import_tasks.stream_csv_from_url", mock_stream_csv),
            patch("src.tasks.import_tasks.validate_and_normalize_batch") as mock_validate,
            patch("src.tasks.import_tasks.upsert_candidates") as mock_upsert,
            patch(
                "src.tasks.import_tasks.enqueue_scrape_batch",
                new=AsyncMock(return_value={"enqueued": 0}),
            ),
            patch("src.tasks.import_tasks.get_settings") as mock_settings,
        ):
            mock_engine.return_value = MagicMock()
            mock_engine.return_value.dispose = AsyncMock()
            settings = MagicMock()
            settings.DB_POOL_SIZE = 5
            settings.DB_POOL_MAX_OVERFLOW = 10
            settings.DB_POOL_TIMEOUT = 30
            settings.DB_POOL_RECYCLE = 1800
            mock_settings.return_value = settings

            mock_validate.return_value = ([MagicMock()], [])
            mock_upsert.return_value = (1, 0)

            from src.tasks.import_tasks import process_fact_check_import

            result = await process_fact_check_import(
                job_id=job_id,
                batch_size=100,
                dry_run=False,
                enqueue_scrapes=True,
                db_url="postgresql+asyncpg://test:test@localhost/test",
                redis_url="redis://localhost:6379",
            )

            assert result["status"] == "completed"
            mock_batch_job_service.complete_job.assert_called_once()

    @pytest.mark.asyncio
    async def test_resources_cleaned_up_in_finally(self):
        """Resources are cleaned up even on failure."""
        job_id = str(uuid4())

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()

        mock_session_maker = MagicMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_redis = AsyncMock()
        mock_redis.connect = AsyncMock()
        mock_redis.disconnect = AsyncMock()

        mock_progress_tracker = MagicMock()

        mock_batch_job_service = MagicMock()
        mock_batch_job_service.start_job = AsyncMock(side_effect=Exception("Job start failed"))
        mock_batch_job_service.fail_job = AsyncMock()

        mock_engine_instance = MagicMock()
        mock_engine_instance.dispose = AsyncMock()

        with (
            patch("src.tasks.import_tasks.create_async_engine") as mock_engine,
            patch("src.tasks.import_tasks.async_sessionmaker", return_value=mock_session_maker),
            patch("src.tasks.import_tasks.RedisClient", return_value=mock_redis),
            patch(
                "src.tasks.import_tasks.BatchJobProgressTracker",
                return_value=mock_progress_tracker,
            ),
            patch("src.tasks.import_tasks.BatchJobService", return_value=mock_batch_job_service),
            patch("src.tasks.import_tasks.get_settings") as mock_settings,
        ):
            mock_engine.return_value = mock_engine_instance
            settings = MagicMock()
            settings.DB_POOL_SIZE = 5
            settings.DB_POOL_MAX_OVERFLOW = 10
            settings.DB_POOL_TIMEOUT = 30
            settings.DB_POOL_RECYCLE = 1800
            mock_settings.return_value = settings

            from src.tasks.import_tasks import process_fact_check_import

            with pytest.raises(Exception, match="Job start failed"):
                await process_fact_check_import(
                    job_id=job_id,
                    batch_size=100,
                    dry_run=False,
                    enqueue_scrapes=False,
                    db_url="postgresql+asyncpg://test:test@localhost/test",
                    redis_url="redis://localhost:6379",
                )

            mock_redis.disconnect.assert_called_once()
            mock_engine_instance.dispose.assert_called_once()


class TestTaskIQLabels:
    """Test TaskIQ task labels are properly configured."""

    def test_import_task_has_labels(self):
        """Verify import task has component and task_type labels."""
        from src.tasks.broker import _all_registered_tasks

        assert "import:fact_check_bureau" in _all_registered_tasks

        _, labels = _all_registered_tasks["import:fact_check_bureau"]
        assert labels.get("component") == "import_pipeline"
        assert labels.get("task_type") == "batch"
