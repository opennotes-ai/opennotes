"""
TaskIQ tasks for fact-check import operations.

Handles background processing of CSV imports from HuggingFace with:
- Streaming CSV download
- Batch processing for memory efficiency
- Progress tracking via BatchJob infrastructure
- Partial failure handling with error aggregation

Tasks are designed to be self-contained, creating their own database and Redis
connections to work reliably in distributed worker environments.
"""

from typing import Any
from uuid import UUID

from opentelemetry import trace
from opentelemetry.trace import StatusCode
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.batch_jobs.progress_tracker import BatchJobProgressTracker
from src.batch_jobs.service import BatchJobService
from src.cache.redis_client import RedisClient
from src.config import get_settings
from src.fact_checking.import_pipeline.importer import (
    HUGGINGFACE_DATASET_URL,
    ImportStats,
    batched,
    parse_csv_rows,
    stream_csv_from_url,
    upsert_candidates,
    validate_and_normalize_batch,
)
from src.fact_checking.import_pipeline.scrape_tasks import enqueue_scrape_batch
from src.monitoring import get_logger
from src.tasks.broker import register_task

logger = get_logger(__name__)
_tracer = trace.get_tracer(__name__)

MAX_STORED_ERRORS = 50


async def _update_job_total_tasks(
    session: async_sessionmaker,
    job_id: UUID,
    total_tasks: int,
) -> None:
    """Update the total_tasks count on a BatchJob."""
    try:
        async with session() as db:
            service = BatchJobService(db)
            job = await service.get_job(job_id)
            if job:
                job.total_tasks = total_tasks
                await db.commit()
    except Exception as e:
        logger.error(
            "Failed to update job total_tasks",
            extra={
                "job_id": str(job_id),
                "total_tasks": total_tasks,
                "error": str(e),
            },
        )


async def _start_job(
    session: async_sessionmaker,
    progress_tracker: BatchJobProgressTracker,
    job_id: UUID,
) -> None:
    """Transition job from PENDING to IN_PROGRESS."""
    async with session() as db:
        service = BatchJobService(db, progress_tracker)
        await service.start_job(job_id)
        await db.commit()


async def _update_progress(
    session: async_sessionmaker,
    progress_tracker: BatchJobProgressTracker,
    job_id: UUID,
    completed_tasks: int,
    failed_tasks: int,
    current_item: str | None = None,
) -> None:
    """Update job progress in both database and Redis."""
    async with session() as db:
        service = BatchJobService(db, progress_tracker)
        await service.update_progress(
            job_id,
            completed_tasks=completed_tasks,
            failed_tasks=failed_tasks,
            current_item=current_item,
        )
        await db.commit()


async def _complete_job(
    session: async_sessionmaker,
    progress_tracker: BatchJobProgressTracker,
    job_id: UUID,
    completed_tasks: int,
    failed_tasks: int,
    stats: dict[str, Any],
) -> None:
    """Mark job as completed with final stats in metadata."""
    async with session() as db:
        service = BatchJobService(db, progress_tracker)
        job = await service.get_job(job_id)
        if job:
            job.metadata_ = {**job.metadata_, "stats": stats}
        await service.complete_job(job_id, completed_tasks, failed_tasks)
        await db.commit()


async def _fail_job(
    session: async_sessionmaker,
    progress_tracker: BatchJobProgressTracker,
    job_id: UUID,
    error_summary: dict[str, Any],
    completed_tasks: int,
    failed_tasks: int,
) -> None:
    """Mark job as failed with error summary."""
    async with session() as db:
        service = BatchJobService(db, progress_tracker)
        await service.fail_job(job_id, error_summary, completed_tasks, failed_tasks)
        await db.commit()


def _aggregate_errors(
    errors: list[str],
    max_errors: int = MAX_STORED_ERRORS,
) -> dict[str, Any]:
    """Aggregate validation errors into a bounded summary."""
    return {
        "validation_errors": errors[:max_errors],
        "total_validation_errors": len(errors),
        "truncated": len(errors) > max_errors,
    }


@register_task(
    task_name="import:fact_check_bureau",
    component="import_pipeline",
    task_type="batch",
)
async def process_fact_check_import(
    job_id: str,
    batch_size: int,
    dry_run: bool,
    enqueue_scrapes: bool,
    db_url: str,
    redis_url: str,
) -> dict[str, Any]:
    """
    TaskIQ task to process fact-check bureau import.

    This task:
    1. Marks job as IN_PROGRESS
    2. Streams CSV from HuggingFace
    3. Updates total_tasks once CSV size is known
    4. Processes rows in batches (validate, normalize, upsert)
    5. Updates progress after each batch
    6. Marks job as COMPLETED or FAILED
    7. Optionally enqueues scrape tasks for imported candidates

    Args:
        job_id: UUID string of the BatchJob for status tracking
        batch_size: Number of rows per batch
        dry_run: If True, validate only without inserting
        enqueue_scrapes: If True, enqueue scrape tasks after import
        db_url: Database connection URL
        redis_url: Redis connection URL for progress tracking

    Returns:
        dict with status and import stats
    """
    with _tracer.start_as_current_span("import.fact_check_bureau") as span:
        span.set_attribute("job.id", job_id)
        span.set_attribute("job.batch_size", batch_size)
        span.set_attribute("job.dry_run", dry_run)
        span.set_attribute("job.enqueue_scrapes", enqueue_scrapes)

        settings = get_settings()
        job_uuid = UUID(job_id)

        engine = create_async_engine(
            db_url,
            pool_pre_ping=True,
            pool_size=settings.DB_POOL_SIZE,
            max_overflow=settings.DB_POOL_MAX_OVERFLOW,
            pool_timeout=settings.DB_POOL_TIMEOUT,
            pool_recycle=settings.DB_POOL_RECYCLE,
        )
        async_session = async_sessionmaker(engine, expire_on_commit=False)

        redis_client = RedisClient()
        await redis_client.connect(redis_url)
        progress_tracker = BatchJobProgressTracker(redis_client)

        stats = ImportStats(errors=[])
        all_errors: list[str] = []

        try:
            await _start_job(async_session, progress_tracker, job_uuid)

            logger.info(
                "Starting fact-check bureau import",
                extra={
                    "job_id": job_id,
                    "batch_size": batch_size,
                    "dry_run": dry_run,
                    "source": HUGGINGFACE_DATASET_URL,
                },
            )

            async for content in stream_csv_from_url(HUGGINGFACE_DATASET_URL):
                rows = list(parse_csv_rows(content))
                stats.total_rows = len(rows)

                await _update_job_total_tasks(async_session, job_uuid, stats.total_rows)
                span.set_attribute("import.total_rows", stats.total_rows)

                logger.info(
                    "Loaded CSV content",
                    extra={
                        "job_id": job_id,
                        "total_rows": stats.total_rows,
                    },
                )

                async with async_session() as db:
                    for batch_num, batch in enumerate(batched(iter(rows), batch_size)):
                        candidates, errors = validate_and_normalize_batch(batch)
                        stats.valid_rows += len(candidates)
                        stats.invalid_rows += len(errors)
                        all_errors.extend(errors)

                        if not dry_run and candidates:
                            inserted, updated = await upsert_candidates(db, candidates)
                            stats.inserted += inserted
                            stats.updated += updated

                        processed = (batch_num + 1) * batch_size
                        processed = min(processed, stats.total_rows)

                        try:
                            await _update_progress(
                                async_session,
                                progress_tracker,
                                job_uuid,
                                completed_tasks=stats.valid_rows,
                                failed_tasks=stats.invalid_rows,
                                current_item=f"Batch {batch_num + 1} ({processed}/{stats.total_rows})",
                            )
                        except Exception as e:
                            logger.warning(
                                "Failed to update progress after batch",
                                extra={
                                    "job_id": job_id,
                                    "batch_num": batch_num,
                                    "error": str(e),
                                },
                            )

                        if processed % 10000 == 0 or processed >= stats.total_rows:
                            logger.info(
                                "Import progress",
                                extra={
                                    "job_id": job_id,
                                    "processed": processed,
                                    "total": stats.total_rows,
                                    "valid": stats.valid_rows,
                                    "invalid": stats.invalid_rows,
                                },
                            )

            final_stats = {
                "total_rows": stats.total_rows,
                "valid_rows": stats.valid_rows,
                "invalid_rows": stats.invalid_rows,
                "inserted": stats.inserted,
                "updated": stats.updated,
                "dry_run": dry_run,
            }

            if all_errors:
                final_stats["errors"] = _aggregate_errors(all_errors)

            await _complete_job(
                async_session,
                progress_tracker,
                job_uuid,
                completed_tasks=stats.valid_rows,
                failed_tasks=stats.invalid_rows,
                stats=final_stats,
            )

            span.set_attribute("import.valid_rows", stats.valid_rows)
            span.set_attribute("import.invalid_rows", stats.invalid_rows)
            span.set_attribute("import.inserted", stats.inserted)

            logger.info(
                "Fact-check bureau import completed",
                extra={
                    "job_id": job_id,
                    **final_stats,
                },
            )

            if enqueue_scrapes and not dry_run:
                scrape_result = await enqueue_scrape_batch(batch_size=batch_size)
                logger.info(
                    "Enqueued scrape tasks after import",
                    extra={
                        "job_id": job_id,
                        "enqueued": scrape_result.get("enqueued", 0),
                    },
                )
                final_stats["scrapes_enqueued"] = scrape_result.get("enqueued", 0)

            return {"status": "completed", **final_stats}

        except Exception as e:
            error_msg = str(e)
            span.record_exception(e)
            span.set_status(StatusCode.ERROR, error_msg)

            error_summary = {
                "exception": error_msg,
                "exception_type": type(e).__name__,
                "partial_stats": {
                    "total_rows": stats.total_rows,
                    "valid_rows": stats.valid_rows,
                    "invalid_rows": stats.invalid_rows,
                    "inserted": stats.inserted,
                },
            }

            if all_errors:
                error_summary["validation_errors"] = _aggregate_errors(all_errors)

            await _fail_job(
                async_session,
                progress_tracker,
                job_uuid,
                error_summary=error_summary,
                completed_tasks=stats.valid_rows,
                failed_tasks=stats.invalid_rows,
            )

            logger.error(
                "Fact-check bureau import failed",
                extra={
                    "job_id": job_id,
                    "error": error_msg,
                    "valid_rows": stats.valid_rows,
                    "invalid_rows": stats.invalid_rows,
                },
            )

            raise

        finally:
            await redis_client.disconnect()
            await engine.dispose()
