from datetime import UTC, datetime
from uuid import uuid4

import pytest

from src.batch_jobs.models import BatchJob
from src.batch_jobs.schemas import BatchJobCreate, BatchJobResponse, BatchJobStatus, BatchJobUpdate


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


@pytest.mark.unit
def test_batch_job_create_json_round_trip_preserves_metadata_alias() -> None:
    create = BatchJobCreate(
        job_type="url_scan",
        total_tasks=3,
        metadata={"source": "url_scan", "attempt": 2},
    )

    round_tripped = BatchJobCreate.model_validate_json(create.model_dump_json(by_alias=True))

    assert round_tripped.job_type == "url_scan"
    assert round_tripped.total_tasks == 3
    assert round_tripped.metadata_ == {"source": "url_scan", "attempt": 2}


@pytest.mark.unit
def test_batch_job_response_json_round_trip_preserves_metadata() -> None:
    response = BatchJobResponse.model_validate(
        {
            "id": uuid4(),
            "job_type": "url_scan",
            "status": "partial",
            "total_tasks": 10,
            "completed_tasks": 6,
            "failed_tasks": 1,
            "metadata_": {"source": "url_scan", "attempt": 2},
            "created_at": datetime.now(UTC),
            "updated_at": None,
            "started_at": datetime.now(UTC),
            "completed_at": datetime.now(UTC),
            "error_summary": {"reason": "some_items_failed"},
            "workflow_id": "wf-url-scan-123",
        }
    )

    round_tripped = BatchJobResponse.model_validate_json(response.model_dump_json())

    assert round_tripped.status == BatchJobStatus.PARTIAL.value
    assert round_tripped.metadata_ == {"source": "url_scan", "attempt": 2}
    assert round_tripped.error_summary == {"reason": "some_items_failed"}
    assert round_tripped.workflow_id == "wf-url-scan-123"
    assert response.model_dump(mode="json", by_alias=True)["metadata"] == {
        "source": "url_scan",
        "attempt": 2,
    }
