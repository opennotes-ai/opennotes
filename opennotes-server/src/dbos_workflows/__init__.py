"""DBOS workflow infrastructure for durable background tasks.

This module provides:
- BatchJobDBOSAdapter: Sync DBOS workflow state to BatchJob records
- CircuitBreaker: Protect against cascading failures during workflow execution
- dispatch_dbos_rechunk_workflow: Dispatch rechunk jobs via DBOS
- rechunk_fact_check_workflow: DBOS workflow for rechunking fact-check items
- get_dbos_client: Get DBOSClient for enqueueing workflows (server mode)
- get_dbos: Get full DBOS instance for queue polling (worker mode)
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
