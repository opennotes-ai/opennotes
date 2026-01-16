"""
Fixtures for fact-checking integration tests.

Provides shared fixtures for testing import router endpoints including
mock batch jobs and API key authentication.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from src.auth.models import APIKeyCreate
from src.batch_jobs import PROMOTION_JOB_TYPE, SCRAPE_JOB_TYPE
from src.batch_jobs.models import BatchJob, BatchJobStatus
from src.users.crud import create_api_key


@pytest.fixture
def mock_scrape_job():
    """Create a mock BatchJob for scrape operations."""
    now = datetime.now(UTC)
    return BatchJob(
        id=uuid4(),
        job_type=SCRAPE_JOB_TYPE,
        status=BatchJobStatus.PENDING,
        total_tasks=0,
        completed_tasks=0,
        failed_tasks=0,
        metadata_={"batch_size": 100, "dry_run": False},
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def mock_promotion_job():
    """Create a mock BatchJob for promotion operations."""
    now = datetime.now(UTC)
    return BatchJob(
        id=uuid4(),
        job_type=PROMOTION_JOB_TYPE,
        status=BatchJobStatus.PENDING,
        total_tasks=0,
        completed_tasks=0,
        failed_tasks=0,
        metadata_={"batch_size": 100, "dry_run": False},
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
async def api_key_headers(registered_user, db):
    """Create API key headers for authenticated requests.

    Uses the registered_user fixture from tests/conftest.py to ensure
    the user exists in the database before creating the API key.
    """
    _, raw_key = await create_api_key(
        db=db,
        user_id=registered_user["id"],
        api_key_create=APIKeyCreate(name="Test Import API Key", expires_in_days=30),
    )
    await db.commit()
    return {"X-API-Key": raw_key}
