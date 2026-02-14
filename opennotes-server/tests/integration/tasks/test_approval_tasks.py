"""
Integration tests for the deprecated process_bulk_approval TaskIQ stub.

The bulk approval logic has been migrated to DBOS durable workflows
(see src/dbos_workflows/approval_workflow.py). The TaskIQ stub in
src/tasks/approval_tasks.py exists solely to drain legacy JetStream
messages and returns {"status": "deprecated"} immediately.

The actual approval workflow is tested via the DBOS workflow tests
and the endpoint integration tests in test_candidates_jsonapi.py.
"""

import pytest

from src.tasks.approval_tasks import process_bulk_approval


@pytest.mark.integration
class TestDeprecatedApprovalTaskStub:
    """Verify the deprecated TaskIQ stub behaves as expected."""

    @pytest.mark.asyncio
    async def test_stub_returns_deprecated_status(self):
        """The deprecated stub returns status=deprecated without processing."""
        result = await process_bulk_approval()
        assert result["status"] == "deprecated"
        assert result["migrated_to"] == "dbos"

    @pytest.mark.asyncio
    async def test_stub_accepts_arbitrary_args(self):
        """The deprecated stub accepts any args/kwargs without error."""
        result = await process_bulk_approval(
            "arg1",
            "arg2",
            job_id="fake-id",
            threshold=0.9,
            auto_promote=True,
        )
        assert result["status"] == "deprecated"
        assert result["migrated_to"] == "dbos"
