"""
TaskIQ tasks for chunk re-embedding operations.

DEPRECATION NOTICE:
    All rechunk tasks (fact_check, previously_seen, chunk:fact_check_item) have been
    migrated to DBOS workflows for improved reliability. The TaskIQ task functions
    are retained as deprecated no-op stubs to drain legacy JetStream messages.
    See src/dbos_workflows/rechunk_workflow.py for the DBOS implementations.

    Remove all deprecated stubs after 2026-04-01.

These tasks handle background processing of:
- FactCheckItem operations are handled by DBOS workflows (TASK-1056)
- PreviouslySeenMessage operations are handled by DBOS workflows (TASK-1095)

Service singletons (get_chunk_embedding_service, etc.) are still used by
DBOS workflow steps and must remain in this module.
"""

import threading

from src.config import get_settings
from src.fact_checking.chunk_embedding_service import ChunkEmbeddingService
from src.fact_checking.chunking_service import (
    reset_chunking_service,
    use_chunking_service_sync,
)
from src.llm_config.encryption import EncryptionService
from src.llm_config.manager import LLMClientManager
from src.llm_config.service import LLMService
from src.monitoring import get_logger
from src.tasks.broker import register_task

logger = get_logger(__name__)

_encryption_service: EncryptionService | None = None
_llm_client_manager: LLMClientManager | None = None
_llm_service: LLMService | None = None
_chunk_embedding_service: ChunkEmbeddingService | None = None
_service_lock = threading.RLock()


def _get_encryption_service() -> EncryptionService:
    """Get or create singleton EncryptionService with double-checked locking."""
    global _encryption_service  # noqa: PLW0603
    if _encryption_service is None:
        with _service_lock:
            if _encryption_service is None:
                settings = get_settings()
                _encryption_service = EncryptionService(settings.ENCRYPTION_MASTER_KEY)
    return _encryption_service


def _get_llm_client_manager() -> LLMClientManager:
    """Get or create singleton LLMClientManager with double-checked locking."""
    global _llm_client_manager  # noqa: PLW0603
    if _llm_client_manager is None:
        with _service_lock:
            if _llm_client_manager is None:
                _llm_client_manager = LLMClientManager(encryption_service=_get_encryption_service())
    return _llm_client_manager


def _get_llm_service() -> LLMService:
    """Get or create singleton LLMService with double-checked locking."""
    global _llm_service  # noqa: PLW0603
    if _llm_service is None:
        with _service_lock:
            if _llm_service is None:
                _llm_service = LLMService(client_manager=_get_llm_client_manager())
    return _llm_service


def get_chunk_embedding_service() -> ChunkEmbeddingService:
    """Get or create singleton ChunkEmbeddingService with double-checked locking.

    All service dependencies are also singletons, ensuring consistent caching
    behavior for LLM clients and avoiding repeated model loading.

    Lock ordering: acquires _service_lock and _access_lock (via
    use_chunking_service_sync) independently to avoid ABBA deadlock with
    callers that acquire _access_lock without _service_lock (TASK-1061.06).
    """
    global _chunk_embedding_service  # noqa: PLW0603
    if _chunk_embedding_service is None:
        with _service_lock:
            if _chunk_embedding_service is not None:
                return _chunk_embedding_service
            llm_service = _get_llm_service()

        with use_chunking_service_sync() as chunking_service:
            service = ChunkEmbeddingService(
                chunking_service=chunking_service,
                llm_service=llm_service,
            )

        with _service_lock:
            if _chunk_embedding_service is None:
                _chunk_embedding_service = service
    return _chunk_embedding_service


def reset_task_services() -> None:
    """Reset all service singletons. For testing only."""
    global _encryption_service, _llm_client_manager  # noqa: PLW0603
    global _llm_service, _chunk_embedding_service  # noqa: PLW0603
    with _service_lock:
        _encryption_service = None
        _llm_client_manager = None
        _llm_service = None
        _chunk_embedding_service = None
    reset_chunking_service()


@register_task(
    task_name="rechunk:previously_seen",
    component="rechunk",
    task_type="deprecated",
)
async def process_previously_seen_rechunk_task(*args, **kwargs) -> None:
    """Deprecated no-op handler to drain legacy messages from pre-DBOS migration.

    This task was migrated to DBOS in TASK-1095. This handler exists only to
    acknowledge and discard stale messages in the JetStream queue.

    The task will automatically ACK the message after this function returns,
    preventing infinite redelivery of legacy messages.

    Remove after 2026-04-01 when all legacy messages have been drained.
    """
    logger.info(
        "Received deprecated rechunk:previously_seen message - discarding",
        extra={
            "task_name": "rechunk:previously_seen",
            "args_count": len(args),
            "kwargs_keys": list(kwargs.keys()) if kwargs else [],
            "migration_note": "Task migrated to DBOS in TASK-1095",
        },
    )


@register_task(
    task_name="rechunk:fact_check",
    component="rechunk",
    task_type="deprecated",
)
async def deprecated_fact_check_rechunk_task(*args, **kwargs) -> None:
    """Deprecated no-op handler to drain legacy messages from pre-DBOS migration.

    This task was migrated to DBOS in TASK-1056. This handler exists only to
    acknowledge and discard stale messages in the JetStream queue.

    The task will automatically ACK the message after this function returns,
    preventing infinite redelivery of legacy messages.

    Remove after 2026-04-01 when all legacy messages have been drained.
    """
    logger.info(
        "Received deprecated rechunk:fact_check message - discarding",
        extra={
            "task_name": "rechunk:fact_check",
            "args_count": len(args),
            "kwargs_keys": list(kwargs.keys()) if kwargs else [],
            "migration_note": "Task migrated to DBOS in TASK-1056",
        },
    )


@register_task(
    task_name="chunk:fact_check_item",
    component="rechunk",
    task_type="deprecated",
)
async def deprecated_chunk_fact_check_item_task(*args, **kwargs) -> None:
    """Deprecated no-op handler to drain legacy messages from pre-DBOS migration.

    This task was migrated to DBOS in TASK-1056. This handler exists only to
    acknowledge and discard stale messages in the JetStream queue.

    The task will automatically ACK the message after this function returns,
    preventing infinite redelivery of legacy messages.

    Remove after 2026-04-01 when all legacy messages have been drained.
    """
    logger.info(
        "Received deprecated chunk:fact_check_item message - discarding",
        extra={
            "task_name": "chunk:fact_check_item",
            "args_count": len(args),
            "kwargs_keys": list(kwargs.keys()) if kwargs else [],
            "migration_note": "Task migrated to DBOS in TASK-1056",
        },
    )
