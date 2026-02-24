"""DBOS workflow for bulk candidate approval.

Replaces the TaskIQ-based bulk approval task with durable DBOS execution.
Batch processing is checkpointed per-batch, enabling resume from the last
completed batch on workflow restart.

The dispatch function lives in src/batch_jobs/import_service.py, which
creates the BatchJob record and enqueues this workflow via DBOSClient.

``limit`` semantics
-------------------
The *limit* parameter means "approve up to N candidates".  Because
cursor-based pagination advances past ALL scanned rows (not just those
meeting the threshold), the actual number of approved candidates may be
fewer than *limit* when the threshold match-rate is low.  In the presence
of DBOS step retries the count is approximate: already-approved candidates
are naturally filtered out by the ``rating IS NULL`` predicate, but the
in-memory ``remaining`` counter is not refreshed from the database between
retries.  For exact counts, query the BatchJob record after completion.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from dbos import DBOS, Queue
from sqlalchemy import and_, bindparam, cast, func, select, update
from sqlalchemy.dialects.postgresql import ARRAY as PG_ARRAY
from sqlalchemy.types import Text

from src.dbos_workflows.batch_job_helpers import (
    finalize_batch_job_sync,
    start_batch_job_sync,
    update_batch_job_progress_sync,
)
from src.dbos_workflows.circuit_breaker import CircuitBreaker, CircuitOpenError
from src.dbos_workflows.token_bucket.config import WorkflowWeight
from src.dbos_workflows.token_bucket.gate import TokenGate
from src.fact_checking.candidate_models import FactCheckedItemCandidate
from src.fact_checking.import_pipeline.candidate_service import extract_high_confidence_rating
from src.monitoring import get_logger
from src.utils.async_compat import run_sync

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.sql.elements import ColumnElement

logger = get_logger(__name__)

approval_queue = Queue(
    name="approval",
    worker_concurrency=3,
    concurrency=6,
)
"""Queue configuration for approval workflows.

``worker_concurrency=1`` means each DBOS worker thread processes one workflow at a
time.  ``concurrency=2`` allows two workflows to be in-flight across all workers,
enabling overlap when one workflow is blocked on I/O while another proceeds.  The
net effect is near-serial execution with a small degree of pipelining; this keeps
database lock contention low while still allowing throughput when the queue backs up.
"""

BATCH_SIZE: int = 100
"""Number of candidates fetched per batch step (cursor-based pagination window)."""

MAX_STORED_ERRORS: int = 50
"""Maximum error strings retained in the BatchJob error_summary JSON column."""

PROGRESS_UPDATE_INTERVAL: int = 50
"""Write a BatchJob progress row every N scanned candidates.

The modulo check ``total_scanned % PROGRESS_UPDATE_INTERVAL == 0`` may skip the
final batch if its size is not a multiple of this interval.  The loop compensates
by also writing progress when ``remaining <= 0`` (see the while-loop footer).
"""

STEP_RETRIES_ALLOWED: bool = True
STEP_MAX_ATTEMPTS: int = 3
STEP_INTERVAL_SECONDS: float = 2.0
STEP_BACKOFF_RATE: float = 2.0


def _parse_iso_date(date_str: str | None) -> datetime | None:
    if not date_str:
        return None
    return datetime.fromisoformat(date_str.replace("Z", "+00:00"))


def _build_approval_filters(
    status: str | None,
    dataset_name: str | None,
    dataset_tags: list[str] | None,
    has_content: bool | None,
    published_date_from: datetime | None,
    published_date_to: datetime | None,
) -> list[ColumnElement[bool]]:
    filters: list[ColumnElement[bool]] = [
        FactCheckedItemCandidate.rating.is_(None),
        FactCheckedItemCandidate.predicted_ratings.is_not(None),
    ]

    if status:
        filters.append(FactCheckedItemCandidate.status == status)
    if dataset_name:
        filters.append(FactCheckedItemCandidate.dataset_name == dataset_name)
    if dataset_tags:
        filters.append(
            cast(FactCheckedItemCandidate.dataset_tags, PG_ARRAY(Text)).overlap(
                cast(dataset_tags, PG_ARRAY(Text))
            )
        )
    if has_content is True:
        filters.append(FactCheckedItemCandidate.content.is_not(None))
    elif has_content is False:
        filters.append(FactCheckedItemCandidate.content.is_(None))
    if published_date_from:
        filters.append(FactCheckedItemCandidate.published_date >= published_date_from)
    if published_date_to:
        filters.append(FactCheckedItemCandidate.published_date <= published_date_to)

    return filters


async def _process_single_batch(
    db: AsyncSession,
    batch: list[FactCheckedItemCandidate],
    threshold: float,
    auto_promote: bool,
    errors: list[str],
) -> tuple[int, int, int, int]:
    """Process a single batch of candidates for approval.

    Uses bulk UPDATE for efficiency and tracks actual rows affected.
    Each promotion runs inside a SAVEPOINT so that a single failure does
    not roll back the rating update or other successful promotions.

    Returns:
        Tuple of (updated_count, promoted_count, failed_count, processed_count)
        where processed_count is the number of candidates that met the threshold.
    """
    from src.fact_checking.import_pipeline.promotion import promote_candidate

    updated_count = 0
    promoted_count = 0
    failed_count = 0
    processed_count = 0

    batch_updates: list[dict[str, Any]] = []
    candidates_to_promote: list[UUID] = []

    for candidate in batch:
        cid = candidate.id
        rating = extract_high_confidence_rating(candidate.predicted_ratings, threshold)
        if rating is not None:
            batch_updates.append({"id": cid, "rating": rating})
            if auto_promote:
                candidates_to_promote.append(cid)
            processed_count += 1

    if batch_updates:
        try:
            stmt = (
                update(FactCheckedItemCandidate)
                .where(FactCheckedItemCandidate.id == bindparam("id"))
                .where(FactCheckedItemCandidate.rating.is_(None))
                .values(rating=bindparam("rating"), updated_at=func.now())
                .execution_options(synchronize_session=False)
            )
            await db.execute(stmt, batch_updates)
            updated_count = len(batch_updates)
        except Exception as e:
            await db.rollback()
            failed_count = len(batch_updates)
            if len(errors) < MAX_STORED_ERRORS:
                errors.append(f"Bulk update failed for {len(batch_updates)} candidates: {e!s}")
            return updated_count, promoted_count, failed_count, processed_count

    if auto_promote and candidates_to_promote:
        for candidate_id in candidates_to_promote:
            try:
                async with db.begin_nested():
                    promoted = await promote_candidate(db, candidate_id)
                    if promoted:
                        promoted_count += 1
            except Exception as e:
                failed_count += 1
                if len(errors) < MAX_STORED_ERRORS:
                    errors.append(f"Failed to promote {candidate_id}: {e!s}")

    await db.commit()

    return updated_count, promoted_count, failed_count, processed_count


@DBOS.step(
    retries_allowed=STEP_RETRIES_ALLOWED,
    max_attempts=STEP_MAX_ATTEMPTS,
    interval_seconds=STEP_INTERVAL_SECONDS,
    backoff_rate=STEP_BACKOFF_RATE,
)
def count_approval_candidates_step(
    status: str | None,
    dataset_name: str | None,
    dataset_tags: list[str] | None,
    has_content: bool | None,
    published_date_from: str | None,
    published_date_to: str | None,
    limit: int,
) -> int:
    """Count candidates matching approval filters.

    Returns the number of candidates that match (capped at limit).
    """
    from src.database import get_session_maker

    async def _count() -> int:
        filters = _build_approval_filters(
            status=status,
            dataset_name=dataset_name,
            dataset_tags=dataset_tags,
            has_content=has_content,
            published_date_from=_parse_iso_date(published_date_from),
            published_date_to=_parse_iso_date(published_date_to),
        )

        async with get_session_maker()() as db:
            count_query = select(func.count()).select_from(
                select(FactCheckedItemCandidate.id).where(and_(*filters)).limit(limit).subquery()
            )
            result = await db.execute(count_query)
            return result.scalar() or 0

    return run_sync(_count())


@DBOS.step(
    retries_allowed=STEP_RETRIES_ALLOWED,
    max_attempts=STEP_MAX_ATTEMPTS,
    interval_seconds=STEP_INTERVAL_SECONDS,
    backoff_rate=STEP_BACKOFF_RATE,
)
def process_approval_batch_step(
    threshold: float,
    auto_promote: bool,
    status: str | None,
    dataset_name: str | None,
    dataset_tags: list[str] | None,
    has_content: bool | None,
    published_date_from: str | None,
    published_date_to: str | None,
    last_processed_id: str | None,
    remaining: int,
    errors_so_far: list[str],
) -> dict[str, Any]:
    """Process one batch of candidates for approval.

    Uses cursor-based pagination with FOR UPDATE SKIP LOCKED.

    Returns:
        dict with: updated, promoted, failed, processed, last_id,
                   total_scanned, errors
    """
    from src.database import get_session_maker

    async def _process() -> dict[str, Any]:
        filters = _build_approval_filters(
            status=status,
            dataset_name=dataset_name,
            dataset_tags=dataset_tags,
            has_content=has_content,
            published_date_from=_parse_iso_date(published_date_from),
            published_date_to=_parse_iso_date(published_date_to),
        )

        async with get_session_maker()() as db:
            query = select(FactCheckedItemCandidate).where(and_(*filters))

            if last_processed_id is not None:
                query = query.where(FactCheckedItemCandidate.id > UUID(last_processed_id))

            query = (
                query.order_by(FactCheckedItemCandidate.id)
                .limit(min(BATCH_SIZE, remaining))
                .with_for_update(skip_locked=True)
            )

            result = await db.execute(query)
            batch = list(result.scalars().all())

            if not batch:
                return {
                    "updated": 0,
                    "promoted": 0,
                    "failed": 0,
                    "processed": 0,
                    "last_id": last_processed_id,
                    "scanned": 0,
                    "errors": errors_so_far,
                    "empty": True,
                }

            new_last_id = str(batch[-1].id)
            errors = list(errors_so_far)

            batch_updated, batch_promoted, batch_failed, processed = await _process_single_batch(
                db, batch, threshold, auto_promote, errors
            )

            return {
                "updated": batch_updated,
                "promoted": batch_promoted,
                "failed": batch_failed,
                "processed": processed,
                "last_id": new_last_id,
                "scanned": len(batch),
                "errors": errors,
                "empty": False,
            }

    return run_sync(_process())


def _finalize_and_warn(
    job_uuid: UUID,
    workflow_id: str,
    batch_job_id: str,
    **kwargs: Any,
) -> None:
    if not finalize_batch_job_sync(job_uuid, **kwargs):
        logger.warning(
            "finalize_batch_job_sync returned False",
            extra={"workflow_id": workflow_id, "batch_job_id": batch_job_id},
        )


@DBOS.workflow()
def bulk_approval_workflow(  # noqa: PLR0912
    batch_job_id: str,
    threshold: float,
    auto_promote: bool,
    limit: int,
    status: str | None,
    dataset_name: str | None,
    dataset_tags: list[str] | None,
    has_content: bool | None,
    published_date_from: str | None,
    published_date_to: str | None,
) -> dict[str, Any]:
    """DBOS workflow for bulk approval of fact-check candidates.

    Processes candidates in batches with cursor-based pagination.
    Each batch is a checkpointed DBOS step for durability.

    CircuitOpenError handling: This workflow catches CircuitOpenError and
    breaks out of the loop gracefully, marking the job as FAILED. This
    differs from rechunk workflows which re-raise CircuitOpenError. The
    difference is intentional: approval workflows manage their own BatchJob
    lifecycle (start/finalize), so they must finalize before exiting.
    Rechunk workflows delegate finalization to the caller on circuit trip.

    Retry / limit interaction: ``limit`` is approximate across DBOS step
    retries.  If ``process_approval_batch_step`` commits but fails before
    returning, DBOS replays the step.  The cursor-based pagination and the
    ``rating IS NULL`` filter naturally skip already-approved candidates,
    so duplicates are not produced.  However the in-memory ``remaining``
    counter is not refreshed from the DB, so the final approved count may
    slightly exceed ``limit``.  For exact post-hoc counts query the
    BatchJob record.

    Args:
        batch_job_id: UUID of the BatchJob record (as string)
        threshold: Minimum prediction probability to approve (0.0-1.0)
        auto_promote: Whether to promote approved candidates
        limit: Maximum candidates to scan (approve up to N; see module
            docstring for semantics)
        status: Filter by candidate status
        dataset_name: Filter by dataset name
        dataset_tags: Filter by dataset tags
        has_content: Filter by content presence
        published_date_from: ISO 8601 date string filter
        published_date_to: ISO 8601 date string filter

    Returns:
        dict with approval stats
    """
    gate = TokenGate(pool="default", weight=WorkflowWeight.APPROVAL)
    gate.acquire()
    try:
        workflow_id = DBOS.workflow_id
        assert workflow_id is not None
        job_uuid = UUID(batch_job_id)

        logger.info(
            "Starting bulk approval workflow",
            extra={
                "workflow_id": workflow_id,
                "batch_job_id": batch_job_id,
                "threshold": threshold,
                "auto_promote": auto_promote,
                "limit": limit,
            },
        )

        circuit_breaker = CircuitBreaker(
            threshold=5,
            reset_timeout=60,
        )

        total_matching = count_approval_candidates_step(
            status=status,
            dataset_name=dataset_name,
            dataset_tags=dataset_tags,
            has_content=has_content,
            published_date_from=published_date_from,
            published_date_to=published_date_to,
            limit=limit,
        )

        if not start_batch_job_sync(job_uuid, total_matching):
            logger.error(
                "Failed to start batch job - aborting workflow",
                extra={"workflow_id": workflow_id, "batch_job_id": batch_job_id},
            )
            _finalize_and_warn(
                job_uuid,
                workflow_id,
                batch_job_id,
                success=False,
                completed_tasks=0,
                failed_tasks=0,
                error_summary={"error": "Failed to transition job to IN_PROGRESS"},
            )
            return {"updated_count": 0, "promoted_count": 0, "error": "job_start_failed"}

        if total_matching == 0:
            _finalize_and_warn(
                job_uuid,
                workflow_id,
                batch_job_id,
                success=True,
                completed_tasks=0,
                failed_tasks=0,
                stats={"updated_count": 0, "promoted_count": 0},
            )

            logger.info(
                "Bulk approval workflow completed - no matching candidates",
                extra={"workflow_id": workflow_id, "batch_job_id": batch_job_id},
            )

            return {"updated_count": 0, "promoted_count": 0}

        updated_count = 0
        promoted_count = 0
        failed_count = 0
        total_scanned = 0
        circuit_breaker_tripped = False
        errors: list[str] = []
        last_processed_id: str | None = None
        remaining = limit
        max_iterations = (limit // BATCH_SIZE) * 10 + 20
        iteration_count = 0

        while remaining > 0 and iteration_count < max_iterations:
            iteration_count += 1

            try:
                circuit_breaker.check()
            except CircuitOpenError:
                circuit_breaker_tripped = True
                logger.error(
                    "Circuit breaker open - aborting bulk approval workflow",
                    extra={
                        "workflow_id": workflow_id,
                        "batch_job_id": batch_job_id,
                        "consecutive_failures": circuit_breaker.failures,
                    },
                )
                update_batch_job_progress_sync(
                    job_uuid,
                    completed_tasks=updated_count,
                    failed_tasks=failed_count,
                )
                break

            try:
                batch_result = process_approval_batch_step(
                    threshold=threshold,
                    auto_promote=auto_promote,
                    status=status,
                    dataset_name=dataset_name,
                    dataset_tags=dataset_tags,
                    has_content=has_content,
                    published_date_from=published_date_from,
                    published_date_to=published_date_to,
                    last_processed_id=last_processed_id,
                    remaining=remaining,
                    errors_so_far=errors,
                )

                if batch_result.get("empty", False):
                    break

                updated_count += batch_result["updated"]
                promoted_count += batch_result["promoted"]
                failed_count += batch_result["failed"]
                total_scanned += batch_result["scanned"]
                last_processed_id = batch_result["last_id"]
                remaining -= batch_result["scanned"]
                errors = batch_result["errors"]

                circuit_breaker.record_success()

            except Exception as e:
                failed_count += 1
                circuit_breaker.record_failure()
                if len(errors) < MAX_STORED_ERRORS:
                    errors.append(f"Batch step failed: {e!s}")
                logger.warning(
                    "Approval batch step failed",
                    extra={
                        "workflow_id": workflow_id,
                        "batch_job_id": batch_job_id,
                        "iteration": iteration_count,
                        "error": str(e),
                    },
                )

            should_update = total_scanned > 0 and total_scanned % PROGRESS_UPDATE_INTERVAL == 0
            if should_update or remaining <= 0:
                update_batch_job_progress_sync(
                    job_uuid,
                    completed_tasks=updated_count,
                    failed_tasks=failed_count,
                    current_item=f"Scanned {total_scanned}, updated {updated_count} candidates",
                )

        if iteration_count >= max_iterations:
            logger.warning(
                "Bulk approval reached max iterations",
                extra={
                    "workflow_id": workflow_id,
                    "batch_job_id": batch_job_id,
                    "iteration_count": iteration_count,
                    "max_iterations": max_iterations,
                    "remaining": remaining,
                    "total_scanned": total_scanned,
                },
            )

        stats: dict[str, Any] = {
            "updated_count": updated_count,
            "promoted_count": promoted_count if auto_promote else None,
            "threshold": threshold,
            "total_scanned": total_scanned,
            "iterations": iteration_count,
            "circuit_breaker_tripped": circuit_breaker_tripped,
        }

        if errors:
            stats["errors"] = errors[:MAX_STORED_ERRORS]
            stats["total_errors"] = len(errors)

        success = not circuit_breaker_tripped and not (updated_count == 0 and failed_count > 0)
        error_summary = None
        if not success:
            error_summary = {"errors": errors[:MAX_STORED_ERRORS], "total_errors": len(errors)}
            if circuit_breaker_tripped:
                error_summary["circuit_breaker_tripped"] = True

        _finalize_and_warn(
            job_uuid,
            workflow_id,
            batch_job_id,
            success=success,
            completed_tasks=updated_count,
            failed_tasks=failed_count,
            error_summary=error_summary,
            stats=stats,
        )

        logger.info(
            "Bulk approval workflow completed",
            extra={
                "workflow_id": workflow_id,
                "batch_job_id": batch_job_id,
                "updated_count": updated_count,
                "promoted_count": promoted_count,
                "failed_count": failed_count,
                "threshold": threshold,
            },
        )

        return stats
    finally:
        gate.release()


BULK_APPROVAL_WORKFLOW_NAME: str = bulk_approval_workflow.__qualname__


async def dispatch_bulk_approval_workflow(
    batch_job_id: UUID,
    threshold: float,
    auto_promote: bool,
    limit: int,
    status: str | None = None,
    dataset_name: str | None = None,
    dataset_tags: list[str] | None = None,
    has_content: bool | None = None,
    published_date_from: str | None = None,
    published_date_to: str | None = None,
) -> str:
    """Dispatch a DBOS bulk approval workflow via DBOSClient.enqueue().

    Mirrors the dispatch pattern used by rechunk workflows
    (dispatch_dbos_rechunk_workflow). Enqueues the workflow on the
    approval queue for durable processing by a DBOS worker.

    Args:
        batch_job_id: UUID of the BatchJob record
        threshold: Minimum prediction probability to approve
        auto_promote: Whether to promote approved candidates
        limit: Maximum candidates to process
        status: Optional candidate status filter
        dataset_name: Optional dataset name filter
        dataset_tags: Optional dataset tags filter
        has_content: Optional content presence filter
        published_date_from: Optional ISO 8601 date filter
        published_date_to: Optional ISO 8601 date filter

    Returns:
        The DBOS workflow_id

    Raises:
        Exception: If workflow dispatch fails
    """
    import asyncio

    from dbos import EnqueueOptions

    from src.dbos_workflows.config import get_dbos_client

    client = get_dbos_client()
    options: EnqueueOptions = {
        "queue_name": "approval",
        "workflow_name": BULK_APPROVAL_WORKFLOW_NAME,
    }
    handle = await asyncio.to_thread(
        client.enqueue,
        options,
        str(batch_job_id),
        threshold,
        auto_promote,
        limit,
        status,
        dataset_name,
        dataset_tags,
        has_content,
        published_date_from,
        published_date_to,
    )

    logger.info(
        "DBOS bulk approval workflow dispatched",
        extra={
            "batch_job_id": str(batch_job_id),
            "workflow_id": handle.workflow_id,
        },
    )

    return handle.workflow_id
