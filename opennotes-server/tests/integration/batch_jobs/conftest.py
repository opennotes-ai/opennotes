"""
Pytest fixtures for batch_jobs integration tests.

Provides autouse cleanup fixtures to ensure BatchJob records are removed after tests.
"""

import pytest
from sqlalchemy import delete

from src.batch_jobs.constants import RECHUNK_FACT_CHECK_JOB_TYPE
from src.batch_jobs.models import BatchJob
from src.database import get_session_maker


@pytest.fixture(autouse=True)
async def cleanup_batch_jobs():
    """
    Autouse fixture that cleans up BatchJob records after each test.

    Yields control to the test first, then performs cleanup in teardown.
    Provides defense-in-depth cleanup for concurrent test scenarios.
    """
    yield

    async with get_session_maker()() as session:
        await session.execute(
            delete(BatchJob).where(BatchJob.job_type == RECHUNK_FACT_CHECK_JOB_TYPE)
        )
        await session.commit()
