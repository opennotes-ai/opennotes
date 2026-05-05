"""Tests for URL scan DBOS scheduler workflows."""

from __future__ import annotations

import importlib
import re
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

CRON_FIELD_PATTERN = re.compile(
    r"^("
    r"\*"
    r"|(\d+(-\d+)?)"
    r"|(\*/\d+)"
    r")(,(\*|(\d+(-\d+)?)|(\*/\d+)))*$"
)

CRON_FIELD_RANGES = [
    (0, 59),
    (0, 23),
    (1, 31),
    (1, 12),
    (0, 7),
]


def _is_valid_cron(expr: str) -> bool:
    fields = expr.split()
    if len(fields) != 5:
        return False

    for index, field in enumerate(fields):
        if not CRON_FIELD_PATTERN.match(field):
            return False

        low, high = CRON_FIELD_RANGES[index]
        for number_str in re.findall(r"\d+", field):
            value = int(number_str)
            if field.startswith("*/"):
                if value < 1 or value > high:
                    return False
            elif value < low or value > high:
                return False

    return True


def _close_coroutine_and_return(awaitable: object, result: object) -> object:
    close = getattr(awaitable, "close", None)
    if callable(close):
        close()
    return result


class _FakeBlob:
    def __init__(
        self,
        name: str,
        deleted: list[str],
        *,
        time_created: datetime | None = None,
    ) -> None:
        self.name = name
        self._deleted = deleted
        self.time_created = time_created

    def delete(self) -> None:
        self._deleted.append(self.name)


class _FakeBucket:
    def __init__(self, names: list[str] | dict[str, datetime]) -> None:
        self._blob_times = (
            {name: datetime(2026, 1, 1, tzinfo=UTC) for name in names}
            if isinstance(names, list)
            else names
        )
        self.deleted: list[str] = []

    def list_blobs(self):
        return [
            _FakeBlob(name, self.deleted, time_created=time_created)
            for name, time_created in self._blob_times.items()
        ]

    def blob(self, name: str) -> _FakeBlob:
        return _FakeBlob(name, self.deleted)


class _FakeStorageClient:
    def __init__(self, bucket: _FakeBucket) -> None:
        self._bucket = bucket

    def bucket(self, _name: str) -> _FakeBucket:
        return self._bucket


class TestUrlScanOrphanJobsWorkflow:
    def test_workflow_calls_orphan_sweep_step(self) -> None:
        from src.dbos_workflows.url_scan_scheduler_workflows import url_scan_orphan_jobs_workflow

        now = datetime.now(UTC)
        with patch(
            "src.dbos_workflows.url_scan_scheduler_workflows._sweep_orphan_url_scan_jobs_sync"
        ) as mock_step:
            mock_step.return_value = {
                "status": "completed",
                "swept_count": 1,
                "job_ids": ["job-1"],
                "heartbeat_max_age_seconds": 900,
                "executed_at": now.isoformat(),
            }

            result = url_scan_orphan_jobs_workflow.__wrapped__(scheduled_time=now, actual_time=now)

        assert result is None
        mock_step.assert_called_once_with()

    def test_workflow_reraises_errors(self) -> None:
        from src.dbos_workflows.url_scan_scheduler_workflows import url_scan_orphan_jobs_workflow

        now = datetime.now(UTC)
        with patch(
            "src.dbos_workflows.url_scan_scheduler_workflows._sweep_orphan_url_scan_jobs_sync"
        ) as mock_step:
            mock_step.side_effect = RuntimeError("boom")

            with pytest.raises(RuntimeError, match="boom"):
                url_scan_orphan_jobs_workflow.__wrapped__(scheduled_time=now, actual_time=now)


class TestUrlScanPurgeExpiredDataWorkflow:
    def test_workflow_calls_expired_data_step(self) -> None:
        from src.dbos_workflows.url_scan_scheduler_workflows import (
            url_scan_purge_expired_data_workflow,
        )

        now = datetime.now(UTC)
        with patch(
            "src.dbos_workflows.url_scan_scheduler_workflows._purge_expired_url_scan_data_sync"
        ) as mock_step:
            mock_step.return_value = {
                "status": "completed",
                "expired_scrapes_count": 1,
                "expired_web_risk_count": 2,
                "expired_sidebar_cache_count": 3,
                "purged_terminal_jobs_count": 4,
                "terminal_job_retention_days": 30,
                "executed_at": now.isoformat(),
            }

            result = url_scan_purge_expired_data_workflow.__wrapped__(
                scheduled_time=now,
                actual_time=now,
            )

        assert result is None
        mock_step.assert_called_once_with()


class TestUrlScanPurgeOrphanScreenshotsWorkflow:
    def test_workflow_calls_orphan_screenshot_step(self) -> None:
        from src.dbos_workflows.url_scan_scheduler_workflows import (
            url_scan_purge_orphan_screenshots_workflow,
        )

        now = datetime.now(UTC)
        with patch(
            "src.dbos_workflows.url_scan_scheduler_workflows._purge_orphan_url_scan_screenshots_sync"
        ) as mock_step:
            mock_step.return_value = {
                "status": "completed",
                "deleted_count": 1,
                "candidate_count": 2,
                "remaining_count": 1,
                "max_deletes": 10000,
                "deleted_keys": ["orphan.png"],
                "executed_at": now.isoformat(),
            }

            result = url_scan_purge_orphan_screenshots_workflow.__wrapped__(
                scheduled_time=now,
                actual_time=now,
            )

        assert result is None
        mock_step.assert_called_once_with()


class TestStepHelpers:
    def test_orphan_sweep_helper_uses_run_sync(self) -> None:
        from src.dbos_workflows.url_scan_scheduler_workflows import _sweep_orphan_url_scan_jobs_sync

        with patch("src.dbos_workflows.url_scan_scheduler_workflows.run_sync") as mock_run_sync:
            mock_run_sync.side_effect = lambda awaitable: _close_coroutine_and_return(
                awaitable,
                {
                    "status": "completed",
                    "swept_count": 0,
                    "job_ids": [],
                    "heartbeat_max_age_seconds": 900,
                    "executed_at": "2026-01-01T00:00:00+00:00",
                },
            )

            result = _sweep_orphan_url_scan_jobs_sync()

        assert result["swept_count"] == 0
        mock_run_sync.assert_called_once()

    def test_expired_data_helper_uses_run_sync(self) -> None:
        from src.dbos_workflows.url_scan_scheduler_workflows import (
            _purge_expired_url_scan_data_sync,
        )

        with patch("src.dbos_workflows.url_scan_scheduler_workflows.run_sync") as mock_run_sync:
            mock_run_sync.side_effect = lambda awaitable: _close_coroutine_and_return(
                awaitable,
                {
                    "status": "completed",
                    "expired_scrapes_count": 0,
                    "expired_web_risk_count": 0,
                    "expired_sidebar_cache_count": 0,
                    "purged_terminal_jobs_count": 0,
                    "terminal_job_retention_days": 30,
                    "executed_at": "2026-01-01T00:00:00+00:00",
                },
            )

            result = _purge_expired_url_scan_data_sync()

        assert result["purged_terminal_jobs_count"] == 0
        mock_run_sync.assert_called_once()

    def test_orphan_screenshot_helper_skips_when_bucket_unset(self) -> None:
        from src.dbos_workflows.url_scan_scheduler_workflows import (
            _purge_orphan_url_scan_screenshots_sync,
        )

        with (
            patch(
                "src.dbos_workflows.url_scan_scheduler_workflows.run_sync",
                side_effect=lambda awaitable: _close_coroutine_and_return(awaitable, set()),
            ),
            patch(
                "src.dbos_workflows.url_scan_scheduler_workflows.settings.URL_SCAN_SCREENSHOT_BUCKET",
                "",
            ),
        ):
            result = _purge_orphan_url_scan_screenshots_sync()

        assert result["status"] == "skipped"
        assert result["reason"] == "bucket_unset"

    def test_orphan_screenshot_helper_deletes_only_unreferenced_keys(self) -> None:
        from src.dbos_workflows.url_scan_scheduler_workflows import (
            _purge_orphan_url_scan_screenshots_sync,
        )

        bucket = _FakeBucket(["keep.png", "orphan-a.png", "orphan-b.png"])
        with (
            patch(
                "src.dbos_workflows.url_scan_scheduler_workflows.run_sync",
                side_effect=lambda awaitable: _close_coroutine_and_return(awaitable, {"keep.png"}),
            ) as mock_run_sync,
            patch(
                "src.dbos_workflows.url_scan_scheduler_workflows.storage.Client",
                return_value=_FakeStorageClient(bucket),
            ),
            patch(
                "src.dbos_workflows.url_scan_scheduler_workflows.settings.URL_SCAN_SCREENSHOT_BUCKET",
                "test-bucket",
            ),
        ):
            result = _purge_orphan_url_scan_screenshots_sync(max_deletes=10)

        assert sorted(bucket.deleted) == ["orphan-a.png", "orphan-b.png"]
        assert result["deleted_count"] == 2
        assert result["remaining_count"] == 0
        assert result["skipped_young_count"] == 0
        mock_run_sync.assert_called_once()

    def test_orphan_screenshot_helper_skips_young_unreferenced_keys(self) -> None:
        from src.dbos_workflows.url_scan_scheduler_workflows import (
            _purge_orphan_url_scan_screenshots_sync,
        )

        now = datetime.now(UTC)
        bucket = _FakeBucket(
            {
                "old-orphan.png": now - timedelta(days=2),
                "new-upload.png": now - timedelta(minutes=5),
                "keep.png": now - timedelta(days=2),
            }
        )
        with (
            patch(
                "src.dbos_workflows.url_scan_scheduler_workflows.run_sync",
                side_effect=lambda awaitable: _close_coroutine_and_return(awaitable, {"keep.png"}),
            ),
            patch(
                "src.dbos_workflows.url_scan_scheduler_workflows.storage.Client",
                return_value=_FakeStorageClient(bucket),
            ),
            patch(
                "src.dbos_workflows.url_scan_scheduler_workflows.settings.URL_SCAN_SCREENSHOT_BUCKET",
                "test-bucket",
            ),
        ):
            result = _purge_orphan_url_scan_screenshots_sync(
                min_blob_age=timedelta(hours=1),
                max_deletes=10,
            )

        assert bucket.deleted == ["old-orphan.png"]
        assert result["deleted_count"] == 1
        assert result["candidate_count"] == 1
        assert result["skipped_young_count"] == 1

    def test_orphan_screenshot_helper_respects_delete_cap(self) -> None:
        from src.dbos_workflows.url_scan_scheduler_workflows import (
            _purge_orphan_url_scan_screenshots_sync,
        )

        bucket = _FakeBucket(["orphan-1.png", "orphan-2.png", "orphan-3.png"])
        with (
            patch(
                "src.dbos_workflows.url_scan_scheduler_workflows.run_sync",
                side_effect=lambda awaitable: _close_coroutine_and_return(awaitable, set()),
            ),
            patch(
                "src.dbos_workflows.url_scan_scheduler_workflows.storage.Client",
                return_value=_FakeStorageClient(bucket),
            ),
            patch(
                "src.dbos_workflows.url_scan_scheduler_workflows.settings.URL_SCAN_SCREENSHOT_BUCKET",
                "test-bucket",
            ),
        ):
            result = _purge_orphan_url_scan_screenshots_sync(max_deletes=2)

        assert bucket.deleted == ["orphan-1.png", "orphan-2.png"]
        assert result["deleted_count"] == 2
        assert result["candidate_count"] == 3
        assert result["remaining_count"] == 1


class TestWorkflowNameConstants:
    def test_name_constants_match_qualnames(self) -> None:
        from src.dbos_workflows.url_scan_scheduler_workflows import (
            URL_SCAN_ORPHAN_JOBS_WORKFLOW_NAME,
            URL_SCAN_PURGE_EXPIRED_DATA_WORKFLOW_NAME,
            URL_SCAN_PURGE_ORPHAN_SCREENSHOTS_WORKFLOW_NAME,
            url_scan_orphan_jobs_workflow,
            url_scan_purge_expired_data_workflow,
            url_scan_purge_orphan_screenshots_workflow,
        )

        assert url_scan_orphan_jobs_workflow.__qualname__ == URL_SCAN_ORPHAN_JOBS_WORKFLOW_NAME
        assert (
            url_scan_purge_expired_data_workflow.__qualname__
            == URL_SCAN_PURGE_EXPIRED_DATA_WORKFLOW_NAME
        )
        assert (
            url_scan_purge_orphan_screenshots_workflow.__qualname__
            == URL_SCAN_PURGE_ORPHAN_SCREENSHOTS_WORKFLOW_NAME
        )

    def test_name_constants_are_distinct(self) -> None:
        from src.dbos_workflows.url_scan_scheduler_workflows import (
            URL_SCAN_ORPHAN_JOBS_WORKFLOW_NAME,
            URL_SCAN_PURGE_EXPIRED_DATA_WORKFLOW_NAME,
            URL_SCAN_PURGE_ORPHAN_SCREENSHOTS_WORKFLOW_NAME,
        )

        assert (
            len(
                {
                    URL_SCAN_ORPHAN_JOBS_WORKFLOW_NAME,
                    URL_SCAN_PURGE_EXPIRED_DATA_WORKFLOW_NAME,
                    URL_SCAN_PURGE_ORPHAN_SCREENSHOTS_WORKFLOW_NAME,
                }
            )
            == 3
        )


class TestInitExports:
    @pytest.mark.parametrize(
        "export_name",
        [
            "URL_SCAN_ORPHAN_JOBS_WORKFLOW_NAME",
            "URL_SCAN_PURGE_EXPIRED_DATA_WORKFLOW_NAME",
            "URL_SCAN_PURGE_ORPHAN_SCREENSHOTS_WORKFLOW_NAME",
            "url_scan_orphan_jobs_workflow",
            "url_scan_purge_expired_data_workflow",
            "url_scan_purge_orphan_screenshots_workflow",
        ],
    )
    def test_exports_are_lazy_registered(self, export_name: str) -> None:
        module = importlib.reload(importlib.import_module("src.dbos_workflows"))
        assert export_name in module._LAZY_IMPORTS
        exported = getattr(module, export_name)
        assert exported is not None


class TestCronExpressions:
    @pytest.mark.parametrize(
        ("symbol_name", "expected"),
        [
            ("url_scan_orphan_jobs_workflow", "*/5 * * * *"),
            ("url_scan_purge_expired_data_workflow", "0 4 * * *"),
            ("url_scan_purge_orphan_screenshots_workflow", "30 4 * * *"),
        ],
    )
    def test_cron_expression_is_valid(self, symbol_name: str, expected: str) -> None:
        module = importlib.import_module("src.dbos_workflows.url_scan_scheduler_workflows")
        cron_constants = {
            "url_scan_orphan_jobs_workflow": module._ORPHAN_JOB_WORKFLOW_CRON,
            "url_scan_purge_expired_data_workflow": module._PURGE_EXPIRED_DATA_WORKFLOW_CRON,
            "url_scan_purge_orphan_screenshots_workflow": (
                module._PURGE_ORPHAN_SCREENSHOTS_WORKFLOW_CRON
            ),
        }
        assert cron_constants[symbol_name] == expected
        assert _is_valid_cron(expected)
