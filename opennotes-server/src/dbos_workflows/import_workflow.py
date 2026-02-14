"""DBOS workflows for fact-check import pipeline.

Replaces TaskIQ-based import tasks with durable DBOS execution.
Three workflows cover the full import lifecycle:
1. fact_check_import_workflow: CSV streaming, validation, and upsert
2. scrape_candidates_workflow: Batch URL scraping with concurrency control
3. promote_candidates_workflow: Batch candidate promotion to fact-check items

Architecture:
    ImportBatchJobService              DBOS Worker
        |                                  |
        | client.enqueue(import_wf)       |
        | -----> (queued)                  |
        |         start_import_step -----> |
        |         import_csv_step -------> |
        |         (progress updates)       |
        |         (finalize)               |

    All workflows follow the BatchJob lifecycle:
    PENDING -> IN_PROGRESS -> COMPLETED/FAILED

    Progress tracking uses synchronous helpers that call async DB
    operations via run_sync(). Updates are fire-and-forget to avoid
    blocking workflow execution on transient DB errors.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

from dbos import DBOS, EnqueueOptions, Queue

from src.batch_jobs.constants import (
    DEFAULT_SCRAPE_CONCURRENCY,
)
from src.monitoring import get_logger
from src.utils.async_compat import run_sync

logger = get_logger(__name__)

import_pipeline_queue = Queue(
    name="import_pipeline",
    worker_concurrency=1,
    concurrency=3,
)

SCRAPING_TIMEOUT_MINUTES = 120
PROMOTING_TIMEOUT_MINUTES = 120
PROGRESS_UPDATE_INTERVAL = 100


def _update_batch_job_progress_sync(
    batch_job_id: UUID,
    completed_tasks: int,
    failed_tasks: int,
    current_item: str | None = None,
) -> bool:
    from src.batch_jobs.service import BatchJobService
    from src.database import get_session_maker

    async def _async_impl() -> bool:
        async with get_session_maker()() as db:
            service = BatchJobService(db)
            await service.update_progress(
                batch_job_id,
                completed_tasks=completed_tasks,
                failed_tasks=failed_tasks,
                current_item=current_item,
            )
            await db.commit()
            return True

    try:
        return run_sync(_async_impl())
    except Exception as e:
        logger.error(
            "Failed to update batch job progress",
            extra={"batch_job_id": str(batch_job_id), "error": str(e)},
            exc_info=True,
        )
        return False


def _finalize_batch_job_sync(
    batch_job_id: UUID,
    success: bool,
    completed_tasks: int,
    failed_tasks: int,
    error_summary: dict[str, Any] | None = None,
    stats: dict[str, Any] | None = None,
) -> bool:
    from src.batch_jobs.service import BatchJobService
    from src.database import get_session_maker

    async def _async_impl() -> bool:
        async with get_session_maker()() as db:
            service = BatchJobService(db)
            job = await service.get_job(batch_job_id)
            if job and stats:
                job.metadata_ = {**(job.metadata_ or {}), "stats": stats}  # pyright: ignore[reportAttributeAccessIssue]
            if success:
                await service.complete_job(
                    batch_job_id,
                    completed_tasks=completed_tasks,
                    failed_tasks=failed_tasks,
                )
            else:
                await service.update_progress(
                    batch_job_id,
                    completed_tasks=completed_tasks,
                    failed_tasks=failed_tasks,
                )
                await service.fail_job(batch_job_id, error_summary)
            await db.commit()
            return True

    try:
        return run_sync(_async_impl())
    except Exception as e:
        logger.error(
            "Failed to finalize batch job",
            extra={"batch_job_id": str(batch_job_id), "error": str(e)},
            exc_info=True,
        )
        return False


def _start_batch_job_sync(batch_job_id: UUID) -> bool:
    from src.batch_jobs.service import BatchJobService
    from src.database import get_session_maker

    async def _async_impl() -> bool:
        async with get_session_maker()() as db:
            service = BatchJobService(db)
            job = await service.get_job(batch_job_id)
            if job is None:
                raise ValueError(f"Batch job not found: {batch_job_id}")
            await service.start_job(batch_job_id)
            await db.commit()
            return True

    try:
        return run_sync(_async_impl())
    except Exception as e:
        logger.error(
            "Failed to start batch job",
            extra={"batch_job_id": str(batch_job_id), "error": str(e)},
            exc_info=True,
        )
        return False


def _update_job_total_tasks_sync(batch_job_id: UUID, total_tasks: int) -> bool:
    from src.batch_jobs.service import BatchJobService
    from src.database import get_session_maker

    async def _async_impl() -> bool:
        async with get_session_maker()() as db:
            service = BatchJobService(db)
            job = await service.get_job(batch_job_id)
            if job:
                job.total_tasks = total_tasks
                await db.commit()
            return True

    try:
        return run_sync(_async_impl())
    except Exception as e:
        logger.error(
            "Failed to update job total_tasks",
            extra={
                "batch_job_id": str(batch_job_id),
                "total_tasks": total_tasks,
                "error": str(e),
            },
        )
        return False


# ---------------------------------------------------------------------------
# Workflow 1: fact_check_import_workflow
# ---------------------------------------------------------------------------


@DBOS.step()
def start_import_step(batch_job_id: str) -> bool:
    job_uuid = UUID(batch_job_id)
    return _start_batch_job_sync(job_uuid)


@DBOS.step()
def import_csv_step(
    batch_job_id: str,
    batch_size: int,
    dry_run: bool,
    enqueue_scrapes: bool,
) -> dict[str, Any]:
    from src.fact_checking.import_pipeline.importer import (
        HUGGINGFACE_DATASET_URL,
        ImportStats,
        batched,
        parse_csv_rows,
        stream_csv_from_url,
        upsert_candidates,
        validate_and_normalize_batch,
    )
    from src.tasks.import_tasks import _check_row_accounting

    job_uuid = UUID(batch_job_id)

    async def _import() -> dict[str, Any]:
        from src.database import get_session_maker

        stats = ImportStats(errors=[])
        all_errors: list[str] = []

        async for content in stream_csv_from_url(HUGGINGFACE_DATASET_URL):
            rows = list(parse_csv_rows(content))
            stats.total_rows = len(rows)

            _update_job_total_tasks_sync(job_uuid, stats.total_rows)

            logger.info(
                "Loaded CSV content",
                extra={
                    "job_id": batch_job_id,
                    "total_rows": stats.total_rows,
                },
            )

            rows_seen_in_batches = 0
            batch_count = 0

            async with get_session_maker()() as db:
                for batch_num, batch in enumerate(batched(iter(rows), batch_size)):
                    batch_count += 1
                    rows_seen_in_batches += len(batch)

                    candidates, errors = validate_and_normalize_batch(batch, batch_num=batch_num)
                    stats.valid_rows += len(candidates)
                    stats.invalid_rows += len(errors)
                    all_errors.extend(errors)

                    if not dry_run and candidates:
                        inserted, updated = await upsert_candidates(db, candidates)
                        stats.inserted += inserted
                        stats.updated += updated

                    processed = min((batch_num + 1) * batch_size, stats.total_rows)

                    _update_batch_job_progress_sync(
                        job_uuid,
                        completed_tasks=stats.valid_rows,
                        failed_tasks=stats.invalid_rows,
                        current_item=f"Batch {batch_num + 1} ({processed}/{stats.total_rows})",
                    )

                    if processed % 10000 == 0 or processed >= stats.total_rows:
                        logger.info(
                            "Import progress",
                            extra={
                                "job_id": batch_job_id,
                                "processed": processed,
                                "total": stats.total_rows,
                                "valid": stats.valid_rows,
                                "invalid": stats.invalid_rows,
                            },
                        )

            if rows_seen_in_batches != stats.total_rows:
                logger.error(
                    "Row count mismatch: batching lost rows",
                    extra={
                        "job_id": batch_job_id,
                        "total_rows": stats.total_rows,
                        "rows_seen_in_batches": rows_seen_in_batches,
                    },
                )

        _check_row_accounting(batch_job_id, stats)

        final_stats: dict[str, Any] = {
            "total_rows": stats.total_rows,
            "valid_rows": stats.valid_rows,
            "invalid_rows": stats.invalid_rows,
            "inserted": stats.inserted,
            "updated": stats.updated,
            "dry_run": dry_run,
        }

        if all_errors:
            from src.tasks.import_tasks import _aggregate_errors

            final_stats["errors"] = _aggregate_errors(all_errors)

        if enqueue_scrapes and not dry_run:
            from src.fact_checking.import_pipeline.scrape_tasks import (
                enqueue_scrape_batch,
            )

            scrape_result = await enqueue_scrape_batch(batch_size=batch_size)
            final_stats["scrapes_enqueued"] = scrape_result.get("enqueued", 0)

        return final_stats

    return run_sync(_import())


@DBOS.workflow()
def fact_check_import_workflow(
    batch_job_id: str,
    batch_size: int,
    dry_run: bool,
    enqueue_scrapes: bool,
) -> dict[str, Any]:
    workflow_id = DBOS.workflow_id
    job_uuid = UUID(batch_job_id)

    logger.info(
        "Starting fact-check import workflow",
        extra={
            "workflow_id": workflow_id,
            "batch_job_id": batch_job_id,
            "batch_size": batch_size,
            "dry_run": dry_run,
            "enqueue_scrapes": enqueue_scrapes,
        },
    )

    started = start_import_step(batch_job_id)
    if not started:
        _finalize_batch_job_sync(
            job_uuid,
            success=False,
            completed_tasks=0,
            failed_tasks=0,
            error_summary={"stage": "start", "error": "Failed to start batch job"},
        )
        return {"status": "failed", "error": "Failed to start batch job"}

    try:
        final_stats = import_csv_step(
            batch_job_id=batch_job_id,
            batch_size=batch_size,
            dry_run=dry_run,
            enqueue_scrapes=enqueue_scrapes,
        )

        _finalize_batch_job_sync(
            job_uuid,
            success=True,
            completed_tasks=final_stats.get("valid_rows", 0),
            failed_tasks=final_stats.get("invalid_rows", 0),
            stats=final_stats,
        )

        logger.info(
            "Fact-check import workflow completed",
            extra={
                "workflow_id": workflow_id,
                "batch_job_id": batch_job_id,
                **final_stats,
            },
        )

        return {"status": "completed", **final_stats}

    except Exception as e:
        error_summary = {
            "exception": str(e),
            "exception_type": type(e).__name__,
            "stage": "import_csv",
        }

        _finalize_batch_job_sync(
            job_uuid,
            success=False,
            completed_tasks=0,
            failed_tasks=0,
            error_summary=error_summary,
        )

        logger.error(
            "Fact-check import workflow failed",
            extra={
                "workflow_id": workflow_id,
                "batch_job_id": batch_job_id,
                "error": str(e),
            },
        )

        raise


# ---------------------------------------------------------------------------
# Workflow 2: scrape_candidates_workflow
# ---------------------------------------------------------------------------


@DBOS.step()
def recover_and_count_scrape_step(batch_job_id: str) -> dict[str, Any]:
    from src.tasks.import_tasks import _recover_stuck_scraping_candidates

    job_uuid = UUID(batch_job_id)

    async def _impl() -> dict[str, Any]:
        from sqlalchemy import func, select

        from src.database import get_session_maker
        from src.fact_checking.candidate_models import CandidateStatus, FactCheckedItemCandidate

        session_maker = get_session_maker()

        recovered = await _recover_stuck_scraping_candidates(session_maker)

        _start_batch_job_sync(job_uuid)

        async with session_maker() as db:
            count_query = (
                select(func.count())
                .select_from(FactCheckedItemCandidate)
                .where(
                    FactCheckedItemCandidate.status.in_(
                        [
                            CandidateStatus.PENDING.value,
                            CandidateStatus.SCRAPING.value,
                        ]
                    )
                )
                .where(FactCheckedItemCandidate.content.is_(None))
            )
            count_result = await db.execute(count_query)
            total_candidates = count_result.scalar_one()

        _update_job_total_tasks_sync(job_uuid, total_candidates)

        return {
            "recovered": recovered,
            "total_candidates": total_candidates,
        }

    return run_sync(_impl())


@DBOS.step()
def process_scrape_batch_step(
    batch_job_id: str,
    batch_size: int,
    concurrency: int,
    base_delay: float,
    total_candidates: int,
    scraped_so_far: int,
    failed_so_far: int,
) -> dict[str, Any]:
    job_uuid = UUID(batch_job_id)

    async def _process() -> dict[str, Any]:
        from sqlalchemy import select
        from sqlalchemy import update as sa_update

        from src.database import get_session_maker
        from src.fact_checking.candidate_models import CandidateStatus, FactCheckedItemCandidate
        from src.fact_checking.import_pipeline.scrape_tasks import (
            scrape_url_content,
        )

        session_maker = get_session_maker()
        scraped = scraped_so_far
        failed = failed_so_far

        while True:
            async with session_maker() as db:
                subquery = (
                    select(FactCheckedItemCandidate.id)
                    .where(FactCheckedItemCandidate.status == CandidateStatus.PENDING.value)
                    .where(FactCheckedItemCandidate.content.is_(None))
                    .limit(batch_size)
                    .with_for_update(skip_locked=True)
                )
                stmt = (
                    sa_update(FactCheckedItemCandidate)
                    .where(FactCheckedItemCandidate.id.in_(subquery))
                    .values(status=CandidateStatus.SCRAPING.value)
                    .returning(
                        FactCheckedItemCandidate.id,
                        FactCheckedItemCandidate.source_url,
                    )
                )
                result = await db.execute(stmt)
                candidates = list(result.fetchall())
                await db.commit()

                if not candidates:
                    break

            logger.info(
                "Processing scrape batch",
                extra={
                    "job_id": batch_job_id,
                    "batch_size": len(candidates),
                    "concurrency": concurrency,
                },
            )

            semaphore = asyncio.Semaphore(concurrency)

            async def scrape_single(
                candidate_id: UUID,
                source_url: str,
                _semaphore: asyncio.Semaphore = semaphore,
            ) -> tuple[bool, str | None]:
                async with _semaphore:
                    if base_delay > 0:
                        await asyncio.sleep(base_delay)
                    content = await asyncio.to_thread(scrape_url_content, source_url)

                    async with session_maker() as db:
                        if content:
                            await db.execute(
                                sa_update(FactCheckedItemCandidate)
                                .where(FactCheckedItemCandidate.id == candidate_id)
                                .values(
                                    status=CandidateStatus.SCRAPED.value,
                                    content=content,
                                )
                            )
                            await db.commit()
                            return (True, None)

                        await db.execute(
                            sa_update(FactCheckedItemCandidate)
                            .where(FactCheckedItemCandidate.id == candidate_id)
                            .values(
                                status=CandidateStatus.SCRAPE_FAILED.value,
                                error_message="Scrape returned no content",
                            )
                        )
                        await db.commit()
                        return (False, "Scrape failed")

            tasks = [
                scrape_single(candidate_id, source_url) for candidate_id, source_url in candidates
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for r in results:
                if isinstance(r, BaseException):
                    failed += 1
                elif r[0]:
                    scraped += 1
                else:
                    failed += 1

            processed = scraped + failed
            _update_batch_job_progress_sync(
                job_uuid,
                completed_tasks=scraped,
                failed_tasks=failed,
                current_item=f"Processed {processed}/{total_candidates}",
            )

        return {
            "scraped": scraped,
            "failed": failed,
        }

    return run_sync(_process())


@DBOS.workflow()
def scrape_candidates_workflow(
    batch_job_id: str,
    batch_size: int,
    dry_run: bool,
    concurrency: int = DEFAULT_SCRAPE_CONCURRENCY,
    base_delay: float = 1.0,
) -> dict[str, Any]:
    workflow_id = DBOS.workflow_id
    job_uuid = UUID(batch_job_id)

    logger.info(
        "Starting scrape candidates workflow",
        extra={
            "workflow_id": workflow_id,
            "batch_job_id": batch_job_id,
            "batch_size": batch_size,
            "dry_run": dry_run,
            "concurrency": concurrency,
        },
    )

    try:
        init_result = recover_and_count_scrape_step(batch_job_id)
        total_candidates = init_result["total_candidates"]
        recovered = init_result["recovered"]

        if dry_run:
            final_stats = {
                "total_candidates": total_candidates,
                "scraped": 0,
                "failed": 0,
                "recovered_stuck": recovered,
                "dry_run": True,
            }
            _finalize_batch_job_sync(
                job_uuid,
                success=True,
                completed_tasks=0,
                failed_tasks=0,
                stats=final_stats,
            )

            logger.info(
                "Scrape candidates dry run completed",
                extra={"workflow_id": workflow_id, **final_stats},
            )
            return {"status": "completed", **final_stats}

        scrape_result = process_scrape_batch_step(
            batch_job_id=batch_job_id,
            batch_size=batch_size,
            concurrency=concurrency,
            base_delay=base_delay,
            total_candidates=total_candidates,
            scraped_so_far=0,
            failed_so_far=0,
        )

        scraped = scrape_result["scraped"]
        failed = scrape_result["failed"]

        final_stats = {
            "total_candidates": total_candidates,
            "scraped": scraped,
            "failed": failed,
            "recovered_stuck": recovered,
            "dry_run": False,
        }

        _finalize_batch_job_sync(
            job_uuid,
            success=True,
            completed_tasks=scraped,
            failed_tasks=failed,
            stats=final_stats,
        )

        logger.info(
            "Scrape candidates workflow completed",
            extra={
                "workflow_id": workflow_id,
                "batch_job_id": batch_job_id,
                **final_stats,
            },
        )

        return {"status": "completed", **final_stats}

    except Exception as e:
        error_summary = {
            "exception": str(e),
            "exception_type": type(e).__name__,
            "stage": "scrape",
        }

        _finalize_batch_job_sync(
            job_uuid,
            success=False,
            completed_tasks=0,
            failed_tasks=0,
            error_summary=error_summary,
        )

        logger.error(
            "Scrape candidates workflow failed",
            extra={
                "workflow_id": workflow_id,
                "batch_job_id": batch_job_id,
                "error": str(e),
            },
        )

        raise


# ---------------------------------------------------------------------------
# Workflow 3: promote_candidates_workflow
# ---------------------------------------------------------------------------


@DBOS.step()
def recover_and_count_promote_step(batch_job_id: str) -> dict[str, Any]:
    from src.tasks.import_tasks import _recover_stuck_promoting_candidates

    job_uuid = UUID(batch_job_id)

    async def _impl() -> dict[str, Any]:
        from sqlalchemy import func, select

        from src.database import get_session_maker
        from src.fact_checking.candidate_models import CandidateStatus, FactCheckedItemCandidate

        session_maker = get_session_maker()

        recovered = await _recover_stuck_promoting_candidates(session_maker)

        _start_batch_job_sync(job_uuid)

        async with session_maker() as db:
            count_query = (
                select(func.count())
                .select_from(FactCheckedItemCandidate)
                .where(
                    FactCheckedItemCandidate.status.in_(
                        [
                            CandidateStatus.SCRAPED.value,
                            CandidateStatus.PROMOTING.value,
                        ]
                    )
                )
                .where(FactCheckedItemCandidate.content.is_not(None))
                .where(FactCheckedItemCandidate.content != "")
                .where(FactCheckedItemCandidate.rating.is_not(None))
            )
            count_result = await db.execute(count_query)
            total_candidates = count_result.scalar_one()

        _update_job_total_tasks_sync(job_uuid, total_candidates)

        return {
            "recovered": recovered,
            "total_candidates": total_candidates,
        }

    return run_sync(_impl())


@DBOS.step()
def process_promotion_batch_step(
    batch_job_id: str,
    batch_size: int,
    total_candidates: int,
) -> dict[str, Any]:
    job_uuid = UUID(batch_job_id)

    async def _process() -> dict[str, Any]:
        from sqlalchemy import select
        from sqlalchemy import update as sa_update

        from src.database import get_session_maker
        from src.fact_checking.candidate_models import CandidateStatus, FactCheckedItemCandidate
        from src.fact_checking.import_pipeline.promotion import promote_candidate

        session_maker = get_session_maker()
        promoted = 0
        failed = 0

        while True:
            async with session_maker() as db:
                subquery = (
                    select(FactCheckedItemCandidate.id)
                    .where(FactCheckedItemCandidate.status == CandidateStatus.SCRAPED.value)
                    .where(FactCheckedItemCandidate.content.is_not(None))
                    .where(FactCheckedItemCandidate.content != "")
                    .where(FactCheckedItemCandidate.rating.is_not(None))
                    .limit(batch_size)
                    .with_for_update(skip_locked=True)
                )
                stmt = (
                    sa_update(FactCheckedItemCandidate)
                    .where(FactCheckedItemCandidate.id.in_(subquery))
                    .values(status=CandidateStatus.PROMOTING.value)
                    .returning(FactCheckedItemCandidate.id)
                )
                result = await db.execute(stmt)
                candidate_ids = [row[0] for row in result.fetchall()]
                await db.commit()

                if not candidate_ids:
                    break

            for candidate_id in candidate_ids:
                async with session_maker() as db:
                    success = await promote_candidate(db, candidate_id)

                    if success:
                        promoted += 1
                    else:
                        failed += 1

            processed = promoted + failed
            _update_batch_job_progress_sync(
                job_uuid,
                completed_tasks=promoted,
                failed_tasks=failed,
                current_item=f"Processed {processed}/{total_candidates}",
            )

        return {
            "promoted": promoted,
            "failed": failed,
        }

    return run_sync(_process())


@DBOS.workflow()
def promote_candidates_workflow(
    batch_job_id: str,
    batch_size: int,
    dry_run: bool,
) -> dict[str, Any]:
    workflow_id = DBOS.workflow_id
    job_uuid = UUID(batch_job_id)

    logger.info(
        "Starting promote candidates workflow",
        extra={
            "workflow_id": workflow_id,
            "batch_job_id": batch_job_id,
            "batch_size": batch_size,
            "dry_run": dry_run,
        },
    )

    try:
        init_result = recover_and_count_promote_step(batch_job_id)
        total_candidates = init_result["total_candidates"]
        recovered = init_result["recovered"]

        if dry_run:
            final_stats = {
                "total_candidates": total_candidates,
                "promoted": 0,
                "failed": 0,
                "recovered_stuck": recovered,
                "dry_run": True,
            }
            _finalize_batch_job_sync(
                job_uuid,
                success=True,
                completed_tasks=0,
                failed_tasks=0,
                stats=final_stats,
            )

            logger.info(
                "Promote candidates dry run completed",
                extra={"workflow_id": workflow_id, **final_stats},
            )
            return {"status": "completed", **final_stats}

        promote_result = process_promotion_batch_step(
            batch_job_id=batch_job_id,
            batch_size=batch_size,
            total_candidates=total_candidates,
        )

        promoted = promote_result["promoted"]
        failed = promote_result["failed"]

        final_stats = {
            "total_candidates": total_candidates,
            "promoted": promoted,
            "failed": failed,
            "recovered_stuck": recovered,
            "dry_run": False,
        }

        _finalize_batch_job_sync(
            job_uuid,
            success=True,
            completed_tasks=promoted,
            failed_tasks=failed,
            stats=final_stats,
        )

        logger.info(
            "Promote candidates workflow completed",
            extra={
                "workflow_id": workflow_id,
                "batch_job_id": batch_job_id,
                **final_stats,
            },
        )

        return {"status": "completed", **final_stats}

    except Exception as e:
        error_summary = {
            "exception": str(e),
            "exception_type": type(e).__name__,
            "stage": "promote",
        }

        _finalize_batch_job_sync(
            job_uuid,
            success=False,
            completed_tasks=0,
            failed_tasks=0,
            error_summary=error_summary,
        )

        logger.error(
            "Promote candidates workflow failed",
            extra={
                "workflow_id": workflow_id,
                "batch_job_id": batch_job_id,
                "error": str(e),
            },
        )

        raise


# ---------------------------------------------------------------------------
# Dispatch helpers (async, used by ImportBatchJobService)
# ---------------------------------------------------------------------------


async def dispatch_import_workflow(
    batch_job_id: UUID,
    batch_size: int,
    dry_run: bool,
    enqueue_scrapes: bool,
) -> str:
    from src.dbos_workflows.config import get_dbos_client

    client = get_dbos_client()
    options: EnqueueOptions = {
        "queue_name": "import_pipeline",
        "workflow_name": FACT_CHECK_IMPORT_WORKFLOW_NAME,
    }
    handle = await asyncio.to_thread(
        client.enqueue,
        options,
        str(batch_job_id),
        batch_size,
        dry_run,
        enqueue_scrapes,
    )

    logger.info(
        "Import workflow dispatched via DBOS",
        extra={
            "batch_job_id": str(batch_job_id),
            "workflow_id": handle.workflow_id,
        },
    )

    return handle.workflow_id


async def dispatch_scrape_workflow(
    batch_job_id: UUID,
    batch_size: int,
    dry_run: bool,
    concurrency: int = DEFAULT_SCRAPE_CONCURRENCY,
    base_delay: float = 1.0,
) -> str:
    from src.dbos_workflows.config import get_dbos_client

    client = get_dbos_client()
    options: EnqueueOptions = {
        "queue_name": "import_pipeline",
        "workflow_name": SCRAPE_CANDIDATES_WORKFLOW_NAME,
    }
    handle = await asyncio.to_thread(
        client.enqueue,
        options,
        str(batch_job_id),
        batch_size,
        dry_run,
        concurrency,
        base_delay,
    )

    logger.info(
        "Scrape workflow dispatched via DBOS",
        extra={
            "batch_job_id": str(batch_job_id),
            "workflow_id": handle.workflow_id,
        },
    )

    return handle.workflow_id


async def dispatch_promote_workflow(
    batch_job_id: UUID,
    batch_size: int,
    dry_run: bool,
) -> str:
    from src.dbos_workflows.config import get_dbos_client

    client = get_dbos_client()
    options: EnqueueOptions = {
        "queue_name": "import_pipeline",
        "workflow_name": PROMOTE_CANDIDATES_WORKFLOW_NAME,
    }
    handle = await asyncio.to_thread(
        client.enqueue,
        options,
        str(batch_job_id),
        batch_size,
        dry_run,
    )

    logger.info(
        "Promote workflow dispatched via DBOS",
        extra={
            "batch_job_id": str(batch_job_id),
            "workflow_id": handle.workflow_id,
        },
    )

    return handle.workflow_id


FACT_CHECK_IMPORT_WORKFLOW_NAME: str = fact_check_import_workflow.__qualname__
SCRAPE_CANDIDATES_WORKFLOW_NAME: str = scrape_candidates_workflow.__qualname__
PROMOTE_CANDIDATES_WORKFLOW_NAME: str = promote_candidates_workflow.__qualname__
