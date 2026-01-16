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

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from opentelemetry import trace
from opentelemetry.trace import StatusCode
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.batch_jobs.constants import DEFAULT_SCRAPE_CONCURRENCY, SCRAPE_URL_TIMEOUT_SECONDS
from src.batch_jobs.progress_tracker import BatchJobProgressTracker
from src.batch_jobs.service import BatchJobService
from src.cache.redis_client import RedisClient
from src.config import get_settings
from src.fact_checking.candidate_models import CandidateStatus, FactCheckedItemCandidate
from src.fact_checking.import_pipeline.importer import (
    HUGGINGFACE_DATASET_URL,
    ImportStats,
    batched,
    parse_csv_rows,
    stream_csv_from_url,
    upsert_candidates,
    validate_and_normalize_batch,
)
from src.fact_checking.import_pipeline.promotion import promote_candidate
from src.fact_checking.import_pipeline.scrape_tasks import (
    enqueue_scrape_batch,
    scrape_url_content,
)
from src.monitoring import get_logger
from src.tasks.broker import register_task

logger = get_logger(__name__)
_tracer = trace.get_tracer(__name__)

MAX_STORED_ERRORS = 50
SCRAPING_TIMEOUT_MINUTES = 120  # 2 hours - allows ~1400 candidates at 5s each
PROMOTING_TIMEOUT_MINUTES = 120  # 2 hours - allows large batch promotion


def _check_row_accounting(
    job_id: str,
    stats: ImportStats,
    span: Any,
) -> bool:
    """Check row accounting integrity and log errors if mismatched.

    Returns True if accounting is valid, False otherwise.
    """
    processed_count = stats.valid_rows + stats.invalid_rows
    if processed_count == stats.total_rows:
        return True

    missing = stats.total_rows - processed_count
    missing_pct = round(missing / stats.total_rows * 100, 2) if stats.total_rows > 0 else 0

    logger.error(
        "Row accounting integrity check failed",
        extra={
            "job_id": job_id,
            "total_rows": stats.total_rows,
            "valid_rows": stats.valid_rows,
            "invalid_rows": stats.invalid_rows,
            "processed": processed_count,
            "missing": missing,
            "missing_percentage": missing_pct,
        },
    )
    span.set_attribute("import.row_mismatch", True)
    span.set_attribute("import.missing_rows", missing)
    return False


class JobNotFoundError(Exception):
    """Raised when a batch job is not found."""

    def __init__(self, job_id: UUID) -> None:
        self.job_id = job_id
        super().__init__(f"Batch job not found: {job_id}")


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
    """Transition job from PENDING to IN_PROGRESS.

    Raises:
        JobNotFoundError: If the job doesn't exist in the database.
    """
    async with session() as db:
        service = BatchJobService(db, progress_tracker)
        job = await service.get_job(job_id)
        if job is None:
            raise JobNotFoundError(job_id)
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


async def _recover_stuck_scraping_candidates(
    session: async_sessionmaker,
    timeout_minutes: int = SCRAPING_TIMEOUT_MINUTES,
) -> int:
    """Recover candidates stuck in SCRAPING state due to task crash.

    Candidates that have been in SCRAPING state for longer than the timeout
    are reset back to PENDING state so they can be retried.

    Args:
        session: SQLAlchemy async session maker
        timeout_minutes: Number of minutes after which SCRAPING state is considered stuck

    Returns:
        Number of candidates recovered
    """
    cutoff_time = datetime.now(UTC) - timedelta(minutes=timeout_minutes)

    async with session() as db:
        result = await db.execute(
            update(FactCheckedItemCandidate)
            .where(FactCheckedItemCandidate.status == CandidateStatus.SCRAPING.value)
            .where(FactCheckedItemCandidate.updated_at < cutoff_time)
            .values(
                status=CandidateStatus.PENDING.value,
                content=None,
                error_message="Recovered from stuck SCRAPING state",
            )
        )
        await db.commit()
        recovered_count = result.rowcount

        if recovered_count > 0:
            logger.info(
                "Recovered candidates stuck in SCRAPING state",
                extra={
                    "recovered_count": recovered_count,
                    "timeout_minutes": timeout_minutes,
                },
            )

        return recovered_count


async def _recover_stuck_promoting_candidates(
    session: async_sessionmaker,
    timeout_minutes: int = PROMOTING_TIMEOUT_MINUTES,
) -> int:
    """Recover candidates stuck in PROMOTING state due to task crash.

    Candidates that have been in PROMOTING state for longer than the timeout
    are reset back to SCRAPED state so they can be retried.

    Args:
        session: SQLAlchemy async session maker
        timeout_minutes: Number of minutes after which PROMOTING state is considered stuck

    Returns:
        Number of candidates recovered
    """
    cutoff_time = datetime.now(UTC) - timedelta(minutes=timeout_minutes)

    async with session() as db:
        result = await db.execute(
            update(FactCheckedItemCandidate)
            .where(FactCheckedItemCandidate.status == CandidateStatus.PROMOTING.value)
            .where(FactCheckedItemCandidate.updated_at < cutoff_time)
            .values(
                status=CandidateStatus.SCRAPED.value,
                error_message="Recovered from stuck PROMOTING state",
            )
        )
        await db.commit()
        recovered_count = result.rowcount

        if recovered_count > 0:
            logger.info(
                "Recovered candidates stuck in PROMOTING state",
                extra={
                    "recovered_count": recovered_count,
                    "timeout_minutes": timeout_minutes,
                },
            )

        return recovered_count


@register_task(
    task_name="import:fact_check_bureau",
    component="import_pipeline",
    task_type="batch",
    rate_limit_name="import:fact_check",
    rate_limit_capacity="1",
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

    Rate limiting is handled by TaskIQ middleware via @register_task labels.

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

                rows_seen_in_batches = 0
                batch_count = 0

                async with async_session() as db:
                    for batch_num, batch in enumerate(batched(iter(rows), batch_size)):
                        batch_count += 1
                        rows_seen_in_batches += len(batch)

                        candidates, errors = validate_and_normalize_batch(
                            batch, batch_num=batch_num
                        )
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

                logger.info(
                    "Batch processing complete",
                    extra={
                        "job_id": job_id,
                        "batch_count": batch_count,
                        "rows_seen_in_batches": rows_seen_in_batches,
                        "total_rows": stats.total_rows,
                        "valid_rows": stats.valid_rows,
                        "invalid_rows": stats.invalid_rows,
                    },
                )

                if rows_seen_in_batches != stats.total_rows:
                    logger.error(
                        "Row count mismatch: batching lost rows",
                        extra={
                            "job_id": job_id,
                            "total_rows": stats.total_rows,
                            "rows_seen_in_batches": rows_seen_in_batches,
                            "missing": stats.total_rows - rows_seen_in_batches,
                        },
                    )

            row_accounting_valid = _check_row_accounting(job_id, stats, span)

            final_stats = {
                "total_rows": stats.total_rows,
                "valid_rows": stats.valid_rows,
                "invalid_rows": stats.invalid_rows,
                "inserted": stats.inserted,
                "updated": stats.updated,
                "dry_run": dry_run,
                "row_accounting_valid": row_accounting_valid,
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

            try:
                await _fail_job(
                    async_session,
                    progress_tracker,
                    job_uuid,
                    error_summary=error_summary,
                    completed_tasks=stats.valid_rows,
                    failed_tasks=stats.invalid_rows,
                )
            except Exception as fail_error:
                logger.error(
                    "Failed to mark job as failed",
                    extra={
                        "job_id": job_id,
                        "fail_error": str(fail_error),
                        "original_error": error_msg,
                    },
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


async def _scrape_single_url(
    url: str,
    timeout_seconds: float = SCRAPE_URL_TIMEOUT_SECONDS,
) -> str | None:
    """Scrape a single URL with timeout protection.

    Args:
        url: The URL to scrape
        timeout_seconds: Maximum time to wait for scrape

    Returns:
        Scraped content on success, None on timeout or error.
    """
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(scrape_url_content, url),
            timeout=timeout_seconds,
        )
    except TimeoutError:
        logger.warning(f"Scrape timeout for URL: {url}")
        return None
    except Exception as e:
        logger.error(f"Scrape error for URL {url}: {e}")
        return None


@register_task(
    task_name="scrape:candidates",
    component="import_pipeline",
    task_type="batch",
    rate_limit_name="scrape:candidates",
    rate_limit_capacity="1",
)
async def process_scrape_batch(  # noqa: PLR0912
    job_id: str,
    batch_size: int,
    dry_run: bool,
    db_url: str,
    redis_url: str,
    concurrency: int = DEFAULT_SCRAPE_CONCURRENCY,
) -> dict[str, Any]:
    """
    TaskIQ task to process scraping of pending candidates.

    This task:
    1. Recovers candidates stuck in SCRAPING state from previous crashes
    2. Marks job as IN_PROGRESS
    3. Counts total pending candidates without content
    4. In dry_run mode: returns count without scraping
    5. Otherwise: processes candidates with session-per-candidate pattern
    6. For each candidate: scrapes content (non-blocking) and updates status
    7. Tracks progress via BatchJob infrastructure
    8. Marks job as COMPLETED or FAILED

    Rate limiting is handled by TaskIQ middleware via @register_task labels.

    Args:
        job_id: UUID string of the BatchJob for status tracking
        batch_size: Number of candidates to process per batch
        dry_run: If True, count candidates but don't scrape
        db_url: Database connection URL
        redis_url: Redis connection URL for progress tracking
        concurrency: Max concurrent URL scrapes (default: DEFAULT_SCRAPE_CONCURRENCY)

    Returns:
        dict with status and scrape stats
    """
    with _tracer.start_as_current_span("scrape.candidates") as span:
        span.set_attribute("job.id", job_id)
        span.set_attribute("job.batch_size", batch_size)
        span.set_attribute("job.dry_run", dry_run)

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

        scraped = 0
        failed = 0
        total_candidates = 0
        recovered = 0

        try:
            recovered = await _recover_stuck_scraping_candidates(async_session)
            if recovered > 0:
                span.set_attribute("scrape.recovered_stuck", recovered)

            await _start_job(async_session, progress_tracker, job_uuid)

            async with async_session() as db:
                count_query = (
                    select(func.count())
                    .select_from(FactCheckedItemCandidate)
                    .where(FactCheckedItemCandidate.status == CandidateStatus.PENDING.value)
                    .where(FactCheckedItemCandidate.content.is_(None))
                )
                count_result = await db.execute(count_query)
                total_candidates = count_result.scalar_one()

            await _update_job_total_tasks(async_session, job_uuid, total_candidates)
            span.set_attribute("scrape.total_candidates", total_candidates)

            logger.info(
                "Starting candidate scrape batch",
                extra={
                    "job_id": job_id,
                    "batch_size": batch_size,
                    "dry_run": dry_run,
                    "total_candidates": total_candidates,
                    "recovered_stuck": recovered,
                },
            )

            if dry_run:
                final_stats = {
                    "total_candidates": total_candidates,
                    "scraped": 0,
                    "failed": 0,
                    "recovered_stuck": recovered,
                    "dry_run": True,
                }

                await _complete_job(
                    async_session,
                    progress_tracker,
                    job_uuid,
                    completed_tasks=0,
                    failed_tasks=0,
                    stats=final_stats,
                )

                logger.info(
                    "Candidate scrape batch dry run completed",
                    extra={
                        "job_id": job_id,
                        **final_stats,
                    },
                )

                return {"status": "completed", **final_stats}

            semaphore = asyncio.Semaphore(concurrency)
            errors: list[str] = []

            async def process_single_candidate(
                candidate_id: UUID,
                source_url: str,
            ) -> tuple[bool, str | None]:
                """Process a single candidate with semaphore-bounded concurrency."""
                async with semaphore:
                    content = await _scrape_single_url(source_url, SCRAPE_URL_TIMEOUT_SECONDS)

                    async with async_session() as db:
                        if content:
                            await db.execute(
                                update(FactCheckedItemCandidate)
                                .where(FactCheckedItemCandidate.id == candidate_id)
                                .values(
                                    status=CandidateStatus.SCRAPED.value,
                                    content=content,
                                )
                            )
                            await db.commit()
                            logger.debug(
                                "Scraped candidate",
                                extra={
                                    "candidate_id": str(candidate_id),
                                    "content_length": len(content),
                                },
                            )
                            return (True, None)

                        await db.execute(
                            update(FactCheckedItemCandidate)
                            .where(FactCheckedItemCandidate.id == candidate_id)
                            .values(
                                status=CandidateStatus.SCRAPE_FAILED.value,
                                error_message="Scrape returned no content or timed out",
                            )
                        )
                        await db.commit()
                        logger.warning(
                            "Failed to scrape candidate",
                            extra={
                                "candidate_id": str(candidate_id),
                                "source_url": source_url,
                            },
                        )
                        return (False, "Scrape failed")

            progress_interval = max(1, batch_size)

            while True:
                async with async_session() as db:
                    candidate_query = (
                        select(
                            FactCheckedItemCandidate.id,
                            FactCheckedItemCandidate.source_url,
                        )
                        .where(FactCheckedItemCandidate.status == CandidateStatus.PENDING.value)
                        .where(FactCheckedItemCandidate.content.is_(None))
                        .limit(batch_size)
                        .with_for_update(skip_locked=True)
                    )
                    result = await db.execute(candidate_query)
                    candidates = list(result.fetchall())

                    if not candidates:
                        logger.info(f"Job {job_id}: No more candidates to process")
                        break

                    candidate_ids = [c[0] for c in candidates]
                    await db.execute(
                        update(FactCheckedItemCandidate)
                        .where(FactCheckedItemCandidate.id.in_(candidate_ids))
                        .values(status=CandidateStatus.SCRAPING.value)
                    )
                    await db.commit()

                logger.info(
                    f"Job {job_id}: Processing {len(candidates)} candidates in parallel "
                    f"(concurrency={concurrency})"
                )

                tasks = [
                    process_single_candidate(candidate_id, source_url)
                    for candidate_id, source_url in candidates
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                batch_scraped = 0
                batch_failed = 0
                for result in results:
                    if isinstance(result, BaseException):
                        batch_failed += 1
                        errors.append(str(result)[:200])
                        logger.error(f"Job {job_id}: Candidate processing error: {result}")
                    elif result[0]:
                        batch_scraped += 1
                    else:
                        batch_failed += 1
                        if result[1]:
                            errors.append(result[1])

                scraped += batch_scraped
                failed += batch_failed

                processed = scraped + failed
                if processed % progress_interval == 0 or processed == total_candidates:
                    try:
                        await _update_progress(
                            async_session,
                            progress_tracker,
                            job_uuid,
                            completed_tasks=scraped,
                            failed_tasks=failed,
                            current_item=f"Processed {processed}/{total_candidates}",
                        )
                    except Exception as e:
                        logger.warning(
                            "Failed to update progress during scrape batch",
                            extra={
                                "job_id": job_id,
                                "error": str(e),
                            },
                        )

            final_stats = {
                "total_candidates": total_candidates,
                "scraped": scraped,
                "failed": failed,
                "recovered_stuck": recovered,
                "dry_run": False,
            }

            await _complete_job(
                async_session,
                progress_tracker,
                job_uuid,
                completed_tasks=scraped,
                failed_tasks=failed,
                stats=final_stats,
            )

            span.set_attribute("scrape.scraped", scraped)
            span.set_attribute("scrape.failed", failed)

            logger.info(
                "Candidate scrape batch completed",
                extra={
                    "job_id": job_id,
                    **final_stats,
                },
            )

            return {"status": "completed", **final_stats}

        except Exception as e:
            error_msg = str(e)
            span.record_exception(e)
            span.set_status(StatusCode.ERROR, error_msg)

            error_summary = {
                "exception": error_msg,
                "exception_type": type(e).__name__,
                "partial_stats": {
                    "total_candidates": total_candidates,
                    "scraped": scraped,
                    "failed": failed,
                },
            }

            try:
                await _fail_job(
                    async_session,
                    progress_tracker,
                    job_uuid,
                    error_summary=error_summary,
                    completed_tasks=scraped,
                    failed_tasks=failed,
                )
            except Exception as fail_error:
                logger.error(
                    "Failed to mark job as failed",
                    extra={
                        "job_id": job_id,
                        "fail_error": str(fail_error),
                        "original_error": error_msg,
                    },
                )

            logger.error(
                "Candidate scrape batch failed",
                extra={
                    "job_id": job_id,
                    "error": error_msg,
                    "scraped": scraped,
                    "failed": failed,
                },
            )

            raise

        finally:
            await redis_client.disconnect()
            await engine.dispose()


@register_task(
    task_name="promote:candidates",
    component="import_pipeline",
    task_type="batch",
    rate_limit_name="promote:candidates",
    rate_limit_capacity="1",
)
async def process_promotion_batch(
    job_id: str,
    batch_size: int,
    dry_run: bool,
    db_url: str,
    redis_url: str,
) -> dict[str, Any]:
    """
    TaskIQ task to promote scraped candidates to fact_check_items.

    This task:
    1. Marks job as IN_PROGRESS
    2. Counts total promotable candidates (status='scraped', content IS NOT NULL, rating IS NOT NULL)
    3. In dry_run mode: returns count without promoting
    4. Otherwise: processes candidates in batches
    5. For each candidate: calls promote_candidate to create fact_check_item
    6. Tracks progress via BatchJob infrastructure
    7. Marks job as COMPLETED or FAILED

    Rate limiting is handled by TaskIQ middleware via @register_task labels.

    Args:
        job_id: UUID string of the BatchJob for status tracking
        batch_size: Number of candidates to process per batch
        dry_run: If True, count candidates but don't promote
        db_url: Database connection URL
        redis_url: Redis connection URL for progress tracking

    Returns:
        dict with status and promotion stats
    """
    with _tracer.start_as_current_span("promote.candidates") as span:
        span.set_attribute("job.id", job_id)
        span.set_attribute("job.batch_size", batch_size)
        span.set_attribute("job.dry_run", dry_run)

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

        promoted = 0
        failed = 0
        total_candidates = 0
        recovered = 0

        try:
            recovered = await _recover_stuck_promoting_candidates(async_session)
            if recovered > 0:
                span.set_attribute("promote.recovered_stuck", recovered)

            await _start_job(async_session, progress_tracker, job_uuid)

            async with async_session() as db:
                count_query = (
                    select(func.count())
                    .select_from(FactCheckedItemCandidate)
                    .where(FactCheckedItemCandidate.status == CandidateStatus.SCRAPED.value)
                    .where(FactCheckedItemCandidate.content.is_not(None))
                    .where(FactCheckedItemCandidate.content != "")
                    .where(FactCheckedItemCandidate.rating.is_not(None))
                )
                count_result = await db.execute(count_query)
                total_candidates = count_result.scalar_one()

            await _update_job_total_tasks(async_session, job_uuid, total_candidates)
            span.set_attribute("promote.total_candidates", total_candidates)

            logger.info(
                "Starting candidate promotion batch",
                extra={
                    "job_id": job_id,
                    "batch_size": batch_size,
                    "dry_run": dry_run,
                    "total_candidates": total_candidates,
                    "recovered_stuck": recovered,
                },
            )

            if dry_run:
                final_stats = {
                    "total_candidates": total_candidates,
                    "promoted": 0,
                    "failed": 0,
                    "recovered_stuck": recovered,
                    "dry_run": True,
                }

                await _complete_job(
                    async_session,
                    progress_tracker,
                    job_uuid,
                    completed_tasks=0,
                    failed_tasks=0,
                    stats=final_stats,
                )

                logger.info(
                    "Candidate promotion batch dry run completed",
                    extra={
                        "job_id": job_id,
                        **final_stats,
                    },
                )

                return {"status": "completed", **final_stats}

            progress_interval = max(1, batch_size)
            while True:
                async with async_session() as db:
                    candidate_query = (
                        select(FactCheckedItemCandidate.id)
                        .where(FactCheckedItemCandidate.status == CandidateStatus.SCRAPED.value)
                        .where(FactCheckedItemCandidate.content.is_not(None))
                        .where(FactCheckedItemCandidate.content != "")
                        .where(FactCheckedItemCandidate.rating.is_not(None))
                        .limit(1)
                        .with_for_update(skip_locked=True)
                    )
                    result = await db.execute(candidate_query)
                    candidate_row = result.fetchone()

                    if not candidate_row:
                        break

                    candidate_id = candidate_row[0]
                    await db.execute(
                        update(FactCheckedItemCandidate)
                        .where(FactCheckedItemCandidate.id == candidate_id)
                        .values(status=CandidateStatus.PROMOTING.value)
                    )
                    await db.commit()

                async with async_session() as db:
                    success = await promote_candidate(db, candidate_id)

                    if success:
                        promoted += 1
                        logger.debug(
                            "Promoted candidate",
                            extra={
                                "candidate_id": str(candidate_id),
                            },
                        )
                    else:
                        failed += 1
                        logger.warning(
                            "Failed to promote candidate",
                            extra={
                                "candidate_id": str(candidate_id),
                            },
                        )

                processed = promoted + failed
                if processed % progress_interval == 0:
                    try:
                        await _update_progress(
                            async_session,
                            progress_tracker,
                            job_uuid,
                            completed_tasks=promoted,
                            failed_tasks=failed,
                            current_item=f"Processed {processed}/{total_candidates}",
                        )
                    except Exception as e:
                        logger.warning(
                            "Failed to update progress during promotion batch",
                            extra={
                                "job_id": job_id,
                                "error": str(e),
                            },
                        )

            final_stats = {
                "total_candidates": total_candidates,
                "promoted": promoted,
                "failed": failed,
                "recovered_stuck": recovered,
                "dry_run": False,
            }

            await _complete_job(
                async_session,
                progress_tracker,
                job_uuid,
                completed_tasks=promoted,
                failed_tasks=failed,
                stats=final_stats,
            )

            span.set_attribute("promote.promoted", promoted)
            span.set_attribute("promote.failed", failed)

            logger.info(
                "Candidate promotion batch completed",
                extra={
                    "job_id": job_id,
                    **final_stats,
                },
            )

            return {"status": "completed", **final_stats}

        except Exception as e:
            error_msg = str(e)
            span.record_exception(e)
            span.set_status(StatusCode.ERROR, error_msg)

            error_summary = {
                "exception": error_msg,
                "exception_type": type(e).__name__,
                "partial_stats": {
                    "total_candidates": total_candidates,
                    "promoted": promoted,
                    "failed": failed,
                },
            }

            try:
                await _fail_job(
                    async_session,
                    progress_tracker,
                    job_uuid,
                    error_summary=error_summary,
                    completed_tasks=promoted,
                    failed_tasks=failed,
                )
            except Exception as fail_error:
                logger.error(
                    "Failed to mark job as failed",
                    extra={
                        "job_id": job_id,
                        "fail_error": str(fail_error),
                        "original_error": error_msg,
                    },
                )

            logger.error(
                "Candidate promotion batch failed",
                extra={
                    "job_id": job_id,
                    "error": error_msg,
                    "promoted": promoted,
                    "failed": failed,
                },
            )

            raise

        finally:
            await redis_client.disconnect()
            await engine.dispose()
