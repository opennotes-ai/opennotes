"""
TaskIQ tasks for bulk candidate approval operations.

Handles background processing of bulk approval from predicted ratings with:
- Batch processing for memory efficiency
- Progress tracking via BatchJob infrastructure
- Partial failure handling with error aggregation

Tasks are designed to be self-contained, creating their own database and Redis
connections to work reliably in distributed worker environments.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.sql.elements import ColumnElement

from opentelemetry import trace
from sqlalchemy import and_, bindparam, cast, func, select, update
from sqlalchemy.dialects.postgresql import ARRAY as PG_ARRAY
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.types import Text

from src.batch_jobs.constants import BULK_APPROVAL_JOB_TYPE
from src.batch_jobs.progress_tracker import BatchJobProgressTracker
from src.batch_jobs.service import BatchJobService
from src.cache.redis_client import RedisClient
from src.fact_checking.candidate_models import FactCheckedItemCandidate
from src.fact_checking.import_pipeline.candidate_service import extract_high_confidence_rating
from src.fact_checking.import_pipeline.promotion import promote_candidate
from src.monitoring import get_logger
from src.tasks.broker import register_task

logger = get_logger(__name__)
_tracer = trace.get_tracer(__name__)

MAX_STORED_ERRORS = 50
BATCH_SIZE = 100
PROGRESS_UPDATE_INTERVAL = 50


class JobNotFoundError(Exception):
    """Raised when a batch job is not found."""

    def __init__(self, job_id: UUID) -> None:
        self.job_id = job_id
        super().__init__(f"Batch job not found: {job_id}")


async def _start_job(
    session: async_sessionmaker,
    progress_tracker: BatchJobProgressTracker,
    job_id: UUID,
) -> None:
    """Transition job from PENDING to IN_PROGRESS."""
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


def _build_approval_filters(
    status: str | None,
    dataset_name: str | None,
    dataset_tags: list[str] | None,
    has_content: bool | None,
    published_date_from: datetime | None,
    published_date_to: datetime | None,
) -> "list[ColumnElement[bool]]":
    """Build SQLAlchemy filters for bulk approval query."""
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


def _parse_iso_date(date_str: str | None) -> datetime | None:
    """Parse ISO 8601 date string, handling Z timezone."""
    if not date_str:
        return None
    return datetime.fromisoformat(date_str.replace("Z", "+00:00"))


async def _process_single_batch(
    db: "AsyncSession",
    batch: list[FactCheckedItemCandidate],
    threshold: float,
    auto_promote: bool,
    errors: list[str],
) -> tuple[int, int, int, int]:
    """Process a single batch of candidates for approval.

    Uses bulk UPDATE for efficiency and tracks actual rows affected.
    Promotions run within the same transaction context but are best-effort;
    a promotion failure does not roll back the rating update.

    The commit is deferred until after all promotions complete to maintain
    row locks throughout the entire batch operation. This prevents concurrent
    jobs from selecting the same rows via skip_locked.

    Returns:
        Tuple of (updated_count, promoted_count, failed_count, processed_count)
        where processed_count is the number of candidates that met the threshold.
    """
    updated_count = 0
    promoted_count = 0
    failed_count = 0
    processed_count = 0

    batch_updates: list[dict[str, Any]] = []
    candidates_to_promote: list[UUID] = []

    for candidate in batch:
        rating = extract_high_confidence_rating(candidate.predicted_ratings, threshold)
        if rating is not None:
            batch_updates.append({"id": candidate.id, "rating": rating})
            if auto_promote:
                candidates_to_promote.append(candidate.id)
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
            failed_count = len(batch_updates)
            if len(errors) < MAX_STORED_ERRORS:
                errors.append(f"Bulk update failed for {len(batch_updates)} candidates: {e!s}")

    if auto_promote and candidates_to_promote:
        for candidate_id in candidates_to_promote:
            try:
                promoted = await promote_candidate(db, candidate_id)
                if promoted:
                    promoted_count += 1
            except Exception as e:
                failed_count += 1
                if len(errors) < MAX_STORED_ERRORS:
                    errors.append(f"Failed to promote {candidate_id}: {e!s}")

    await db.commit()

    return updated_count, promoted_count, failed_count, processed_count


@register_task(
    task_name=BULK_APPROVAL_JOB_TYPE,
    component="fact_checking",
    task_type="batch",
    rate_limit_name="approve:candidates",
    rate_limit_capacity="1",
)
async def process_bulk_approval(
    job_id: str,
    threshold: float,
    auto_promote: bool,
    limit: int,
    status: str | None,
    dataset_name: str | None,
    dataset_tags: list[str] | None,
    has_content: bool | None,
    published_date_from: str | None,
    published_date_to: str | None,
    db_url: str,
    redis_url: str,
) -> dict[str, Any]:
    """Process bulk approval of candidates from predicted ratings.

    This task runs asynchronously and updates progress via BatchJob infrastructure.

    Limit Semantics:
        The `limit` parameter controls the maximum number of candidates that will
        be *approved* (i.e., have their rating set from predicted_ratings). This is
        distinct from the number of candidates *scanned*: if many candidates have
        predictions below the threshold, the job may scan more rows than it approves.

        The loop terminates when either:
        - `limit` candidates have been approved (met the threshold)
        - No more candidates match the filters
        - Maximum iterations reached (safety guard against infinite loops)

    Args:
        job_id: UUID of the BatchJob tracking this operation
        threshold: Minimum prediction probability to approve (0.0-1.0)
        auto_promote: Whether to promote approved candidates
        limit: Maximum number of candidates to *approve* (not scan)
        status: Filter by candidate status
        dataset_name: Filter by dataset name
        dataset_tags: Filter by dataset tags
        has_content: Filter by content presence
        published_date_from: Filter by published date (ISO 8601 string)
        published_date_to: Filter by published date (ISO 8601 string)
        db_url: Database connection URL
        redis_url: Redis connection URL

    Returns:
        Dict with approval stats (updated_count, promoted_count, errors)
    """
    job_uuid = UUID(job_id)

    updated_count = 0
    promoted_count = 0
    failed_count = 0
    errors: list[str] = []

    with _tracer.start_as_current_span("process_bulk_approval") as span:
        span.set_attribute("job_id", job_id)
        span.set_attribute("threshold", threshold)
        span.set_attribute("auto_promote", auto_promote)
        span.set_attribute("limit", limit)

        engine = create_async_engine(
            db_url,
            echo=False,
            pool_size=5,
            max_overflow=10,
        )
        async_session = async_sessionmaker(engine, expire_on_commit=False)

        redis_client = RedisClient()
        await redis_client.connect(redis_url)
        progress_tracker = BatchJobProgressTracker(redis_client)

        try:
            await _start_job(async_session, progress_tracker, job_uuid)

            filters = _build_approval_filters(
                status=status,
                dataset_name=dataset_name,
                dataset_tags=dataset_tags,
                has_content=has_content,
                published_date_from=_parse_iso_date(published_date_from),
                published_date_to=_parse_iso_date(published_date_to),
            )

            async with async_session() as db:
                count_query = select(func.count()).select_from(
                    select(FactCheckedItemCandidate.id)
                    .where(and_(*filters))
                    .limit(limit)
                    .subquery()
                )
                result = await db.execute(count_query)
                total_matching = result.scalar() or 0

            await _update_job_total_tasks(async_session, job_uuid, total_matching)
            span.set_attribute("total_matching", total_matching)

            if total_matching == 0:
                await _complete_job(
                    async_session,
                    progress_tracker,
                    job_uuid,
                    completed_tasks=0,
                    failed_tasks=0,
                    stats={"updated_count": 0, "promoted_count": 0},
                )
                return {"updated_count": 0, "promoted_count": 0}

            remaining = limit
            last_processed_id: UUID | None = None
            total_scanned = 0
            max_iterations = (limit // BATCH_SIZE) + 10
            iteration_count = 0

            while remaining > 0 and iteration_count < max_iterations:
                iteration_count += 1
                async with async_session() as db:
                    query = select(FactCheckedItemCandidate).where(and_(*filters))

                    if last_processed_id is not None:
                        query = query.where(FactCheckedItemCandidate.id > last_processed_id)

                    query = (
                        query.order_by(FactCheckedItemCandidate.id)
                        .limit(min(BATCH_SIZE, remaining))
                        .with_for_update(skip_locked=True)
                    )

                    result = await db.execute(query)
                    batch = list(result.scalars().all())

                    if not batch:
                        break

                    last_processed_id = batch[-1].id
                    total_scanned += len(batch)

                    (
                        batch_updated,
                        batch_promoted,
                        batch_failed,
                        processed,
                    ) = await _process_single_batch(db, batch, threshold, auto_promote, errors)
                    updated_count += batch_updated
                    promoted_count += batch_promoted
                    failed_count += batch_failed
                    remaining -= processed

                    should_update = total_scanned % PROGRESS_UPDATE_INTERVAL == 0
                    if should_update or not batch:
                        await _update_progress(
                            async_session,
                            progress_tracker,
                            job_uuid,
                            completed_tasks=updated_count,
                            failed_tasks=failed_count,
                            current_item=f"Scanned {total_scanned}, updated {updated_count} candidates",
                        )

            if iteration_count >= max_iterations:
                logger.warning(
                    "Bulk approval reached max iterations",
                    extra={
                        "job_id": job_id,
                        "iteration_count": iteration_count,
                        "max_iterations": max_iterations,
                        "remaining": remaining,
                        "total_scanned": total_scanned,
                    },
                )

            stats = {
                "updated_count": updated_count,
                "promoted_count": promoted_count if auto_promote else None,
                "threshold": threshold,
                "total_scanned": total_scanned,
                "iterations": iteration_count,
            }

            if errors:
                stats["errors"] = errors[:MAX_STORED_ERRORS]
                stats["total_errors"] = len(errors)

            await _complete_job(
                async_session,
                progress_tracker,
                job_uuid,
                completed_tasks=updated_count,
                failed_tasks=failed_count,
                stats=stats,
            )

            span.set_attribute("updated_count", updated_count)
            span.set_attribute("promoted_count", promoted_count)
            span.set_attribute("failed_count", failed_count)

            logger.info(
                "Bulk approval job completed",
                extra={
                    "job_id": job_id,
                    "updated_count": updated_count,
                    "promoted_count": promoted_count,
                    "failed_count": failed_count,
                    "threshold": threshold,
                },
            )

            return stats

        except JobNotFoundError:
            logger.error("Bulk approval job not found", extra={"job_id": job_id})
            raise

        except Exception as e:
            logger.exception("Bulk approval job failed", extra={"job_id": job_id})
            span.record_exception(e)

            await _fail_job(
                async_session,
                progress_tracker,
                job_uuid,
                error_summary={"error": str(e), "type": type(e).__name__},
                completed_tasks=updated_count,
                failed_tasks=failed_count,
            )
            raise

        finally:
            await redis_client.disconnect()
            await engine.dispose()
