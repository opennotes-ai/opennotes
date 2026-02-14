"""
Unit tests for scrape batch job TaskIQ task labels.

Task: task-1093 - Migrate import pipeline tasks to DBOS durable workflows

NOTE: End-to-end tests for the scrape batch pipeline have been moved to
tests/unit/dbos_workflows/test_import_workflow.py. The TaskIQ task stubs
in import_tasks.py are deprecated no-ops (TASK-1093).

Remaining tests verify:
- TaskIQ task label configuration for deprecated stubs
"""

import pytest

from src.batch_jobs import SCRAPE_JOB_TYPE

pytestmark = pytest.mark.unit


class TestScrapeBatchTaskLabels:
    """Test TaskIQ task labels are properly configured for deprecated stub."""

    def test_scrape_batch_task_has_deprecated_labels(self):
        """Verify scrape batch task has component and deprecated task_type labels."""
        import src.tasks.import_tasks  # noqa: F401
        from src.tasks.broker import get_registered_tasks

        registered_tasks = get_registered_tasks()
        assert SCRAPE_JOB_TYPE in registered_tasks

        _, labels = registered_tasks[SCRAPE_JOB_TYPE]
        assert labels.get("component") == "import_pipeline"
        assert labels.get("task_type") == "deprecated"
