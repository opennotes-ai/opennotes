# Task 1008: Parallel Scraping and Rate Limit Middleware

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace custom lock managers with TaskIQ middleware using redis-rate-limiters library, and add parallel URL scraping.

**Architecture:** Two phases - (1) Add asyncio.gather parallelism to scraping with semaphore-bounded concurrency, (2) Create reusable TaskIQ middleware that wraps task execution with AsyncSemaphore from redis-rate-limiters, allowing task-level concurrency control via labels. Remove all custom lock managers.

**Tech Stack:** Python 3.11+, redis-rate-limiters (AsyncSemaphore), TaskIQ, Redis

---

## Phase 1: Parallel Scraping (AC #1-2)

### Task 1.1: Add Parallel Scraping Constants

**Files:**
- Modify: `src/tasks/import_tasks.py:1-50`

**Step 1: Add constants at top of file**

After the existing imports, add:

```python
# Parallel scraping configuration
DEFAULT_SCRAPE_CONCURRENCY = 10  # Max concurrent URL scrapes
SCRAPE_URL_TIMEOUT_SECONDS = 60  # Per-URL timeout
```

**Step 2: Verify file compiles**

Run: `cd /Users/mike/code/opennotes-ai/multiverse/worktrees/task-1006-batch-jobs-scrape-promote/opennotes-server && uv run python -c "import src.tasks.import_tasks"`

Expected: No output (successful import)

**Step 3: Commit**

```bash
git add src/tasks/import_tasks.py
git commit -m "feat(scraping): add parallel scraping constants"
```

---

### Task 1.2: Add Concurrency Parameter to process_scrape_batch

**Files:**
- Modify: `src/tasks/import_tasks.py:602-620`

**Step 1: Update function signature**

Change from:
```python
async def process_scrape_batch(
    job_id: str,
    batch_size: int,
    dry_run: bool,
    db_url: str,
    redis_url: str,
    lock_operation: str | None = None,
) -> dict[str, Any]:
```

To:
```python
async def process_scrape_batch(
    job_id: str,
    batch_size: int,
    dry_run: bool,
    db_url: str,
    redis_url: str,
    lock_operation: str | None = None,
    concurrency: int = DEFAULT_SCRAPE_CONCURRENCY,
) -> dict[str, Any]:
```

**Step 2: Update import_service.py dispatch call**

In `src/batch_jobs/import_service.py`, update the `start_scrape_job` method (around line 235) to pass concurrency:

```python
task_result = await process_scrape_batch.kiq(
    str(job.id),
    batch_size,
    dry_run,
    str(db_url),
    str(redis_url),
    lock_operation,
    concurrency,  # Add this
)
```

**Step 3: Verify tests still pass**

Run: `cd /Users/mike/code/opennotes-ai/multiverse/worktrees/task-1006-batch-jobs-scrape-promote/opennotes-server && mise run test:server -- tests/unit/fact_checking/import_pipeline/test_scrape_batch_job.py -v --tb=short`

Expected: All tests pass

**Step 4: Commit**

```bash
git add src/tasks/import_tasks.py src/batch_jobs/import_service.py
git commit -m "feat(scraping): add concurrency parameter to process_scrape_batch"
```

---

### Task 1.3: Create Single URL Scrape Helper with Timeout

**Files:**
- Modify: `src/tasks/import_tasks.py` (add helper function before process_scrape_batch)

**Step 1: Write the failing test**

Create test in `tests/unit/fact_checking/import_pipeline/test_scrape_batch_job.py`:

```python
class TestSingleUrlScrapeHelper:
    """Tests for _scrape_single_url helper function."""

    @pytest.mark.asyncio
    async def test_scrape_single_url_success(self):
        """Successful scrape returns content."""
        with patch("src.tasks.import_tasks.scrape_url_content") as mock_scrape:
            mock_scrape.return_value = "scraped content"

            result = await _scrape_single_url(
                "https://example.com",
                timeout_seconds=10,
            )

            assert result == "scraped content"
            mock_scrape.assert_called_once_with("https://example.com")

    @pytest.mark.asyncio
    async def test_scrape_single_url_timeout(self):
        """Timeout returns None instead of raising."""
        async def slow_scrape(*args):
            await asyncio.sleep(10)
            return "content"

        with patch("src.tasks.import_tasks.asyncio.to_thread", side_effect=slow_scrape):
            result = await _scrape_single_url(
                "https://example.com",
                timeout_seconds=0.1,
            )

            assert result is None

    @pytest.mark.asyncio
    async def test_scrape_single_url_exception(self):
        """Exception returns None instead of raising."""
        with patch("src.tasks.import_tasks.scrape_url_content") as mock_scrape:
            mock_scrape.side_effect = Exception("Network error")

            result = await _scrape_single_url(
                "https://example.com",
                timeout_seconds=10,
            )

            assert result is None
```

**Step 2: Run test to verify it fails**

Run: `mise run test:server -- tests/unit/fact_checking/import_pipeline/test_scrape_batch_job.py::TestSingleUrlScrapeHelper -v`

Expected: FAIL with "NameError: name '_scrape_single_url' is not defined"

**Step 3: Write the implementation**

Add to `src/tasks/import_tasks.py` before `process_scrape_batch`:

```python
async def _scrape_single_url(
    url: str,
    timeout_seconds: float = SCRAPE_URL_TIMEOUT_SECONDS,
) -> str | None:
    """Scrape a single URL with timeout protection.

    Returns:
        Scraped content on success, None on timeout or error.
    """
    try:
        content = await asyncio.wait_for(
            asyncio.to_thread(scrape_url_content, url),
            timeout=timeout_seconds,
        )
        return content
    except asyncio.TimeoutError:
        logger.warning(f"Scrape timeout for URL: {url}")
        return None
    except Exception as e:
        logger.error(f"Scrape error for URL {url}: {e}")
        return None
```

**Step 4: Add import in test file**

```python
from src.tasks.import_tasks import _scrape_single_url
```

**Step 5: Run test to verify it passes**

Run: `mise run test:server -- tests/unit/fact_checking/import_pipeline/test_scrape_batch_job.py::TestSingleUrlScrapeHelper -v`

Expected: All 3 tests pass

**Step 6: Commit**

```bash
git add src/tasks/import_tasks.py tests/unit/fact_checking/import_pipeline/test_scrape_batch_job.py
git commit -m "feat(scraping): add _scrape_single_url helper with timeout protection"
```

---

### Task 1.4: Implement Parallel Scraping with asyncio.gather

**Files:**
- Modify: `src/tasks/import_tasks.py:726-808` (main processing loop)

**Step 1: Write the failing test**

Add to `tests/unit/fact_checking/import_pipeline/test_scrape_batch_job.py`:

```python
class TestParallelScraping:
    """Tests for parallel URL scraping with asyncio.gather."""

    @pytest.mark.asyncio
    async def test_parallel_scrape_processes_multiple_urls_concurrently(self):
        """Verifies multiple URLs are scraped in parallel, not sequentially."""
        scrape_start_times = []

        async def track_scrape_timing(*args, **kwargs):
            scrape_start_times.append(asyncio.get_event_loop().time())
            await asyncio.sleep(0.1)  # Simulate network delay
            return "content"

        with patch("src.tasks.import_tasks._scrape_single_url", side_effect=track_scrape_timing):
            # Setup: Create mock with 5 candidates
            candidate_rows = [(uuid4(), f"https://example.com/{i}") for i in range(5)]

            # ... (full test setup with mocks)

            # If parallel, all 5 should start within 50ms of each other
            # If sequential, they'd be 100ms apart
            time_span = max(scrape_start_times) - min(scrape_start_times)
            assert time_span < 0.05, f"Scrapes not parallel: {time_span}s spread"

    @pytest.mark.asyncio
    async def test_parallel_scrape_respects_concurrency_limit(self):
        """Verifies semaphore limits concurrent scrapes."""
        concurrent_count = [0]
        max_concurrent = [0]

        async def track_concurrency(*args, **kwargs):
            concurrent_count[0] += 1
            max_concurrent[0] = max(max_concurrent[0], concurrent_count[0])
            await asyncio.sleep(0.1)
            concurrent_count[0] -= 1
            return "content"

        with patch("src.tasks.import_tasks._scrape_single_url", side_effect=track_concurrency):
            # Setup: 20 candidates, concurrency=5
            # ... (full test setup)

            assert max_concurrent[0] <= 5, f"Exceeded concurrency limit: {max_concurrent[0]}"
```

**Step 2: Run tests to verify they fail**

Run: `mise run test:server -- tests/unit/fact_checking/import_pipeline/test_scrape_batch_job.py::TestParallelScraping -v`

Expected: FAIL (current implementation is sequential)

**Step 3: Refactor process_scrape_batch for parallel execution**

Replace the sequential while loop (lines 726-808) with batch-based parallel processing:

```python
# Create semaphore for concurrency control
semaphore = asyncio.Semaphore(concurrency)

async def process_candidate(candidate_id: UUID, source_url: str) -> tuple[bool, str | None]:
    """Process a single candidate with semaphore-bounded concurrency."""
    async with semaphore:
        # Scrape with timeout protection
        content = await _scrape_single_url(source_url, SCRAPE_URL_TIMEOUT_SECONDS)

        # Update candidate in database
        async with async_session() as db:
            if content:
                await db.execute(
                    update(FactCheckedItemCandidate)
                    .where(FactCheckedItemCandidate.id == candidate_id)
                    .values(
                        status=CandidateStatus.SCRAPED.value,
                        content=content,
                    )
                )
                await db.commit()
                return (True, None)  # success
            else:
                await db.execute(
                    update(FactCheckedItemCandidate)
                    .where(FactCheckedItemCandidate.id == candidate_id)
                    .values(
                        status=CandidateStatus.SCRAPE_FAILED.value,
                        error_message="Scrape returned no content",
                    )
                )
                await db.commit()
                return (False, "Scrape returned no content")  # failure

# Main processing loop - fetch batches and process in parallel
while True:
    async with async_session() as db:
        # Fetch batch of candidates
        candidate_query = (
            select(
                FactCheckedItemCandidate.id,
                FactCheckedItemCandidate.source_url,
            )
            .where(FactCheckedItemCandidate.status == CandidateStatus.PENDING.value)
            .where(FactCheckedItemCandidate.content.is_(None))
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )
        result = await db.execute(candidate_query)
        candidates = result.fetchall()

        if not candidates:
            break

        # Mark all as SCRAPING
        candidate_ids = [c[0] for c in candidates]
        await db.execute(
            update(FactCheckedItemCandidate)
            .where(FactCheckedItemCandidate.id.in_(candidate_ids))
            .values(status=CandidateStatus.SCRAPING.value)
        )
        await db.commit()

    # Process batch in parallel with gather
    tasks = [
        process_candidate(candidate_id, source_url)
        for candidate_id, source_url in candidates
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Aggregate results
    for result in results:
        if isinstance(result, Exception):
            failed += 1
            errors.append(str(result))
        elif result[0]:  # success
            scraped += 1
        else:  # failure
            failed += 1
            if result[1]:
                errors.append(result[1])

    # Update progress
    processed = scraped + failed
    await _update_progress(progress_tracker, job_id, processed, total_tasks)
```

**Step 4: Run tests to verify they pass**

Run: `mise run test:server -- tests/unit/fact_checking/import_pipeline/test_scrape_batch_job.py -v --tb=short`

Expected: All tests pass

**Step 5: Commit**

```bash
git add src/tasks/import_tasks.py tests/unit/fact_checking/import_pipeline/test_scrape_batch_job.py
git commit -m "feat(scraping): implement parallel URL scraping with asyncio.gather"
```

---

## Phase 2: Add redis-rate-limiters Dependency (AC #3-5)

### Task 2.1: Add Dependency

**Files:**
- Modify: `pyproject.toml`

**Step 1: Add dependency**

Run: `cd /Users/mike/code/opennotes-ai/multiverse/worktrees/task-1006-batch-jobs-scrape-promote/opennotes-server && uv add redis-rate-limiters`

**Step 2: Verify installation**

Run: `uv run python -c "from limiters import AsyncSemaphore; print('OK')"`

Expected: `OK`

**Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "feat(deps): add redis-rate-limiters for distributed rate limiting"
```

---

### Task 2.2: Create Proof-of-Concept Test

**Files:**
- Create: `tests/integration/test_redis_rate_limiters.py`

**Step 1: Write integration test**

```python
"""Integration tests for redis-rate-limiters library.

Verifies the AsyncSemaphore works correctly with our Redis setup.
"""
import asyncio
import pytest
from limiters import AsyncSemaphore
from redis.asyncio import Redis


@pytest.fixture
async def redis_client():
    """Create Redis client for testing."""
    client = Redis.from_url("redis://localhost:6379")
    yield client
    await client.aclose()


class TestAsyncSemaphoreIntegration:
    """Integration tests for AsyncSemaphore."""

    @pytest.mark.asyncio
    async def test_semaphore_limits_concurrency(self, redis_client):
        """Verify semaphore limits concurrent access."""
        semaphore = AsyncSemaphore(
            name="test:concurrency",
            capacity=2,
            max_sleep=5,
            expiry=30,
            connection=redis_client,
        )

        concurrent_count = [0]
        max_concurrent = [0]

        async def work():
            async with semaphore:
                concurrent_count[0] += 1
                max_concurrent[0] = max(max_concurrent[0], concurrent_count[0])
                await asyncio.sleep(0.1)
                concurrent_count[0] -= 1

        # Launch 10 tasks with capacity=2
        await asyncio.gather(*[work() for _ in range(10)])

        assert max_concurrent[0] == 2, f"Expected max 2 concurrent, got {max_concurrent[0]}"

    @pytest.mark.asyncio
    async def test_semaphore_releases_on_exception(self, redis_client):
        """Verify semaphore is released when exception occurs."""
        semaphore = AsyncSemaphore(
            name="test:exception",
            capacity=1,
            max_sleep=2,
            expiry=30,
            connection=redis_client,
        )

        # First task raises exception
        with pytest.raises(ValueError):
            async with semaphore:
                raise ValueError("test error")

        # Second task should acquire immediately (not wait)
        acquired = False
        async with semaphore:
            acquired = True

        assert acquired, "Semaphore not released after exception"

    @pytest.mark.asyncio
    async def test_different_names_are_independent(self, redis_client):
        """Verify different semaphore names don't block each other."""
        sem_a = AsyncSemaphore(
            name="test:name_a",
            capacity=1,
            max_sleep=1,
            expiry=30,
            connection=redis_client,
        )
        sem_b = AsyncSemaphore(
            name="test:name_b",
            capacity=1,
            max_sleep=1,
            expiry=30,
            connection=redis_client,
        )

        results = []

        async def use_a():
            async with sem_a:
                results.append("a_start")
                await asyncio.sleep(0.2)
                results.append("a_end")

        async def use_b():
            async with sem_b:
                results.append("b_start")
                await asyncio.sleep(0.1)
                results.append("b_end")

        await asyncio.gather(use_a(), use_b())

        # Both should start immediately (not blocked by each other)
        assert results[0] in ("a_start", "b_start")
        assert results[1] in ("a_start", "b_start")
```

**Step 2: Run tests**

Run: `mise run test:server -- tests/integration/test_redis_rate_limiters.py -v --tb=short`

Expected: All 3 tests pass (requires Redis running)

**Step 3: Commit**

```bash
git add tests/integration/test_redis_rate_limiters.py
git commit -m "test(integration): add redis-rate-limiters proof-of-concept tests"
```

---

## Phase 3: Create RateLimitMiddleware (AC #6-8, #15)

### Task 3.1: Create Middleware Module with Tests

**Files:**
- Create: `src/tasks/rate_limit_middleware.py`
- Create: `tests/unit/tasks/test_rate_limit_middleware.py`

**Step 1: Write the failing tests first**

```python
"""Unit tests for DistributedRateLimitMiddleware."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.tasks.rate_limit_middleware import (
    DistributedRateLimitMiddleware,
    RATE_LIMIT_NAME,
    RATE_LIMIT_CAPACITY,
    RATE_LIMIT_MAX_SLEEP,
    RATE_LIMIT_EXPIRY,
)


class TestDistributedRateLimitMiddleware:
    """Tests for DistributedRateLimitMiddleware."""

    @pytest.fixture
    def middleware(self):
        """Create middleware instance."""
        redis_url = "redis://localhost:6379"
        return DistributedRateLimitMiddleware(redis_url)

    @pytest.mark.asyncio
    async def test_pre_execute_acquires_semaphore_when_labels_present(self, middleware):
        """Middleware acquires semaphore when task has rate_limit_name label."""
        message = MagicMock()
        message.labels = {
            RATE_LIMIT_NAME: "import:fact_check",
            RATE_LIMIT_CAPACITY: "1",
            RATE_LIMIT_MAX_SLEEP: "30",
        }

        mock_semaphore = AsyncMock()
        mock_semaphore.__aenter__ = AsyncMock()

        with patch.object(middleware, "_get_semaphore", return_value=mock_semaphore):
            result = await middleware.pre_execute(message)

        assert result == message
        mock_semaphore.__aenter__.assert_called_once()

    @pytest.mark.asyncio
    async def test_pre_execute_skips_when_no_rate_limit_labels(self, middleware):
        """Middleware does nothing when task has no rate_limit_name label."""
        message = MagicMock()
        message.labels = {"component": "import_pipeline"}

        result = await middleware.pre_execute(message)

        assert result == message

    @pytest.mark.asyncio
    async def test_post_execute_releases_semaphore(self, middleware):
        """Middleware releases semaphore after task execution."""
        message = MagicMock()
        message.labels = {RATE_LIMIT_NAME: "test:lock"}
        result = {"status": "success"}

        mock_semaphore = AsyncMock()
        mock_semaphore.__aexit__ = AsyncMock(return_value=False)
        middleware._active_semaphores[id(message)] = mock_semaphore

        await middleware.post_execute(message, result)

        mock_semaphore.__aexit__.assert_called_once()
        assert id(message) not in middleware._active_semaphores

    @pytest.mark.asyncio
    async def test_on_error_releases_semaphore(self, middleware):
        """Middleware releases semaphore on task error."""
        message = MagicMock()
        message.labels = {RATE_LIMIT_NAME: "test:lock"}
        error = ValueError("test error")

        mock_semaphore = AsyncMock()
        mock_semaphore.__aexit__ = AsyncMock(return_value=False)
        middleware._active_semaphores[id(message)] = mock_semaphore

        await middleware.on_error(message, error)

        mock_semaphore.__aexit__.assert_called_once()
```

**Step 2: Run tests to verify they fail**

Run: `mise run test:server -- tests/unit/tasks/test_rate_limit_middleware.py -v`

Expected: FAIL with import error

**Step 3: Create the middleware implementation**

```python
"""Distributed rate limiting middleware for TaskIQ.

Wraps task execution with AsyncSemaphore from redis-rate-limiters library,
allowing task-level concurrency control via labels.

Designed to be extractable as a standalone package (taskiq-redis-ratelimit).

Label Configuration:
    rate_limit_name: Required. Lock signature/name (e.g., "import:fact_check")
    rate_limit_capacity: Optional. Max concurrent permits (default: 1)
    rate_limit_max_sleep: Optional. Seconds before MaxSleepExceededError (default: 30)
    rate_limit_expiry: Optional. Redis key TTL in seconds (default: 1800)

Example:
    @register_task(
        task_name="import:candidates",
        rate_limit_name="import:fact_check",
        rate_limit_capacity="1",
    )
    async def my_task():
        ...
"""
from __future__ import annotations

import logging
from typing import Any

from limiters import AsyncSemaphore
from redis.asyncio import Redis
from taskiq import TaskiqMessage, TaskiqMiddleware, TaskiqResult

logger = logging.getLogger(__name__)

# Label keys for task configuration
RATE_LIMIT_NAME = "rate_limit_name"
RATE_LIMIT_CAPACITY = "rate_limit_capacity"
RATE_LIMIT_MAX_SLEEP = "rate_limit_max_sleep"
RATE_LIMIT_EXPIRY = "rate_limit_expiry"

# Default values
DEFAULT_CAPACITY = 1
DEFAULT_MAX_SLEEP = 30  # seconds
DEFAULT_EXPIRY = 1800  # 30 minutes


class DistributedRateLimitMiddleware(TaskiqMiddleware):
    """TaskIQ middleware for distributed rate limiting using redis-rate-limiters.

    Provides semaphore-based concurrency control for tasks. Tasks opt-in by
    setting the `rate_limit_name` label.

    This middleware is designed to be framework-agnostic and easily extractable
    as a standalone package.
    """

    def __init__(self, redis_url: str) -> None:
        """Initialize middleware.

        Args:
            redis_url: Redis connection URL (e.g., "redis://localhost:6379")
        """
        self._redis_url = redis_url
        self._redis: Redis | None = None
        self._active_semaphores: dict[int, AsyncSemaphore] = {}

    async def startup(self) -> None:
        """Initialize Redis connection on broker startup."""
        self._redis = Redis.from_url(self._redis_url)
        logger.info("DistributedRateLimitMiddleware started")

    async def shutdown(self) -> None:
        """Close Redis connection on broker shutdown."""
        if self._redis:
            await self._redis.aclose()
            self._redis = None
        logger.info("DistributedRateLimitMiddleware stopped")

    def _get_semaphore(
        self,
        name: str,
        capacity: int = DEFAULT_CAPACITY,
        max_sleep: int = DEFAULT_MAX_SLEEP,
        expiry: int = DEFAULT_EXPIRY,
    ) -> AsyncSemaphore:
        """Create AsyncSemaphore for the given configuration."""
        if self._redis is None:
            raise RuntimeError("Middleware not started - call startup() first")

        return AsyncSemaphore(
            name=name,
            capacity=capacity,
            max_sleep=max_sleep,
            expiry=expiry,
            connection=self._redis,
        )

    async def pre_execute(self, message: TaskiqMessage) -> TaskiqMessage:
        """Acquire semaphore before task execution if rate_limit_name is set."""
        labels = message.labels or {}
        rate_limit_name = labels.get(RATE_LIMIT_NAME)

        if not rate_limit_name:
            return message

        # Parse configuration from labels
        capacity = int(labels.get(RATE_LIMIT_CAPACITY, DEFAULT_CAPACITY))
        max_sleep = int(labels.get(RATE_LIMIT_MAX_SLEEP, DEFAULT_MAX_SLEEP))
        expiry = int(labels.get(RATE_LIMIT_EXPIRY, DEFAULT_EXPIRY))

        logger.debug(
            f"Acquiring rate limit: name={rate_limit_name}, capacity={capacity}"
        )

        semaphore = self._get_semaphore(rate_limit_name, capacity, max_sleep, expiry)
        await semaphore.__aenter__()

        # Store for release in post_execute/on_error
        self._active_semaphores[id(message)] = semaphore

        return message

    async def post_execute(
        self, message: TaskiqMessage, result: TaskiqResult[Any]
    ) -> None:
        """Release semaphore after successful task execution."""
        await self._release_semaphore(message)

    async def on_error(
        self,
        message: TaskiqMessage,
        result: BaseException,
        exception: BaseException,
    ) -> None:
        """Release semaphore on task error."""
        await self._release_semaphore(message)

    async def _release_semaphore(self, message: TaskiqMessage) -> None:
        """Release the semaphore for a message if one was acquired."""
        semaphore = self._active_semaphores.pop(id(message), None)
        if semaphore:
            try:
                await semaphore.__aexit__(None, None, None)
                logger.debug(f"Released rate limit for task {message.task_name}")
            except Exception as e:
                logger.error(f"Error releasing semaphore: {e}")
```

**Step 4: Run tests to verify they pass**

Run: `mise run test:server -- tests/unit/tasks/test_rate_limit_middleware.py -v --tb=short`

Expected: All tests pass

**Step 5: Commit**

```bash
git add src/tasks/rate_limit_middleware.py tests/unit/tasks/test_rate_limit_middleware.py
git commit -m "feat(tasks): add DistributedRateLimitMiddleware for TaskIQ"
```

---

### Task 3.2: Integrate Middleware into Broker

**Files:**
- Modify: `src/tasks/broker.py`

**Step 1: Add middleware import and registration**

After the existing middleware imports (around line 50), add:

```python
from src.tasks.rate_limit_middleware import DistributedRateLimitMiddleware
```

In the broker configuration section (around line 170), add the middleware:

```python
# Add rate limit middleware
rate_limit_middleware = DistributedRateLimitMiddleware(
    redis_url=str(settings.REDIS_URL),
)
broker.add_middlewares([rate_limit_middleware])
```

**Step 2: Verify broker still starts**

Run: `cd /Users/mike/code/opennotes-ai/multiverse/worktrees/task-1006-batch-jobs-scrape-promote/opennotes-server && uv run python -c "from src.tasks.broker import broker; print('OK')"`

Expected: `OK`

**Step 3: Commit**

```bash
git add src/tasks/broker.py
git commit -m "feat(broker): integrate DistributedRateLimitMiddleware"
```

---

## Phase 4: Migration - Remove Custom Lock Managers (AC #9-13)

### Task 4.1: Add Rate Limit Labels to Tasks

**Files:**
- Modify: `src/tasks/import_tasks.py` (task decorators)
- Modify: `src/tasks/rechunk_tasks.py` (task decorators)

**Step 1: Update import_tasks.py task decorators**

For `process_fact_check_import`:
```python
@register_task(
    task_name="import:fact_check_bureau",
    component="import_pipeline",
    task_type="batch",
    rate_limit_name="import:fact_check",
    rate_limit_capacity="1",
)
```

For `process_scrape_batch`:
```python
@register_task(
    task_name="scrape:candidates",
    component="import_pipeline",
    task_type="batch",
    rate_limit_name="scrape:candidates",
    rate_limit_capacity="1",
)
```

For `process_promotion_batch`:
```python
@register_task(
    task_name="promote:candidates",
    component="import_pipeline",
    task_type="batch",
    rate_limit_name="promote:candidates",
    rate_limit_capacity="1",
)
```

**Step 2: Update rechunk_tasks.py task decorators**

For `process_fact_check_rechunk`:
```python
@register_task(
    task_name="rechunk:fact_check",
    component="rechunk",
    task_type="batch",
    rate_limit_name="rechunk:fact_check",
    rate_limit_capacity="1",
)
```

For `process_previously_seen_rechunk`:
```python
@register_task(
    task_name="rechunk:previously_seen",
    component="rechunk",
    task_type="batch",
    rate_limit_name="rechunk:previously_seen:{community_server_id}",
    rate_limit_capacity="1",
)
```

**Step 3: Verify tasks still register**

Run: `uv run python -c "from src.tasks import import_tasks, rechunk_tasks; print('OK')"`

Expected: `OK`

**Step 4: Commit**

```bash
git add src/tasks/import_tasks.py src/tasks/rechunk_tasks.py
git commit -m "feat(tasks): add rate_limit labels to batch tasks"
```

---

### Task 4.2: Remove lock_operation Parameter from Tasks

**Files:**
- Modify: `src/tasks/import_tasks.py`
- Modify: `src/batch_jobs/import_service.py`

**Step 1: Remove lock_operation from function signatures**

In `process_fact_check_import`, `process_scrape_batch`, `process_promotion_batch`:

Remove `lock_operation: str | None = None` from parameters.

**Step 2: Remove _release_job_lock calls from finally blocks**

In each task's finally block, remove:
```python
if lock_operation:
    await _release_job_lock(redis_client, lock_operation, job_id)
```

**Step 3: Remove _release_job_lock function entirely**

Delete the `_release_job_lock` helper function (around lines 55-89).

**Step 4: Update import_service.py dispatch calls**

Remove `lock_operation` from all `.kiq()` calls.

**Step 5: Run tests**

Run: `mise run test:server -- tests/unit/batch_jobs/ tests/unit/fact_checking/ -v --tb=short`

Expected: Some tests may fail due to mocking lock_operation - update those tests.

**Step 6: Update failing tests**

Remove lock_operation from test mocks and assertions.

**Step 7: Commit**

```bash
git add src/tasks/import_tasks.py src/batch_jobs/import_service.py tests/
git commit -m "refactor(tasks): remove lock_operation parameter (now handled by middleware)"
```

---

### Task 4.3: Remove Lock Managers from Services

**Files:**
- Modify: `src/batch_jobs/import_service.py`
- Modify: `src/batch_jobs/rechunk_service.py`

**Step 1: Remove lock acquisition from import_service.py**

In `ImportBatchJobService.__init__`, remove `_lock_manager` parameter and storage.

In `start_import_job`, `start_scrape_job`, `start_promotion_job`:
- Remove lock acquisition code
- Remove lock release on failure code
- Remove `ConcurrentJobError` raising (middleware handles this now)

**Step 2: Remove lock acquisition from rechunk_service.py**

Same pattern - remove all lock manager interactions.

**Step 3: Update tests**

Remove `mock_lock_manager` fixtures and related assertions.

**Step 4: Run tests**

Run: `mise run test:server -- tests/unit/batch_jobs/ -v --tb=short`

Expected: All tests pass

**Step 5: Commit**

```bash
git add src/batch_jobs/import_service.py src/batch_jobs/rechunk_service.py tests/
git commit -m "refactor(services): remove manual lock management (now handled by middleware)"
```

---

### Task 4.4: Delete Lock Manager Files

**Files:**
- Delete: `src/fact_checking/rechunk_lock.py`
- Modify: `src/fact_checking/import_pipeline/router.py`

**Step 1: Delete rechunk_lock.py**

```bash
rm src/fact_checking/rechunk_lock.py
```

**Step 2: Remove _GlobalImportLockManager from router.py**

Delete the class definition and `import_lock_manager` instance.

Remove from dependency injection in router endpoints.

**Step 3: Remove imports referencing deleted code**

Search for imports of `RechunkLockManager`, `TaskRechunkLockManager`, `_GlobalImportLockManager` and remove them.

**Step 4: Update router to return 409 on middleware rejection**

The middleware raises `MaxSleepExceededError`. Add exception handler in router:

```python
from limiters import MaxSleepExceededError

@router.exception_handler(MaxSleepExceededError)
async def handle_rate_limit(request, exc):
    return JSONResponse(
        status_code=409,
        content={"detail": "A concurrent job is already running. Please wait."},
    )
```

**Step 5: Run full test suite**

Run: `mise run test:server -- -v --tb=short`

Expected: All tests pass

**Step 6: Commit**

```bash
git add -A
git commit -m "refactor: delete custom lock managers (replaced by middleware)"
```

---

## Phase 5: Integration Tests (AC #14)

### Task 5.1: Create Comprehensive Integration Tests

**Files:**
- Create: `tests/integration/test_rate_limit_middleware.py`

**Step 1: Write integration tests**

```python
"""Integration tests for DistributedRateLimitMiddleware."""
import asyncio
import pytest
from unittest.mock import patch

from src.tasks.broker import broker
from src.tasks.rate_limit_middleware import RATE_LIMIT_NAME, RATE_LIMIT_CAPACITY


class TestRateLimitMiddlewareIntegration:
    """Integration tests for rate limit middleware with actual TaskIQ broker."""

    @pytest.mark.asyncio
    async def test_capacity_1_serializes_concurrent_tasks(self):
        """Tasks with capacity=1 execute one at a time."""
        execution_order = []

        @broker.task(
            task_name="test:serial",
            rate_limit_name="test:serial",
            rate_limit_capacity="1",
        )
        async def serial_task(task_id: int):
            execution_order.append(f"start_{task_id}")
            await asyncio.sleep(0.1)
            execution_order.append(f"end_{task_id}")

        # Launch 3 tasks "concurrently"
        await asyncio.gather(
            serial_task(1),
            serial_task(2),
            serial_task(3),
        )

        # Should be strictly serialized: start_1, end_1, start_2, end_2, ...
        for i in range(3):
            assert execution_order[i*2] == f"start_{i+1}"
            assert execution_order[i*2+1] == f"end_{i+1}"

    @pytest.mark.asyncio
    async def test_capacity_n_allows_n_parallel(self):
        """Tasks with capacity=N allow N concurrent executions."""
        concurrent_count = [0]
        max_concurrent = [0]

        @broker.task(
            task_name="test:parallel",
            rate_limit_name="test:parallel",
            rate_limit_capacity="3",
        )
        async def parallel_task():
            concurrent_count[0] += 1
            max_concurrent[0] = max(max_concurrent[0], concurrent_count[0])
            await asyncio.sleep(0.1)
            concurrent_count[0] -= 1

        # Launch 10 tasks
        await asyncio.gather(*[parallel_task() for _ in range(10)])

        assert max_concurrent[0] == 3

    @pytest.mark.asyncio
    async def test_lock_released_on_task_error(self):
        """Lock is released even when task raises exception."""
        @broker.task(
            task_name="test:error",
            rate_limit_name="test:error",
            rate_limit_capacity="1",
        )
        async def error_task(should_fail: bool):
            if should_fail:
                raise ValueError("Intentional failure")
            return "success"

        # First task fails
        with pytest.raises(ValueError):
            await error_task(True)

        # Second task should succeed (lock was released)
        result = await error_task(False)
        assert result == "success"

    @pytest.mark.asyncio
    async def test_different_lock_names_independent(self):
        """Tasks with different rate_limit_name don't block each other."""
        results = []

        @broker.task(
            task_name="test:name_a",
            rate_limit_name="test:lock_a",
            rate_limit_capacity="1",
        )
        async def task_a():
            results.append("a_start")
            await asyncio.sleep(0.2)
            results.append("a_end")

        @broker.task(
            task_name="test:name_b",
            rate_limit_name="test:lock_b",
            rate_limit_capacity="1",
        )
        async def task_b():
            results.append("b_start")
            await asyncio.sleep(0.1)
            results.append("b_end")

        await asyncio.gather(task_a(), task_b())

        # Both should start immediately
        assert "a_start" in results[:2]
        assert "b_start" in results[:2]
```

**Step 2: Run integration tests**

Run: `mise run test:server -- tests/integration/test_rate_limit_middleware.py -v`

Expected: All tests pass

**Step 3: Commit**

```bash
git add tests/integration/test_rate_limit_middleware.py
git commit -m "test(integration): add comprehensive rate limit middleware tests"
```

---

## Final Verification

### Task 6.1: Run Full Test Suite

**Step 1: Run all tests**

Run: `mise run test:server -- -v --tb=short 2>&1 | tee /tmp/final_test_output.log`

**Step 2: Verify no regressions**

Expected: All tests pass

**Step 3: Final commit and push**

```bash
git push origin task-1006-batch-jobs-scrape-promote
```

---

## Summary

This plan implements all 15 acceptance criteria:

| AC | Description | Implementation |
|----|-------------|----------------|
| #1 | asyncio.gather with semaphore | Task 1.4 |
| #2 | Per-URL timeout | Task 1.3 |
| #3 | Evaluate libraries | Task 2.2 |
| #4 | Replace with AsyncSemaphore | Task 3.1 |
| #5 | Add dependency | Task 2.1 |
| #6 | Create middleware | Task 3.1 |
| #7 | Extract Redis from backend | Task 3.1 |
| #8 | Task-level labels | Task 4.1 |
| #9 | Remove RechunkLockManager | Task 4.4 |
| #10 | Remove _GlobalImportLockManager | Task 4.4 |
| #11 | Remove manual locking | Task 4.3 |
| #12 | Update tasks with labels | Task 4.1 |
| #13 | Remove HTTP 409 logic | Task 4.4 |
| #14 | Integration tests | Task 5.1 |
| #15 | Standalone package design | Task 3.1 |
