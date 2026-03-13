"""DBOS workflow infrastructure for durable background tasks.

Architecture:
    Worker mode (opennotes-dbos-worker):
        Uses DBOS with launch() for queue polling and execution.
        Processes workflows dispatched by servers.
        Use get_dbos() in this mode.

Configuration:
    get_dbos(): Get DBOS instance (worker mode, full execution)
    destroy_dbos(): Gracefully destroy DBOS singleton during shutdown
    reset_dbos(): Reset DBOS singleton for testing

Adapters:
    BatchJobDBOSAdapter: Sync DBOS workflow state to BatchJob records.
        All methods use fire-and-forget semantics (errors logged, not raised).

Resilience:
    CircuitBreaker: Protect against cascading failures during workflow execution
    CircuitOpenError: Raised when circuit breaker is open
    CircuitState: Enum with CLOSED, OPEN, HALF_OPEN states

Scheduled Workflows:
    cleanup_stale_batch_jobs_workflow: Weekly cleanup of stale batch jobs (Sunday midnight UTC)
    monitor_stuck_batch_jobs_workflow: Monitor for stuck batch jobs (every 15 minutes)

Workflows:
    rechunk_fact_check_workflow: Batch rechunking of fact-check items
    rechunk_previously_seen_workflow: Batch rechunking of previously-seen messages
    dispatch_dbos_rechunk_workflow: Create BatchJob and enqueue fact-check workflow
    dispatch_dbos_previously_seen_rechunk_workflow: Create BatchJob and enqueue previously-seen workflow
    enqueue_single_fact_check_chunk: Enqueue single item for chunking
    content_scan_orchestration_workflow: Orchestrate content scan pipeline
    dispatch_content_scan_workflow: Start orchestration workflow
    enqueue_content_scan_batch: Enqueue batch for processing
    send_all_transmitted_signal: Signal orchestrator that all batches transmitted
    bulk_approval_workflow: Bulk approve fact-check candidates from predictions
    fact_check_import_workflow: CSV streaming, validation, and upsert from HuggingFace
    scrape_candidates_workflow: Batch URL scraping with concurrency control
    promote_candidates_workflow: Batch candidate promotion to fact-check items
    dispatch_import_workflow: Enqueue fact-check import workflow
    dispatch_scrape_workflow: Enqueue scrape candidates workflow
    dispatch_promote_workflow: Enqueue promote candidates workflow
    ai_note_generation_workflow: Generate AI note for fact-check match or moderation flag
    vision_description_workflow: Generate image description via LLM vision API
    call_persist_audit_log: Persist audit log entry to database
    start_ai_note_workflow: Enqueue AI note generation workflow
"""

from __future__ import annotations

import importlib

_LAZY_IMPORTS: dict[str, tuple[str, str]] = {
    "AI_NOTE_GENERATION_WORKFLOW_NAME": (
        "src.dbos_workflows.content_monitoring_workflows",
        "AI_NOTE_GENERATION_WORKFLOW_NAME",
    ),
    "AUDIT_LOG_WORKFLOW_NAME": (
        "src.dbos_workflows.content_monitoring_workflows",
        "AUDIT_LOG_WORKFLOW_NAME",
    ),
    "BULK_APPROVAL_WORKFLOW_NAME": (
        "src.dbos_workflows.approval_workflow",
        "BULK_APPROVAL_WORKFLOW_NAME",
    ),
    "CHUNK_SINGLE_FACT_CHECK_WORKFLOW_NAME": (
        "src.dbos_workflows.rechunk_workflow",
        "CHUNK_SINGLE_FACT_CHECK_WORKFLOW_NAME",
    ),
    "CLEANUP_STALE_BATCH_JOBS_WORKFLOW_NAME": (
        "src.dbos_workflows.scheduler_workflows",
        "CLEANUP_STALE_BATCH_JOBS_WORKFLOW_NAME",
    ),
    "CLEANUP_STALE_TOKEN_HOLDS_WORKFLOW_NAME": (
        "src.dbos_workflows.token_bucket.cleanup",
        "CLEANUP_STALE_TOKEN_HOLDS_WORKFLOW_NAME",
    ),
    "CONTENT_SCAN_ORCHESTRATION_WORKFLOW_NAME": (
        "src.dbos_workflows.content_scan_workflow",
        "CONTENT_SCAN_ORCHESTRATION_WORKFLOW_NAME",
    ),
    "FACT_CHECK_IMPORT_WORKFLOW_NAME": (
        "src.dbos_workflows.import_workflow",
        "FACT_CHECK_IMPORT_WORKFLOW_NAME",
    ),
    "MONITOR_STUCK_BATCH_JOBS_WORKFLOW_NAME": (
        "src.dbos_workflows.scheduler_workflows",
        "MONITOR_STUCK_BATCH_JOBS_WORKFLOW_NAME",
    ),
    "PROCESS_CONTENT_SCAN_BATCH_WORKFLOW_NAME": (
        "src.dbos_workflows.content_scan_workflow",
        "PROCESS_CONTENT_SCAN_BATCH_WORKFLOW_NAME",
    ),
    "PROMOTE_CANDIDATES_WORKFLOW_NAME": (
        "src.dbos_workflows.import_workflow",
        "PROMOTE_CANDIDATES_WORKFLOW_NAME",
    ),
    "RECHUNK_FACT_CHECK_WORKFLOW_NAME": (
        "src.dbos_workflows.rechunk_workflow",
        "RECHUNK_FACT_CHECK_WORKFLOW_NAME",
    ),
    "RECHUNK_PREVIOUSLY_SEEN_WORKFLOW_NAME": (
        "src.dbos_workflows.rechunk_workflow",
        "RECHUNK_PREVIOUSLY_SEEN_WORKFLOW_NAME",
    ),
    "SCRAPE_CANDIDATES_WORKFLOW_NAME": (
        "src.dbos_workflows.import_workflow",
        "SCRAPE_CANDIDATES_WORKFLOW_NAME",
    ),
    "VISION_DESCRIPTION_WORKFLOW_NAME": (
        "src.dbos_workflows.content_monitoring_workflows",
        "VISION_DESCRIPTION_WORKFLOW_NAME",
    ),
    "BatchJobDBOSAdapter": ("src.dbos_workflows.batch_job_adapter", "BatchJobDBOSAdapter"),
    "CircuitBreaker": ("src.dbos_workflows.circuit_breaker", "CircuitBreaker"),
    "CircuitOpenError": ("src.dbos_workflows.circuit_breaker", "CircuitOpenError"),
    "CircuitState": ("src.dbos_workflows.circuit_breaker", "CircuitState"),
    "ai_note_generation_workflow": (
        "src.dbos_workflows.content_monitoring_workflows",
        "ai_note_generation_workflow",
    ),
    "bulk_approval_workflow": (
        "src.dbos_workflows.approval_workflow",
        "bulk_approval_workflow",
    ),
    "call_persist_audit_log": (
        "src.dbos_workflows.content_monitoring_workflows",
        "call_persist_audit_log",
    ),
    "cleanup_stale_batch_jobs_workflow": (
        "src.dbos_workflows.scheduler_workflows",
        "cleanup_stale_batch_jobs_workflow",
    ),
    "cleanup_stale_token_holds": (
        "src.dbos_workflows.token_bucket.cleanup",
        "cleanup_stale_token_holds",
    ),
    "content_scan_orchestration_workflow": (
        "src.dbos_workflows.content_scan_workflow",
        "content_scan_orchestration_workflow",
    ),
    "destroy_dbos": ("src.dbos_workflows.config", "destroy_dbos"),
    "dispatch_bulk_approval_workflow": (
        "src.dbos_workflows.approval_workflow",
        "dispatch_bulk_approval_workflow",
    ),
    "dispatch_content_scan_workflow": (
        "src.dbos_workflows.content_scan_workflow",
        "dispatch_content_scan_workflow",
    ),
    "dispatch_dbos_previously_seen_rechunk_workflow": (
        "src.dbos_workflows.rechunk_workflow",
        "dispatch_dbos_previously_seen_rechunk_workflow",
    ),
    "dispatch_dbos_rechunk_workflow": (
        "src.dbos_workflows.rechunk_workflow",
        "dispatch_dbos_rechunk_workflow",
    ),
    "dispatch_import_workflow": (
        "src.dbos_workflows.import_workflow",
        "dispatch_import_workflow",
    ),
    "dispatch_promote_workflow": (
        "src.dbos_workflows.import_workflow",
        "dispatch_promote_workflow",
    ),
    "dispatch_scrape_workflow": (
        "src.dbos_workflows.import_workflow",
        "dispatch_scrape_workflow",
    ),
    "enqueue_content_scan_batch": (
        "src.dbos_workflows.content_scan_workflow",
        "enqueue_content_scan_batch",
    ),
    "enqueue_single_fact_check_chunk": (
        "src.dbos_workflows.rechunk_workflow",
        "enqueue_single_fact_check_chunk",
    ),
    "fact_check_import_workflow": (
        "src.dbos_workflows.import_workflow",
        "fact_check_import_workflow",
    ),
    "flashpoint_scan_step": (
        "src.dbos_workflows.content_scan_workflow",
        "flashpoint_scan_step",
    ),
    "get_dbos": ("src.dbos_workflows.config", "get_dbos"),
    "load_messages_from_redis": (
        "src.dbos_workflows.content_scan_workflow",
        "load_messages_from_redis",
    ),
    "monitor_stuck_batch_jobs_workflow": (
        "src.dbos_workflows.scheduler_workflows",
        "monitor_stuck_batch_jobs_workflow",
    ),
    "preprocess_batch_step": (
        "src.dbos_workflows.content_scan_workflow",
        "preprocess_batch_step",
    ),
    "process_content_scan_batch": (
        "src.dbos_workflows.content_scan_workflow",
        "process_content_scan_batch",
    ),
    "promote_candidates_workflow": (
        "src.dbos_workflows.import_workflow",
        "promote_candidates_workflow",
    ),
    "rechunk_fact_check_workflow": (
        "src.dbos_workflows.rechunk_workflow",
        "rechunk_fact_check_workflow",
    ),
    "rechunk_previously_seen_workflow": (
        "src.dbos_workflows.rechunk_workflow",
        "rechunk_previously_seen_workflow",
    ),
    "relevance_filter_step": (
        "src.dbos_workflows.content_scan_workflow",
        "relevance_filter_step",
    ),
    "reset_dbos": ("src.dbos_workflows.config", "reset_dbos"),
    "scrape_candidates_workflow": (
        "src.dbos_workflows.import_workflow",
        "scrape_candidates_workflow",
    ),
    "send_all_transmitted_signal": (
        "src.dbos_workflows.content_scan_workflow",
        "send_all_transmitted_signal",
    ),
    "similarity_scan_step": (
        "src.dbos_workflows.content_scan_workflow",
        "similarity_scan_step",
    ),
    "start_ai_note_workflow": (
        "src.dbos_workflows.content_monitoring_workflows",
        "start_ai_note_workflow",
    ),
    "store_messages_in_redis": (
        "src.dbos_workflows.content_scan_workflow",
        "store_messages_in_redis",
    ),
    "vision_description_workflow": (
        "src.dbos_workflows.content_monitoring_workflows",
        "vision_description_workflow",
    ),
}


def __getattr__(name: str) -> object:
    if name in _LAZY_IMPORTS:
        module_path, attr = _LAZY_IMPORTS[name]
        mod = importlib.import_module(module_path)
        val = getattr(mod, attr)
        globals()[name] = val
        return val
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = list(_LAZY_IMPORTS)
