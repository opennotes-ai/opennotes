"""DBOS workflow infrastructure for durable background tasks.

Architecture:
    Server mode (opennotes-server):
        Uses DBOSClient for lightweight enqueue-only operations.
        Does not poll queues or execute workflows.
        Use get_dbos_client() in this mode.

    Worker mode (opennotes-dbos-worker):
        Uses DBOS with launch() for queue polling and execution.
        Processes workflows dispatched by servers.
        Use get_dbos() in this mode.

Configuration:
    get_dbos_client(): Get DBOSClient instance (server mode, enqueue only)
    get_dbos(): Get DBOS instance (worker mode, full execution)
    destroy_dbos(): Gracefully destroy DBOS singleton during shutdown
    destroy_dbos_client(): Gracefully destroy DBOSClient singleton during shutdown
    reset_dbos(): Reset DBOS singleton for testing
    reset_dbos_client(): Reset DBOSClient singleton for testing

Adapters:
    BatchJobDBOSAdapter: Sync DBOS workflow state to BatchJob records.
        All methods use fire-and-forget semantics (errors logged, not raised).

Resilience:
    CircuitBreaker: Protect against cascading failures during workflow execution
    CircuitOpenError: Raised when circuit breaker is open
    CircuitState: Enum with CLOSED, OPEN, HALF_OPEN states

Workflows:
    rechunk_fact_check_workflow: Batch rechunking of fact-check items
    dispatch_dbos_rechunk_workflow: Create BatchJob and enqueue workflow
    enqueue_single_fact_check_chunk: Enqueue single item for chunking
    content_scan_orchestration_workflow: Orchestrate content scan pipeline
    dispatch_content_scan_workflow: Start orchestration workflow
    enqueue_content_scan_batch: Enqueue batch for processing
    send_all_transmitted_signal: Signal orchestrator that all batches transmitted
    ai_note_generation_workflow: Generate AI note for fact-check match or moderation flag
    vision_description_workflow: Generate image description via LLM vision API
    call_persist_audit_log: Persist audit log entry to database
    start_ai_note_workflow: Enqueue AI note generation workflow
    start_vision_description_workflow: Enqueue vision description workflow
"""

from src.dbos_workflows.batch_job_adapter import BatchJobDBOSAdapter
from src.dbos_workflows.circuit_breaker import (
    CircuitBreaker,
    CircuitOpenError,
    CircuitState,
)
from src.dbos_workflows.config import (
    destroy_dbos,
    destroy_dbos_client,
    get_dbos,
    get_dbos_client,
    reset_dbos,
    reset_dbos_client,
)
from src.dbos_workflows.content_monitoring_workflows import (
    AI_NOTE_GENERATION_WORKFLOW_NAME,
    AUDIT_LOG_WORKFLOW_NAME,
    VISION_DESCRIPTION_WORKFLOW_NAME,
    ai_note_generation_workflow,
    call_persist_audit_log,
    start_ai_note_workflow,
    start_vision_description_workflow,
    vision_description_workflow,
)
from src.dbos_workflows.content_scan_workflow import (
    CONTENT_SCAN_ORCHESTRATION_WORKFLOW_NAME,
    PROCESS_CONTENT_SCAN_BATCH_WORKFLOW_NAME,
    content_scan_orchestration_workflow,
    dispatch_content_scan_workflow,
    enqueue_content_scan_batch,
    flashpoint_scan_step,
    load_messages_from_redis,
    preprocess_batch_step,
    process_content_scan_batch,
    relevance_filter_step,
    send_all_transmitted_signal,
    similarity_scan_step,
    store_messages_in_redis,
)
from src.dbos_workflows.rechunk_workflow import (
    CHUNK_SINGLE_FACT_CHECK_WORKFLOW_NAME,
    RECHUNK_FACT_CHECK_WORKFLOW_NAME,
    dispatch_dbos_rechunk_workflow,
    enqueue_single_fact_check_chunk,
    rechunk_fact_check_workflow,
)

__all__ = [
    "AI_NOTE_GENERATION_WORKFLOW_NAME",
    "AUDIT_LOG_WORKFLOW_NAME",
    "CHUNK_SINGLE_FACT_CHECK_WORKFLOW_NAME",
    "CONTENT_SCAN_ORCHESTRATION_WORKFLOW_NAME",
    "PROCESS_CONTENT_SCAN_BATCH_WORKFLOW_NAME",
    "RECHUNK_FACT_CHECK_WORKFLOW_NAME",
    "VISION_DESCRIPTION_WORKFLOW_NAME",
    "BatchJobDBOSAdapter",
    "CircuitBreaker",
    "CircuitOpenError",
    "CircuitState",
    "ai_note_generation_workflow",
    "call_persist_audit_log",
    "content_scan_orchestration_workflow",
    "destroy_dbos",
    "destroy_dbos_client",
    "dispatch_content_scan_workflow",
    "dispatch_dbos_rechunk_workflow",
    "enqueue_content_scan_batch",
    "enqueue_single_fact_check_chunk",
    "flashpoint_scan_step",
    "get_dbos",
    "get_dbos_client",
    "load_messages_from_redis",
    "preprocess_batch_step",
    "process_content_scan_batch",
    "rechunk_fact_check_workflow",
    "relevance_filter_step",
    "reset_dbos",
    "reset_dbos_client",
    "send_all_transmitted_signal",
    "similarity_scan_step",
    "start_ai_note_workflow",
    "start_vision_description_workflow",
    "store_messages_in_redis",
    "vision_description_workflow",
]
