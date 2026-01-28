"""DBOS workflow for rechunking fact-check items.

This workflow replaces the TaskIQ-based rechunk task with durable
DBOS execution. Each item is processed as a step with automatic
checkpointing, enabling resume from the last completed item.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any
from uuid import UUID

from dbos import DBOS, Queue

from src.dbos_workflows.circuit_breaker import CircuitBreaker, CircuitOpenError
from src.monitoring import get_logger

if TYPE_CHECKING:
    from src.dbos_workflows.batch_job_adapter import BatchJobDBOSAdapter

logger = get_logger(__name__)

rechunk_queue = Queue(
    name="rechunk",
    worker_concurrency=2,
    concurrency=10,
)

EMBEDDING_RETRY_CONFIG = {
    "retries_allowed": True,
    "max_attempts": 5,
    "interval_seconds": 1.0,
    "backoff_rate": 2.0,
}

_batch_job_adapter: BatchJobDBOSAdapter | None = None


def get_batch_job_adapter() -> BatchJobDBOSAdapter:
    """Get or create the BatchJob adapter singleton.

    Lazy initialization to avoid circular imports and allow testing with mocks.
    """
    global _batch_job_adapter
    if _batch_job_adapter is None:
        from src.dbos_workflows.batch_job_adapter import BatchJobDBOSAdapter

        _batch_job_adapter = BatchJobDBOSAdapter()
    return _batch_job_adapter


def _run_async_chunk_and_embed(
    fact_check_id: UUID,
    community_server_id: UUID | None,
) -> dict[str, Any]:
    """Run the async chunk and embed operation synchronously.

    This is extracted to make testing easier (can be mocked).
    """
    async def _async_impl() -> dict[str, Any]:
        from src.config import get_settings
        from src.database import get_session_maker
        from src.fact_checking.chunk_embedding_service import ChunkEmbeddingService
        from src.fact_checking.chunking_service import ChunkingService
        from src.fact_checking.models import FactCheckItem
        from src.llm_config.encryption import EncryptionService
        from src.llm_config.manager import LLMClientManager
        from src.llm_config.service import LLMService

        settings = get_settings()
        llm_client_manager = LLMClientManager(
            encryption_service=EncryptionService(settings.ENCRYPTION_MASTER_KEY)
        )
        llm_service = LLMService(client_manager=llm_client_manager)
        chunking_service = ChunkingService()
        service = ChunkEmbeddingService(
            chunking_service=chunking_service,
            llm_service=llm_service,
        )

        session_maker = get_session_maker()
        async with session_maker() as db:
            fact_check = await db.get(FactCheckItem, fact_check_id)
            if fact_check is None:
                raise ValueError(f"FactCheckItem not found: {fact_check_id}")

            content = fact_check.content or ""
            if not content.strip():
                return {"chunks_created": 0}

            chunks = await service.chunk_and_embed_fact_check(
                db=db,
                fact_check_id=fact_check_id,
                text=content,
                community_server_id=community_server_id,
            )

            await db.commit()

            return {"chunks_created": len(chunks)}

    return asyncio.run(_async_impl())


def chunk_and_embed_fact_check_sync(
    fact_check_id: UUID,
    community_server_id: UUID | None,
) -> dict[str, Any]:
    """Synchronous wrapper for chunk_and_embed_fact_check.

    DBOS steps are synchronous, so we need to wrap the async service method.
    """
    return _run_async_chunk_and_embed(fact_check_id, community_server_id)


def _process_fact_check_item_impl(
    item_id: str,
    community_server_id: str | None,
) -> dict[str, Any]:
    """Core logic for processing a fact-check item.

    This function contains the actual business logic and can be tested
    without DBOS initialization.

    Args:
        item_id: FactCheckItem UUID as string
        community_server_id: Optional community server for LLM credentials

    Returns:
        dict with success boolean and optional error message
    """
    try:
        result = chunk_and_embed_fact_check_sync(
            fact_check_id=UUID(item_id),
            community_server_id=UUID(community_server_id) if community_server_id else None,
        )

        return {
            "success": True,
            "item_id": item_id,
            "chunks_created": result.get("chunks_created", 0),
        }

    except Exception as e:
        logger.warning(
            "Failed to process fact-check item",
            extra={"item_id": item_id, "error": str(e)},
        )
        raise


@DBOS.step(**EMBEDDING_RETRY_CONFIG)
def process_fact_check_item(
    item_id: str,
    community_server_id: str | None,
) -> dict[str, Any]:
    """Process a single fact-check item (DBOS step with retry).

    This step is automatically checkpointed by DBOS. If the workflow
    is interrupted, it will resume from the last completed step.

    Retry schedule: 1s, 2s, 4s, 8s, 16s (5 attempts total)

    Args:
        item_id: FactCheckItem UUID as string
        community_server_id: Optional community server for LLM credentials

    Returns:
        dict with success boolean and optional error message
    """
    return _process_fact_check_item_impl(item_id, community_server_id)


def _rechunk_workflow_impl(
    batch_job_id: str,
    community_server_id: str | None,
    item_ids: list[str],
    batch_size: int = 100,
    workflow_id: str | None = None,
    process_item_func: Any = None,
) -> dict[str, Any]:
    """Core logic for rechunk workflow.

    This function contains the actual business logic and can be tested
    without DBOS initialization. The DBOS-decorated wrapper calls this
    with appropriate parameters.

    Args:
        batch_job_id: UUID of the BatchJob record (as string)
        community_server_id: Optional community server for LLM credentials
        item_ids: List of FactCheckItem UUIDs to process
        batch_size: Items per batch (for progress reporting)
        workflow_id: Optional workflow ID for logging (from DBOS context)
        process_item_func: Function to process each item (allows mocking in tests)

    Returns:
        dict with completed_count, failed_count, and any errors
    """
    if process_item_func is None:
        process_item_func = process_fact_check_item

    total_items = len(item_ids)

    logger.info(
        "Starting rechunk workflow",
        extra={
            "workflow_id": workflow_id,
            "batch_job_id": batch_job_id,
            "total_items": total_items,
        },
    )

    adapter = get_batch_job_adapter()
    adapter.update_status_sync(UUID(batch_job_id), "in_progress")

    circuit_breaker = CircuitBreaker(
        threshold=5,
        reset_timeout=60,
    )

    completed_count = 0
    failed_count = 0
    errors: list[dict[str, Any]] = []

    for i, item_id in enumerate(item_ids):
        try:
            circuit_breaker.check()

            result = process_item_func(
                item_id=item_id,
                community_server_id=community_server_id,
            )

            if result["success"]:
                completed_count += 1
                circuit_breaker.record_success()
            else:
                failed_count += 1
                errors.append({"item_id": item_id, "error": result.get("error")})

        except CircuitOpenError:
            logger.error(
                "Circuit breaker open - pausing workflow",
                extra={
                    "workflow_id": workflow_id,
                    "consecutive_failures": circuit_breaker.failures,
                },
            )
            adapter.update_progress_sync(
                UUID(batch_job_id),
                completed_tasks=completed_count,
                failed_tasks=failed_count,
            )
            raise

        except Exception as e:
            failed_count += 1
            errors.append({"item_id": item_id, "error": str(e)})
            circuit_breaker.record_failure()

        if (i + 1) % batch_size == 0 or (i + 1) == total_items:
            adapter.update_progress_sync(
                UUID(batch_job_id),
                completed_tasks=completed_count,
                failed_tasks=failed_count,
            )

    success = failed_count == 0
    error_summary = {"errors": errors} if errors else None
    adapter.finalize_job(
        UUID(batch_job_id),
        success=success,
        completed_tasks=completed_count,
        failed_tasks=failed_count,
        error_summary=error_summary,
    )

    logger.info(
        "Rechunk workflow completed",
        extra={
            "workflow_id": workflow_id,
            "completed": completed_count,
            "failed": failed_count,
        },
    )

    return {
        "completed_count": completed_count,
        "failed_count": failed_count,
        "errors": errors,
    }


@DBOS.workflow()
def rechunk_fact_check_workflow(
    batch_job_id: str,
    community_server_id: str | None,
    item_ids: list[str],
    batch_size: int = 100,
) -> dict[str, Any]:
    """DBOS workflow for rechunking fact-check items.

    Args:
        batch_job_id: UUID of the BatchJob record (as string)
        community_server_id: Optional community server for LLM credentials
        item_ids: List of FactCheckItem UUIDs to process
        batch_size: Items per batch (for progress reporting)

    Returns:
        dict with completed_count, failed_count, and any errors
    """
    return _rechunk_workflow_impl(
        batch_job_id=batch_job_id,
        community_server_id=community_server_id,
        item_ids=item_ids,
        batch_size=batch_size,
        workflow_id=DBOS.workflow_id,
        process_item_func=process_fact_check_item,
    )
