"""DBOS workflow infrastructure for the rechunk migration.

This module provides adapters and utilities for integrating DBOS workflows
with the existing OpenNotes infrastructure during the TaskIQ → DBOS migration.
"""

from src.dbos_workflows.batch_job_adapter import BatchJobDBOSAdapter

__all__ = ["BatchJobDBOSAdapter"]
