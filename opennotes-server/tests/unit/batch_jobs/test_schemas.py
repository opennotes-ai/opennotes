from datetime import UTC, datetime
from uuid import uuid4

import pytest

from src.batch_jobs.models import BatchJob
from src.batch_jobs.schemas import BatchJobResponse, BatchJobStatus, BatchJobUpdate


@pytest.mark.unit
@pytest.mark.parametrize(
    ("status_value", "is_terminal"),
    [
        ("extracting", False),
        ("analyzing", False),
        ("partial", True),
    ],
)
def test_batch_job_status_supports_url_scan_lifecycle_states(
    status_value: str,
    is_terminal: bool,
):
    """Batch job schemas accept URL-scan lifecycle statuses and preserve them."""
    status = BatchJobStatus(status_value)

    update = BatchJobUpdate.model_validate({"status": status_value})
    response = BatchJobResponse.model_validate(
        {
            "id": uuid4(),
            "job_type": "url_scan",
            "status": status_value,
            "total_tasks": 10,
            "completed_tasks": 6,
            "failed_tasks": 1,
            "metadata": {"source": "url_scan"},
            "created_at": datetime.now(UTC),
            "updated_at": None,
            "started_at": None,
            "completed_at": None,
            "error_summary": None,
            "workflow_id": None,
        }
    )

    assert status == status_value
    assert update.status == status_value
    assert update.model_dump()["status"] == status_value
    assert response.status == status_value
    assert response.model_dump(mode="json")["status"] == status_value

    batch_job = BatchJob(status=status_value)
    assert batch_job.is_terminal is is_terminal
