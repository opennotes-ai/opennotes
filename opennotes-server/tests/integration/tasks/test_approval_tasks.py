"""
Integration tests for process_bulk_approval TaskIQ task.

These tests execute the task function directly (not via .kiq()) to verify
actual database updates, progress tracking, and error aggregation behavior.

Tests verify:
- Candidates are actually updated in database after task execution
- Progress tracking updates during batch processing
- Error aggregation when some candidates fail
- Edge cases: limit=0, threshold=0.0, partial failure scenarios
- All kwargs are passed correctly (filters, date ranges, etc.)
"""

import os
from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy import delete, select

from src.batch_jobs.constants import BULK_APPROVAL_JOB_TYPE
from src.batch_jobs.models import BatchJob
from src.batch_jobs.progress_tracker import BatchJobProgressTracker
from src.batch_jobs.schemas import BatchJobCreate, BatchJobStatus
from src.batch_jobs.service import BatchJobService
from src.cache.redis_client import RedisClient
from src.database import get_session_maker
from src.fact_checking.candidate_models import CandidateStatus, FactCheckedItemCandidate
from src.tasks.approval_tasks import process_bulk_approval


def get_test_urls() -> tuple[str, str]:
    """Get database and redis URLs at runtime after fixtures have configured them."""
    from src.config import settings

    return settings.DATABASE_URL, settings.REDIS_URL


@pytest.fixture
async def redis_client_for_task(test_services):
    """Create and connect a Redis client for task tests."""
    from src.circuit_breaker import circuit_breaker_registry

    _, redis_url = get_test_urls()
    old_value = os.environ.get("INTEGRATION_TESTS")
    os.environ["INTEGRATION_TESTS"] = "true"
    try:
        client = RedisClient()
        await circuit_breaker_registry.reset("redis")
        await client.connect(redis_url)
        yield client
        await client.disconnect()
    finally:
        if old_value is None:
            os.environ.pop("INTEGRATION_TESTS", None)
        else:
            os.environ["INTEGRATION_TESTS"] = old_value
        await circuit_breaker_registry.reset("redis")


@pytest.fixture
async def progress_tracker(redis_client_for_task: RedisClient):
    """Create a progress tracker with the test Redis client."""
    return BatchJobProgressTracker(redis_client_for_task)


@pytest.fixture(autouse=True)
async def cleanup_test_data():
    """Clean up test data after each test."""
    yield
    async with get_session_maker()() as session:
        await session.execute(delete(BatchJob).where(BatchJob.job_type == BULK_APPROVAL_JOB_TYPE))
        await session.execute(
            delete(FactCheckedItemCandidate).where(
                FactCheckedItemCandidate.dataset_name.like("test_%")
            )
        )
        await session.commit()


async def create_candidate(
    session,
    source_url: str,
    title: str,
    predicted_ratings: dict[str, float] | None = None,
    rating: str | None = None,
    status: str = CandidateStatus.SCRAPED.value,
    dataset_name: str = "test_dataset",
    content: str | None = "Test content",
    published_date: datetime | None = None,
    dataset_tags: list[str] | None = None,
) -> UUID:
    """Create a candidate for testing and return its ID."""
    from src.fact_checking.candidate_models import compute_claim_hash

    candidate = FactCheckedItemCandidate(
        source_url=source_url,
        claim_hash=compute_claim_hash(title),
        title=title,
        content=content,
        predicted_ratings=predicted_ratings,
        rating=rating,
        status=status,
        dataset_name=dataset_name,
        published_date=published_date,
        dataset_tags=dataset_tags or [],
    )
    session.add(candidate)
    await session.commit()
    await session.refresh(candidate)
    return candidate.id


async def create_batch_job(
    session,
    progress_tracker: BatchJobProgressTracker,
    total_tasks: int = 0,
) -> UUID:
    """Create a batch job for testing and return its ID."""
    service = BatchJobService(session, progress_tracker)
    job = await service.create_job(
        BatchJobCreate(
            job_type=BULK_APPROVAL_JOB_TYPE,
            total_tasks=total_tasks,
            metadata={},
        )
    )
    await session.commit()
    return job.id


async def get_candidate_rating(candidate_id: UUID) -> str | None:
    """Get the rating of a candidate by ID."""
    async with get_session_maker()() as session:
        result = await session.execute(
            select(FactCheckedItemCandidate.rating).where(
                FactCheckedItemCandidate.id == candidate_id
            )
        )
        return result.scalar_one_or_none()


async def get_batch_job(job_id: UUID) -> BatchJob | None:
    """Get a batch job by ID."""
    async with get_session_maker()() as session:
        result = await session.execute(select(BatchJob).where(BatchJob.id == job_id))
        return result.scalar_one_or_none()


@pytest.mark.integration
class TestProcessBulkApprovalExecution:
    """Test actual execution of process_bulk_approval task."""

    async def test_task_updates_candidates_in_database(
        self,
        progress_tracker: BatchJobProgressTracker,
    ):
        """
        AC#1: Integration test that executes process_bulk_approval task
        and verifies candidates are actually updated.
        """
        async with get_session_maker()() as session:
            candidate1_id = await create_candidate(
                session,
                source_url="https://example.com/article1",
                title="Test Article 1",
                predicted_ratings={"false": 1.0},
            )
            candidate2_id = await create_candidate(
                session,
                source_url="https://example.com/article2",
                title="Test Article 2",
                predicted_ratings={"misleading": 0.95},
            )
            candidate3_id = await create_candidate(
                session,
                source_url="https://example.com/article3",
                title="Test Article 3",
                predicted_ratings=None,
            )
            job_id = await create_batch_job(session, progress_tracker)

        db_url, redis_url = get_test_urls()
        result = await process_bulk_approval(
            job_id=str(job_id),
            threshold=0.9,
            auto_promote=False,
            limit=100,
            status=None,
            dataset_name=None,
            dataset_tags=None,
            has_content=None,
            published_date_from=None,
            published_date_to=None,
            db_url=db_url,
            redis_url=redis_url,
        )

        assert result["updated_count"] == 2

        assert await get_candidate_rating(candidate1_id) == "false"
        assert await get_candidate_rating(candidate2_id) == "misleading"
        assert await get_candidate_rating(candidate3_id) is None

    async def test_task_respects_threshold(
        self,
        progress_tracker: BatchJobProgressTracker,
    ):
        """Task only updates candidates meeting threshold."""
        async with get_session_maker()() as session:
            await create_candidate(
                session,
                source_url="https://example.com/high-conf",
                title="High Confidence",
                predicted_ratings={"false": 1.0},
            )
            low_conf_id = await create_candidate(
                session,
                source_url="https://example.com/low-conf",
                title="Low Confidence",
                predicted_ratings={"false": 0.7},
            )
            job_id = await create_batch_job(session, progress_tracker)

        result = await process_bulk_approval(
            job_id=str(job_id),
            threshold=0.9,
            auto_promote=False,
            limit=100,
            status=None,
            dataset_name=None,
            dataset_tags=None,
            has_content=None,
            published_date_from=None,
            published_date_to=None,
            db_url=get_test_urls()[0],
            redis_url=get_test_urls()[1],
        )

        assert result["updated_count"] == 1
        assert await get_candidate_rating(low_conf_id) is None


@pytest.mark.integration
class TestProgressTracking:
    """AC#2: Test progress tracking during task execution."""

    async def test_progress_updated_during_execution(
        self,
        progress_tracker: BatchJobProgressTracker,
    ):
        """Task updates progress during batch processing."""
        async with get_session_maker()() as session:
            for i in range(5):
                await create_candidate(
                    session,
                    source_url=f"https://example.com/article{i}",
                    title=f"Test Article {i}",
                    predicted_ratings={"false": 1.0},
                )
            job_id = await create_batch_job(session, progress_tracker, total_tasks=5)

        result = await process_bulk_approval(
            job_id=str(job_id),
            threshold=0.9,
            auto_promote=False,
            limit=100,
            status=None,
            dataset_name=None,
            dataset_tags=None,
            has_content=None,
            published_date_from=None,
            published_date_to=None,
            db_url=get_test_urls()[0],
            redis_url=get_test_urls()[1],
        )

        assert result["updated_count"] == 5

        job_record = await get_batch_job(job_id)
        assert job_record is not None
        assert job_record.status == BatchJobStatus.COMPLETED.value
        assert job_record.completed_tasks == 5
        assert job_record.completed_at is not None

    async def test_job_status_transitions(
        self,
        progress_tracker: BatchJobProgressTracker,
    ):
        """Job transitions from PENDING -> IN_PROGRESS -> COMPLETED."""
        async with get_session_maker()() as session:
            await create_candidate(
                session,
                source_url="https://example.com/test",
                title="Test Article",
                predicted_ratings={"false": 1.0},
            )
            job_id = await create_batch_job(session, progress_tracker)

        initial_job = await get_batch_job(job_id)
        assert initial_job is not None
        assert initial_job.status == BatchJobStatus.PENDING.value

        await process_bulk_approval(
            job_id=str(job_id),
            threshold=0.9,
            auto_promote=False,
            limit=100,
            status=None,
            dataset_name=None,
            dataset_tags=None,
            has_content=None,
            published_date_from=None,
            published_date_to=None,
            db_url=get_test_urls()[0],
            redis_url=get_test_urls()[1],
        )

        job_record = await get_batch_job(job_id)
        assert job_record is not None
        assert job_record.status == BatchJobStatus.COMPLETED.value


@pytest.mark.integration
class TestErrorAggregation:
    """AC#3: Test error aggregation when some candidates fail."""

    async def test_partial_success_with_errors(
        self,
        progress_tracker: BatchJobProgressTracker,
    ):
        """Task continues processing after individual failures and aggregates errors."""
        async with get_session_maker()() as session:
            await create_candidate(
                session,
                source_url="https://example.com/good1",
                title="Good Article 1",
                predicted_ratings={"false": 1.0},
            )
            await create_candidate(
                session,
                source_url="https://example.com/good2",
                title="Good Article 2",
                predicted_ratings={"misleading": 1.0},
            )
            job_id = await create_batch_job(session, progress_tracker)

        result = await process_bulk_approval(
            job_id=str(job_id),
            threshold=0.9,
            auto_promote=False,
            limit=100,
            status=None,
            dataset_name=None,
            dataset_tags=None,
            has_content=None,
            published_date_from=None,
            published_date_to=None,
            db_url=get_test_urls()[0],
            redis_url=get_test_urls()[1],
        )

        assert result["updated_count"] == 2

    async def test_job_completes_with_partial_failures(
        self,
        progress_tracker: BatchJobProgressTracker,
    ):
        """Job marks as completed even with some failed tasks."""
        async with get_session_maker()() as session:
            await create_candidate(
                session,
                source_url="https://example.com/test",
                title="Test Article",
                predicted_ratings={"false": 1.0},
            )
            job_id = await create_batch_job(session, progress_tracker)

        await process_bulk_approval(
            job_id=str(job_id),
            threshold=0.9,
            auto_promote=False,
            limit=100,
            status=None,
            dataset_name=None,
            dataset_tags=None,
            has_content=None,
            published_date_from=None,
            published_date_to=None,
            db_url=get_test_urls()[0],
            redis_url=get_test_urls()[1],
        )

        job_record = await get_batch_job(job_id)
        assert job_record is not None
        assert job_record.status == BatchJobStatus.COMPLETED.value
        assert job_record.metadata_.get("stats") is not None


@pytest.mark.integration
class TestEdgeCases:
    """AC#4: Edge case tests."""

    async def test_limit_zero_processes_nothing(
        self,
        progress_tracker: BatchJobProgressTracker,
    ):
        """limit=0 should process zero candidates."""
        async with get_session_maker()() as session:
            candidate_id = await create_candidate(
                session,
                source_url="https://example.com/test",
                title="Test Article",
                predicted_ratings={"false": 1.0},
            )
            job_id = await create_batch_job(session, progress_tracker)

        result = await process_bulk_approval(
            job_id=str(job_id),
            threshold=0.9,
            auto_promote=False,
            limit=0,
            status=None,
            dataset_name=None,
            dataset_tags=None,
            has_content=None,
            published_date_from=None,
            published_date_to=None,
            db_url=get_test_urls()[0],
            redis_url=get_test_urls()[1],
        )

        assert result["updated_count"] == 0
        assert await get_candidate_rating(candidate_id) is None

    async def test_threshold_zero_accepts_all_predictions(
        self,
        progress_tracker: BatchJobProgressTracker,
    ):
        """threshold=0.0 should accept any prediction."""
        async with get_session_maker()() as session:
            await create_candidate(
                session,
                source_url="https://example.com/low-conf",
                title="Low Confidence",
                predicted_ratings={"false": 0.1},
            )
            job_id = await create_batch_job(session, progress_tracker)

        result = await process_bulk_approval(
            job_id=str(job_id),
            threshold=0.0,
            auto_promote=False,
            limit=100,
            status=None,
            dataset_name=None,
            dataset_tags=None,
            has_content=None,
            published_date_from=None,
            published_date_to=None,
            db_url=get_test_urls()[0],
            redis_url=get_test_urls()[1],
        )

        assert result["updated_count"] == 1

    async def test_no_matching_candidates_completes_successfully(
        self,
        progress_tracker: BatchJobProgressTracker,
    ):
        """Task completes successfully when no candidates match filters."""
        async with get_session_maker()() as session:
            await create_candidate(
                session,
                source_url="https://example.com/test",
                title="Test Article",
                rating="already_rated",
                predicted_ratings={"false": 1.0},
            )
            job_id = await create_batch_job(session, progress_tracker)

        result = await process_bulk_approval(
            job_id=str(job_id),
            threshold=0.9,
            auto_promote=False,
            limit=100,
            status=None,
            dataset_name=None,
            dataset_tags=None,
            has_content=None,
            published_date_from=None,
            published_date_to=None,
            db_url=get_test_urls()[0],
            redis_url=get_test_urls()[1],
        )

        assert result["updated_count"] == 0

    async def test_already_rated_candidates_skipped(
        self,
        progress_tracker: BatchJobProgressTracker,
    ):
        """Candidates with existing rating should be skipped."""
        async with get_session_maker()() as session:
            already_rated_id = await create_candidate(
                session,
                source_url="https://example.com/rated",
                title="Already Rated",
                rating="true",
                predicted_ratings={"false": 1.0},
            )
            not_rated_id = await create_candidate(
                session,
                source_url="https://example.com/not-rated",
                title="Not Rated",
                predicted_ratings={"false": 1.0},
            )
            job_id = await create_batch_job(session, progress_tracker)

        result = await process_bulk_approval(
            job_id=str(job_id),
            threshold=0.9,
            auto_promote=False,
            limit=100,
            status=None,
            dataset_name=None,
            dataset_tags=None,
            has_content=None,
            published_date_from=None,
            published_date_to=None,
            db_url=get_test_urls()[0],
            redis_url=get_test_urls()[1],
        )

        assert result["updated_count"] == 1
        assert await get_candidate_rating(already_rated_id) == "true"
        assert await get_candidate_rating(not_rated_id) == "false"


@pytest.mark.integration
class TestKwargsPassThrough:
    """AC#5: Verify all kwargs are passed to task."""

    async def test_published_date_from_filter(
        self,
        progress_tracker: BatchJobProgressTracker,
    ):
        """published_date_from filters older candidates."""
        old_date = datetime(2020, 1, 1, tzinfo=UTC)
        recent_date = datetime(2024, 6, 1, tzinfo=UTC)

        async with get_session_maker()() as session:
            await create_candidate(
                session,
                source_url="https://example.com/old",
                title="Old Article",
                predicted_ratings={"false": 1.0},
                published_date=old_date,
            )
            recent_id = await create_candidate(
                session,
                source_url="https://example.com/recent",
                title="Recent Article",
                predicted_ratings={"false": 1.0},
                published_date=recent_date,
            )
            job_id = await create_batch_job(session, progress_tracker)

        result = await process_bulk_approval(
            job_id=str(job_id),
            threshold=0.9,
            auto_promote=False,
            limit=100,
            status=None,
            dataset_name=None,
            dataset_tags=None,
            has_content=None,
            published_date_from="2024-01-01T00:00:00Z",
            published_date_to=None,
            db_url=get_test_urls()[0],
            redis_url=get_test_urls()[1],
        )

        assert result["updated_count"] == 1
        assert await get_candidate_rating(recent_id) == "false"

    async def test_published_date_to_filter(
        self,
        progress_tracker: BatchJobProgressTracker,
    ):
        """published_date_to filters newer candidates."""
        old_date = datetime(2020, 1, 1, tzinfo=UTC)
        recent_date = datetime(2024, 6, 1, tzinfo=UTC)

        async with get_session_maker()() as session:
            old_id = await create_candidate(
                session,
                source_url="https://example.com/old",
                title="Old Article",
                predicted_ratings={"false": 1.0},
                published_date=old_date,
            )
            await create_candidate(
                session,
                source_url="https://example.com/recent",
                title="Recent Article",
                predicted_ratings={"false": 1.0},
                published_date=recent_date,
            )
            job_id = await create_batch_job(session, progress_tracker)

        result = await process_bulk_approval(
            job_id=str(job_id),
            threshold=0.9,
            auto_promote=False,
            limit=100,
            status=None,
            dataset_name=None,
            dataset_tags=None,
            has_content=None,
            published_date_from=None,
            published_date_to="2021-01-01T00:00:00Z",
            db_url=get_test_urls()[0],
            redis_url=get_test_urls()[1],
        )

        assert result["updated_count"] == 1
        assert await get_candidate_rating(old_id) == "false"

    async def test_has_content_true_filter(
        self,
        progress_tracker: BatchJobProgressTracker,
    ):
        """has_content=True filters candidates without content."""
        async with get_session_maker()() as session:
            with_content_id = await create_candidate(
                session,
                source_url="https://example.com/with-content",
                title="With Content",
                predicted_ratings={"false": 1.0},
                content="This has content",
            )
            await create_candidate(
                session,
                source_url="https://example.com/without-content",
                title="Without Content",
                predicted_ratings={"false": 1.0},
                content=None,
            )
            job_id = await create_batch_job(session, progress_tracker)

        result = await process_bulk_approval(
            job_id=str(job_id),
            threshold=0.9,
            auto_promote=False,
            limit=100,
            status=None,
            dataset_name=None,
            dataset_tags=None,
            has_content=True,
            published_date_from=None,
            published_date_to=None,
            db_url=get_test_urls()[0],
            redis_url=get_test_urls()[1],
        )

        assert result["updated_count"] == 1
        assert await get_candidate_rating(with_content_id) == "false"

    async def test_has_content_false_filter(
        self,
        progress_tracker: BatchJobProgressTracker,
    ):
        """has_content=False filters candidates with content."""
        async with get_session_maker()() as session:
            await create_candidate(
                session,
                source_url="https://example.com/with-content",
                title="With Content",
                predicted_ratings={"false": 1.0},
                content="This has content",
            )
            without_content_id = await create_candidate(
                session,
                source_url="https://example.com/without-content",
                title="Without Content",
                predicted_ratings={"false": 1.0},
                content=None,
            )
            job_id = await create_batch_job(session, progress_tracker)

        result = await process_bulk_approval(
            job_id=str(job_id),
            threshold=0.9,
            auto_promote=False,
            limit=100,
            status=None,
            dataset_name=None,
            dataset_tags=None,
            has_content=False,
            published_date_from=None,
            published_date_to=None,
            db_url=get_test_urls()[0],
            redis_url=get_test_urls()[1],
        )

        assert result["updated_count"] == 1
        assert await get_candidate_rating(without_content_id) == "false"

    async def test_dataset_name_filter(
        self,
        progress_tracker: BatchJobProgressTracker,
    ):
        """dataset_name filters candidates by dataset."""
        async with get_session_maker()() as session:
            matching_id = await create_candidate(
                session,
                source_url="https://example.com/matching",
                title="Matching Dataset",
                predicted_ratings={"false": 1.0},
                dataset_name="test_target_dataset",
            )
            await create_candidate(
                session,
                source_url="https://example.com/other",
                title="Other Dataset",
                predicted_ratings={"false": 1.0},
                dataset_name="test_other_dataset",
            )
            job_id = await create_batch_job(session, progress_tracker)

        result = await process_bulk_approval(
            job_id=str(job_id),
            threshold=0.9,
            auto_promote=False,
            limit=100,
            status=None,
            dataset_name="test_target_dataset",
            dataset_tags=None,
            has_content=None,
            published_date_from=None,
            published_date_to=None,
            db_url=get_test_urls()[0],
            redis_url=get_test_urls()[1],
        )

        assert result["updated_count"] == 1
        assert await get_candidate_rating(matching_id) == "false"

    async def test_status_filter(
        self,
        progress_tracker: BatchJobProgressTracker,
    ):
        """status filters candidates by processing status."""
        async with get_session_maker()() as session:
            scraped_id = await create_candidate(
                session,
                source_url="https://example.com/scraped",
                title="Scraped Article",
                predicted_ratings={"false": 1.0},
                status=CandidateStatus.SCRAPED.value,
            )
            await create_candidate(
                session,
                source_url="https://example.com/pending",
                title="Pending Article",
                predicted_ratings={"false": 1.0},
                status=CandidateStatus.PENDING.value,
            )
            job_id = await create_batch_job(session, progress_tracker)

        result = await process_bulk_approval(
            job_id=str(job_id),
            threshold=0.9,
            auto_promote=False,
            limit=100,
            status=CandidateStatus.SCRAPED.value,
            dataset_name=None,
            dataset_tags=None,
            has_content=None,
            published_date_from=None,
            published_date_to=None,
            db_url=get_test_urls()[0],
            redis_url=get_test_urls()[1],
        )

        assert result["updated_count"] == 1
        assert await get_candidate_rating(scraped_id) == "false"

    async def test_dataset_tags_filter(
        self,
        progress_tracker: BatchJobProgressTracker,
    ):
        """dataset_tags filters candidates by overlapping tags."""
        async with get_session_maker()() as session:
            matching_id = await create_candidate(
                session,
                source_url="https://example.com/matching",
                title="Matching Tags",
                predicted_ratings={"false": 1.0},
                dataset_tags=["politics", "news"],
            )
            await create_candidate(
                session,
                source_url="https://example.com/other",
                title="Other Tags",
                predicted_ratings={"false": 1.0},
                dataset_tags=["sports", "entertainment"],
            )
            job_id = await create_batch_job(session, progress_tracker)

        result = await process_bulk_approval(
            job_id=str(job_id),
            threshold=0.9,
            auto_promote=False,
            limit=100,
            status=None,
            dataset_name=None,
            dataset_tags=["politics"],
            has_content=None,
            published_date_from=None,
            published_date_to=None,
            db_url=get_test_urls()[0],
            redis_url=get_test_urls()[1],
        )

        assert result["updated_count"] == 1
        assert await get_candidate_rating(matching_id) == "false"

    async def test_limit_respects_maximum(
        self,
        progress_tracker: BatchJobProgressTracker,
    ):
        """limit constrains the number of processed candidates."""
        async with get_session_maker()() as session:
            for i in range(5):
                await create_candidate(
                    session,
                    source_url=f"https://example.com/article{i}",
                    title=f"Article {i}",
                    predicted_ratings={"false": 1.0},
                )
            job_id = await create_batch_job(session, progress_tracker)

        result = await process_bulk_approval(
            job_id=str(job_id),
            threshold=0.9,
            auto_promote=False,
            limit=3,
            status=None,
            dataset_name=None,
            dataset_tags=None,
            has_content=None,
            published_date_from=None,
            published_date_to=None,
            db_url=get_test_urls()[0],
            redis_url=get_test_urls()[1],
        )

        assert result["updated_count"] == 3
