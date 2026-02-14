"""
TaskIQ tasks for fact-check import operations.

DEPRECATED: Task bodies have been migrated to DBOS durable workflows
in src/dbos_workflows/import_workflow.py (TASK-1093).

The @register_task decorated functions remain as no-op stubs to drain
legacy JetStream messages. Helper functions (_check_row_accounting,
_recover_stuck_*_candidates, _aggregate_errors, etc.) are retained
because they are used by the DBOS workflow steps.

Remove deprecated stubs after 2026-04-01 when all legacy messages
have been drained.
"""

from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

from sqlalchemy import CursorResult, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.fact_checking.candidate_models import CandidateStatus, FactCheckedItemCandidate
from src.fact_checking.import_pipeline.importer import ImportStats
from src.monitoring import get_logger
from src.tasks.broker import register_task

logger = get_logger(__name__)

MAX_STORED_ERRORS = 50
SCRAPING_TIMEOUT_MINUTES = 120
PROMOTING_TIMEOUT_MINUTES = 120


def _check_row_accounting(
    job_id: str,
    stats: ImportStats,
    span: Any = None,
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
    if span is not None:
        span.set_attribute("import.row_mismatch", True)
        span.set_attribute("import.missing_rows", missing)
    return False


class JobNotFoundError(Exception):
    """Raised when a batch job is not found."""

    def __init__(self, job_id: UUID) -> None:
        self.job_id = job_id
        super().__init__(f"Batch job not found: {job_id}")


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
    session: async_sessionmaker[AsyncSession],
    timeout_minutes: int = SCRAPING_TIMEOUT_MINUTES,
) -> int:
    """Recover candidates stuck in SCRAPING state due to task crash.

    Candidates that have been in SCRAPING state for longer than the timeout
    are reset back to PENDING state so they can be retried.

    Uses SELECT FOR UPDATE SKIP LOCKED to avoid resetting candidates that are
    actively being processed by another worker (which would hold a row lock).

    Args:
        session: SQLAlchemy async session maker
        timeout_minutes: Number of minutes after which SCRAPING state is considered stuck

    Returns:
        Number of candidates recovered
    """
    cutoff_time = datetime.now(UTC) - timedelta(minutes=timeout_minutes)

    async with session() as db:
        subquery = (
            select(FactCheckedItemCandidate.id)
            .where(FactCheckedItemCandidate.status == CandidateStatus.SCRAPING.value)
            .where(FactCheckedItemCandidate.updated_at < cutoff_time)
            .with_for_update(skip_locked=True)
        )
        result = cast(
            CursorResult[Any],
            await db.execute(
                update(FactCheckedItemCandidate)
                .where(FactCheckedItemCandidate.id.in_(subquery))
                .values(
                    status=CandidateStatus.PENDING.value,
                    content=None,
                    error_message="Recovered from stuck SCRAPING state",
                )
            ),
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
    session: async_sessionmaker[AsyncSession],
    timeout_minutes: int = PROMOTING_TIMEOUT_MINUTES,
) -> int:
    """Recover candidates stuck in PROMOTING state due to task crash.

    Candidates that have been in PROMOTING state for longer than the timeout
    are reset back to SCRAPED state so they can be retried.

    Uses SELECT FOR UPDATE SKIP LOCKED to avoid resetting candidates that are
    actively being processed by another worker (which would hold a row lock).

    Args:
        session: SQLAlchemy async session maker
        timeout_minutes: Number of minutes after which PROMOTING state is considered stuck

    Returns:
        Number of candidates recovered
    """
    cutoff_time = datetime.now(UTC) - timedelta(minutes=timeout_minutes)

    async with session() as db:
        subquery = (
            select(FactCheckedItemCandidate.id)
            .where(FactCheckedItemCandidate.status == CandidateStatus.PROMOTING.value)
            .where(FactCheckedItemCandidate.updated_at < cutoff_time)
            .with_for_update(skip_locked=True)
        )
        result = cast(
            CursorResult[Any],
            await db.execute(
                update(FactCheckedItemCandidate)
                .where(FactCheckedItemCandidate.id.in_(subquery))
                .values(
                    status=CandidateStatus.SCRAPED.value,
                    error_message="Recovered from stuck PROMOTING state",
                )
            ),
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
    task_type="deprecated",
)
async def process_fact_check_import(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Deprecated no-op handler to drain legacy messages from pre-DBOS migration.

    This task was migrated to DBOS in TASK-1093. This handler exists only to
    acknowledge and discard stale messages in the JetStream queue.

    The task will automatically ACK the message after this function returns,
    preventing infinite redelivery of legacy messages.

    Remove after 2026-04-01 when all legacy messages have been drained.
    """
    logger.info(
        "Received deprecated import:fact_check_bureau message - discarding",
        extra={
            "task_name": "import:fact_check_bureau",
            "args_count": len(args),
            "kwargs_keys": list(kwargs.keys()) if kwargs else [],
            "migration_note": "Task migrated to DBOS in TASK-1093",
        },
    )
    return {"status": "discarded", "migration_note": "Task migrated to DBOS in TASK-1093"}


@register_task(
    task_name="scrape:candidates",
    component="import_pipeline",
    task_type="deprecated",
)
async def process_scrape_batch(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Deprecated no-op handler to drain legacy messages from pre-DBOS migration.

    This task was migrated to DBOS in TASK-1093. This handler exists only to
    acknowledge and discard stale messages in the JetStream queue.

    The task will automatically ACK the message after this function returns,
    preventing infinite redelivery of legacy messages.

    Remove after 2026-04-01 when all legacy messages have been drained.
    """
    logger.info(
        "Received deprecated scrape:candidates message - discarding",
        extra={
            "task_name": "scrape:candidates",
            "args_count": len(args),
            "kwargs_keys": list(kwargs.keys()) if kwargs else [],
            "migration_note": "Task migrated to DBOS in TASK-1093",
        },
    )
    return {"status": "discarded", "migration_note": "Task migrated to DBOS in TASK-1093"}


@register_task(
    task_name="promote:candidates",
    component="import_pipeline",
    task_type="deprecated",
)
async def process_promotion_batch(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Deprecated no-op handler to drain legacy messages from pre-DBOS migration.

    This task was migrated to DBOS in TASK-1093. This handler exists only to
    acknowledge and discard stale messages in the JetStream queue.

    The task will automatically ACK the message after this function returns,
    preventing infinite redelivery of legacy messages.

    Remove after 2026-04-01 when all legacy messages have been drained.
    """
    logger.info(
        "Received deprecated promote:candidates message - discarding",
        extra={
            "task_name": "promote:candidates",
            "args_count": len(args),
            "kwargs_keys": list(kwargs.keys()) if kwargs else [],
            "migration_note": "Task migrated to DBOS in TASK-1093",
        },
    )
    return {"status": "discarded", "migration_note": "Task migrated to DBOS in TASK-1093"}
