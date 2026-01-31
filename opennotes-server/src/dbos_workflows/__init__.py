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
"""

from src.dbos_workflows.batch_job_adapter import BatchJobDBOSAdapter
from src.dbos_workflows.circuit_breaker import (
    CircuitBreaker,
    CircuitOpenError,
    CircuitState,
)
from src.dbos_workflows.config import (
    get_dbos,
    get_dbos_client,
    reset_dbos,
    reset_dbos_client,
)
from src.dbos_workflows.rechunk_workflow import (
    dispatch_dbos_rechunk_workflow,
    enqueue_single_fact_check_chunk,
    rechunk_fact_check_workflow,
)

__all__ = [
    "BatchJobDBOSAdapter",
    "CircuitBreaker",
    "CircuitOpenError",
    "CircuitState",
    "dispatch_dbos_rechunk_workflow",
    "enqueue_single_fact_check_chunk",
    "get_dbos",
    "get_dbos_client",
    "rechunk_fact_check_workflow",
    "reset_dbos",
    "reset_dbos_client",
]
