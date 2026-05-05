"""DBOS scheduled workflows for URL scan maintenance.

These workflows replace the legacy pg_cron sweepers used by vibecheck-server.
All mutating database and GCS work is wrapped in DBOS steps so replay reads
logged results instead of repeating side effects.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from dbos import DBOS
from google.cloud import storage
from sqlalchemy import delete, func, select, update

from src.batch_jobs.models import BatchJob
from src.config import settings
from src.monitoring import get_logger
from src.url_content_scan.models import (
    UrlScanScrape,
    UrlScanSidebarCache,
    UrlScanState,
    UrlScanWebRiskLookup,
)
from src.utils.async_compat import run_sync

logger = get_logger(__name__)

_ORPHAN_JOB_WORKFLOW_CRON = "*/5 * * * *"
_PURGE_EXPIRED_DATA_WORKFLOW_CRON = "0 4 * * *"
_PURGE_ORPHAN_SCREENSHOTS_WORKFLOW_CRON = "30 4 * * *"

_ACTIVE_URL_SCAN_STATUSES = ("pending", "in_progress", "extracting", "analyzing")
_ORPHAN_HEARTBEAT_MAX_AGE = timedelta(minutes=5)
_TERMINAL_JOB_RETENTION = timedelta(days=30)
_MAX_ORPHAN_SCREENSHOT_DELETES = 10_000


@DBOS.step()
def _sweep_orphan_url_scan_jobs_sync(
    *,
    heartbeat_max_age: timedelta = _ORPHAN_HEARTBEAT_MAX_AGE,
) -> dict[str, Any]:
    """Mark URL scan jobs failed when their heartbeat is stale."""

    async def _async_impl() -> dict[str, Any]:
        from src.database import get_session_maker

        cutoff = datetime.now(UTC) - heartbeat_max_age
        async with get_session_maker()() as session:
            result = await session.execute(
                select(UrlScanState.job_id)
                .join(BatchJob, BatchJob.id == UrlScanState.job_id)
                .where(
                    BatchJob.status.in_(_ACTIVE_URL_SCAN_STATUSES),
                    UrlScanState.heartbeat_at.is_not(None),
                    UrlScanState.heartbeat_at < cutoff,
                )
            )
            stale_job_ids = [job_id for (job_id,) in result.all()]

            if stale_job_ids:
                await session.execute(
                    update(BatchJob)
                    .where(BatchJob.id.in_(stale_job_ids))
                    .values(
                        status="failed",
                        completed_at=func.now(),
                        updated_at=func.now(),
                    )
                )
                await session.execute(
                    update(UrlScanState)
                    .where(UrlScanState.job_id.in_(stale_job_ids))
                    .values(
                        error_code="internal",
                        error_message="heartbeat stale",
                        heartbeat_at=None,
                        finished_at=func.now(),
                    )
                )
                await session.commit()

            payload: dict[str, Any] = {
                "status": "completed",
                "swept_count": len(stale_job_ids),
                "job_ids": [str(job_id) for job_id in stale_job_ids],
                "heartbeat_max_age_seconds": int(heartbeat_max_age.total_seconds()),
                "executed_at": datetime.now(UTC).isoformat(),
            }

            if stale_job_ids:
                logger.warning(
                    "URL scan orphan heartbeat sweep marked jobs failed",
                    extra={
                        "swept_count": payload["swept_count"],
                        "job_ids": payload["job_ids"],
                        "heartbeat_max_age_seconds": payload["heartbeat_max_age_seconds"],
                    },
                )
            else:
                logger.debug(
                    "URL scan orphan heartbeat sweep found no stale jobs",
                    extra={
                        "heartbeat_max_age_seconds": payload["heartbeat_max_age_seconds"],
                    },
                )

            return payload

    return run_sync(_async_impl())


@DBOS.step()
def _purge_expired_url_scan_data_sync(
    *,
    terminal_job_retention: timedelta = _TERMINAL_JOB_RETENTION,
) -> dict[str, Any]:
    """Purge expired URL scan cache rows and aged terminal jobs."""

    async def _async_impl() -> dict[str, Any]:
        from src.database import get_session_maker

        now = datetime.now(UTC)
        finished_before = now - terminal_job_retention
        async with get_session_maker()() as session:
            expired_scrapes = await session.execute(
                delete(UrlScanScrape)
                .where(UrlScanScrape.expires_at < now)
                .returning(UrlScanScrape.normalized_url, UrlScanScrape.tier)
            )
            expired_web_risk = await session.execute(
                delete(UrlScanWebRiskLookup)
                .where(UrlScanWebRiskLookup.expires_at < now)
                .returning(UrlScanWebRiskLookup.normalized_url)
            )
            expired_sidebar = await session.execute(
                delete(UrlScanSidebarCache)
                .where(UrlScanSidebarCache.expires_at < now)
                .returning(UrlScanSidebarCache.normalized_url)
            )
            purged_jobs = await session.execute(
                delete(BatchJob)
                .where(
                    BatchJob.id.in_(
                        select(UrlScanState.job_id).where(
                            UrlScanState.finished_at < finished_before
                        )
                    )
                )
                .returning(BatchJob.id)
            )
            await session.commit()

        payload = {
            "status": "completed",
            "expired_scrapes_count": len(expired_scrapes.all()),
            "expired_web_risk_count": len(expired_web_risk.all()),
            "expired_sidebar_cache_count": len(expired_sidebar.all()),
            "purged_terminal_jobs_count": len(purged_jobs.all()),
            "terminal_job_retention_days": terminal_job_retention.days,
            "executed_at": now.isoformat(),
        }

        logger.info(
            "URL scan expired data purge completed",
            extra=payload,
        )
        return payload

    return run_sync(_async_impl())


@DBOS.step()
def _purge_orphan_url_scan_screenshots_sync(
    *,
    max_deletes: int = _MAX_ORPHAN_SCREENSHOT_DELETES,
) -> dict[str, Any]:
    """Delete screenshot blobs no longer referenced by url_scan_scrapes."""

    async def _load_referenced_keys() -> set[str]:
        from src.database import get_session_maker

        async with get_session_maker()() as session:
            result = await session.execute(
                select(UrlScanScrape.screenshot_storage_key).where(
                    UrlScanScrape.screenshot_storage_key.is_not(None)
                )
            )
            return {key for (key,) in result.all() if isinstance(key, str) and key}

    referenced_keys = run_sync(_load_referenced_keys())
    bucket_name = settings.URL_SCAN_SCREENSHOT_BUCKET
    if not bucket_name:
        logger.info("Skipping orphan screenshot purge because URL_SCAN_SCREENSHOT_BUCKET is unset")
        return {
            "status": "skipped",
            "reason": "bucket_unset",
            "deleted_count": 0,
            "candidate_count": 0,
            "max_deletes": max_deletes,
            "executed_at": datetime.now(UTC).isoformat(),
        }

    client = storage.Client()
    bucket = client.bucket(bucket_name)
    orphan_blob_names = [
        blob.name for blob in bucket.list_blobs() if blob.name and blob.name not in referenced_keys
    ]
    delete_names = orphan_blob_names[:max_deletes]
    for blob_name in delete_names:
        bucket.blob(blob_name).delete()

    payload = {
        "status": "completed",
        "deleted_count": len(delete_names),
        "candidate_count": len(orphan_blob_names),
        "remaining_count": max(0, len(orphan_blob_names) - len(delete_names)),
        "max_deletes": max_deletes,
        "deleted_keys": delete_names,
        "executed_at": datetime.now(UTC).isoformat(),
    }

    if len(orphan_blob_names) > max_deletes:
        logger.warning(
            "URL scan orphan screenshot purge hit delete cap",
            extra=payload,
        )
    else:
        logger.info("URL scan orphan screenshot purge completed", extra=payload)

    return payload


@DBOS.scheduled(_ORPHAN_JOB_WORKFLOW_CRON)
@DBOS.workflow()
def url_scan_orphan_jobs_workflow(scheduled_time: datetime, actual_time: datetime) -> None:
    """Sweep stale URL scan heartbeats and fail orphaned active jobs."""

    logger.info(
        "Starting URL scan orphan jobs workflow",
        extra={
            "scheduled_time": scheduled_time.isoformat(),
            "actual_time": actual_time.isoformat(),
        },
    )
    try:
        result = _sweep_orphan_url_scan_jobs_sync()
        logger.info(
            "Completed URL scan orphan jobs workflow",
            extra={
                "scheduled_time": scheduled_time.isoformat(),
                "swept_count": result["swept_count"],
            },
        )
    except Exception as exc:
        logger.error(
            "URL scan orphan jobs workflow failed",
            extra={
                "scheduled_time": scheduled_time.isoformat(),
                "error": str(exc),
            },
        )
        raise


@DBOS.scheduled(_PURGE_EXPIRED_DATA_WORKFLOW_CRON)
@DBOS.workflow()
def url_scan_purge_expired_data_workflow(
    scheduled_time: datetime,
    actual_time: datetime,
) -> None:
    """Purge expired URL scan rows and aged terminal jobs."""

    logger.info(
        "Starting URL scan expired data purge workflow",
        extra={
            "scheduled_time": scheduled_time.isoformat(),
            "actual_time": actual_time.isoformat(),
        },
    )
    try:
        result = _purge_expired_url_scan_data_sync()
        logger.info(
            "Completed URL scan expired data purge workflow",
            extra={
                "scheduled_time": scheduled_time.isoformat(),
                "expired_scrapes_count": result["expired_scrapes_count"],
                "expired_web_risk_count": result["expired_web_risk_count"],
                "expired_sidebar_cache_count": result["expired_sidebar_cache_count"],
                "purged_terminal_jobs_count": result["purged_terminal_jobs_count"],
            },
        )
    except Exception as exc:
        logger.error(
            "URL scan expired data purge workflow failed",
            extra={
                "scheduled_time": scheduled_time.isoformat(),
                "error": str(exc),
            },
        )
        raise


@DBOS.scheduled(_PURGE_ORPHAN_SCREENSHOTS_WORKFLOW_CRON)
@DBOS.workflow()
def url_scan_purge_orphan_screenshots_workflow(
    scheduled_time: datetime,
    actual_time: datetime,
) -> None:
    """Delete screenshot blobs no longer referenced by URL scan scrape rows."""

    logger.info(
        "Starting URL scan orphan screenshot purge workflow",
        extra={
            "scheduled_time": scheduled_time.isoformat(),
            "actual_time": actual_time.isoformat(),
        },
    )
    try:
        result = _purge_orphan_url_scan_screenshots_sync()
        logger.info(
            "Completed URL scan orphan screenshot purge workflow",
            extra={
                "scheduled_time": scheduled_time.isoformat(),
                "deleted_count": result["deleted_count"],
                "candidate_count": result["candidate_count"],
            },
        )
    except Exception as exc:
        logger.error(
            "URL scan orphan screenshot purge workflow failed",
            extra={
                "scheduled_time": scheduled_time.isoformat(),
                "error": str(exc),
            },
        )
        raise


URL_SCAN_ORPHAN_JOBS_WORKFLOW_NAME: str = url_scan_orphan_jobs_workflow.__qualname__
URL_SCAN_PURGE_EXPIRED_DATA_WORKFLOW_NAME: str = url_scan_purge_expired_data_workflow.__qualname__
URL_SCAN_PURGE_ORPHAN_SCREENSHOTS_WORKFLOW_NAME: str = (
    url_scan_purge_orphan_screenshots_workflow.__qualname__
)
