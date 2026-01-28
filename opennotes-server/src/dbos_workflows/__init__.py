"""DBOS workflow infrastructure for durable background tasks.

This module provides:
- BatchJobDBOSAdapter: Sync DBOS workflow state to BatchJob records
- CircuitBreaker: Protect against cascading failures during workflow execution
- dispatch_dbos_rechunk_workflow: Dispatch rechunk jobs via DBOS
- rechunk_fact_check_workflow: DBOS workflow for rechunking fact-check items
"""

from src.dbos_workflows.batch_job_adapter import BatchJobDBOSAdapter
from src.dbos_workflows.circuit_breaker import (
    CircuitBreaker,
    CircuitOpenError,
    CircuitState,
)
from src.dbos_workflows.rechunk_workflow import (
    dispatch_dbos_rechunk_workflow,
    rechunk_fact_check_workflow,
)

__all__ = [
    "BatchJobDBOSAdapter",
    "CircuitBreaker",
    "CircuitOpenError",
    "CircuitState",
    "dispatch_dbos_rechunk_workflow",
    "rechunk_fact_check_workflow",
]
