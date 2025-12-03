import asyncio
import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from src.webhooks.queue import TaskQueue, process_task_worker, retry_processor_worker, task_queue
from tests.redis_mock import create_stateful_redis_mock

pytestmark = pytest.mark.unit


@pytest.fixture
async def queue():
    q = TaskQueue()
    q.redis_client = create_stateful_redis_mock()
    return q


@pytest.fixture
async def connected_queue():
    q = TaskQueue()
    mock_redis = create_stateful_redis_mock()
    q.redis_client = mock_redis
    return q


class TestTaskQueue:
    @pytest.mark.asyncio
    async def test_init(self):
        q = TaskQueue()
        assert q.redis_client is None
        assert q.queue_name == "webhook:tasks"
        assert q.processing_set == "webhook:processing"
        assert q.retry_set == "webhook:retry"

    @pytest.mark.asyncio
    async def test_connect(self):
        q = TaskQueue()
        with patch("redis.asyncio.from_url", new_callable=AsyncMock) as mock_from_url:
            mock_redis = AsyncMock()
            mock_from_url.return_value = mock_redis

            await q.connect()

            assert q.redis_client == mock_redis
            mock_from_url.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect(self):
        q = TaskQueue()
        mock_redis = AsyncMock()
        q.redis_client = mock_redis
        await q.disconnect()
        mock_redis.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect_when_not_connected(self):
        q = TaskQueue()
        await q.disconnect()

    @pytest.mark.asyncio
    async def test_enqueue_without_connection(self):
        q = TaskQueue()
        with patch("redis.asyncio.from_url", new_callable=AsyncMock) as mock_from_url:
            mock_from_url.side_effect = ConnectionError("Redis connection failed")
            with pytest.raises(
                RuntimeError, match="Redis client not connected and reconnection failed"
            ):
                await q.enqueue("test_task", {"data": "value"})

    @pytest.mark.asyncio
    async def test_enqueue_success(self, connected_queue):
        task_type = "webhook_process"
        task_data = {"interaction_id": "123", "community_server_id": "456"}
        priority = 5

        connected_queue.redis_client.zadd = AsyncMock()

        task_id = await connected_queue.enqueue(task_type, task_data, priority)

        assert task_id.startswith(f"{task_type}:")
        connected_queue.redis_client.zadd.assert_called_once()

        call_args = connected_queue.redis_client.zadd.call_args
        assert call_args[0][0] == "webhook:tasks"

        task_json = next(iter(call_args[0][1].keys()))
        task = json.loads(task_json)
        assert task["type"] == task_type
        assert task["data"] == task_data
        assert task["retry_count"] == 0
        assert "created_at" in task

    @pytest.mark.asyncio
    async def test_enqueue_default_priority(self, connected_queue):
        connected_queue.redis_client.zadd = AsyncMock()

        await connected_queue.enqueue("test", {})

        call_args = connected_queue.redis_client.zadd.call_args
        priority = next(iter(call_args[0][1].values()))
        assert priority == 0

    @pytest.mark.asyncio
    async def test_dequeue_without_connection(self):
        q = TaskQueue()
        with patch("redis.asyncio.from_url", new_callable=AsyncMock) as mock_from_url:
            mock_from_url.side_effect = ConnectionError("Redis connection failed")
            with pytest.raises(
                RuntimeError, match="Redis client not connected and reconnection failed"
            ):
                await q.dequeue()

    @pytest.mark.asyncio
    async def test_dequeue_empty_queue(self, connected_queue):
        connected_queue.redis_client.zpopmin = AsyncMock(return_value=[])

        result = await connected_queue.dequeue()

        assert result is None
        connected_queue.redis_client.zpopmin.assert_called_once_with("webhook:tasks", count=1)

    @pytest.mark.asyncio
    async def test_dequeue_success(self, connected_queue):
        task = {
            "id": "webhook_process:123",
            "type": "webhook_process",
            "data": {"test": "data"},
            "retry_count": 0,
            "created_at": datetime.now(UTC).isoformat(),
        }
        task_json = json.dumps(task)

        connected_queue.redis_client.zpopmin = AsyncMock(return_value=[(task_json, 0)])
        connected_queue.redis_client.sadd = AsyncMock()

        result = await connected_queue.dequeue()

        assert result == task
        connected_queue.redis_client.zpopmin.assert_called_once()
        connected_queue.redis_client.sadd.assert_called_once_with("webhook:processing", task["id"])

    @pytest.mark.asyncio
    async def test_complete_task_without_connection(self):
        q = TaskQueue()
        with patch("redis.asyncio.from_url", new_callable=AsyncMock) as mock_from_url:
            mock_from_url.side_effect = ConnectionError("Redis connection failed")
            with pytest.raises(
                RuntimeError, match="Redis client not connected and reconnection failed"
            ):
                await q.complete_task("task_id")

    @pytest.mark.asyncio
    async def test_complete_task_success(self, connected_queue):
        task_id = "webhook_process:123"
        connected_queue.redis_client.srem = AsyncMock()

        await connected_queue.complete_task(task_id)

        connected_queue.redis_client.srem.assert_called_once_with("webhook:processing", task_id)

    @pytest.mark.asyncio
    async def test_retry_task_without_connection(self):
        q = TaskQueue()
        with patch("redis.asyncio.from_url", new_callable=AsyncMock) as mock_from_url:
            mock_from_url.side_effect = ConnectionError("Redis connection failed")
            with pytest.raises(
                RuntimeError, match="Redis client not connected and reconnection failed"
            ):
                await q.retry_task({"id": "test"}, "error")

    @pytest.mark.asyncio
    async def test_retry_task_first_retry(self, connected_queue):
        task = {
            "id": "webhook_process:123",
            "type": "webhook_process",
            "data": {"test": "data"},
            "retry_count": 0,
            "created_at": datetime.now(UTC).isoformat(),
        }
        error = "Connection timeout"

        connected_queue.redis_client.zadd = AsyncMock()
        connected_queue.redis_client.srem = AsyncMock()

        result = await connected_queue.retry_task(task, error)

        assert result is True
        assert task["retry_count"] == 1
        assert task["last_error"] == error
        assert "last_retry" in task

        connected_queue.redis_client.zadd.assert_called_once()
        connected_queue.redis_client.srem.assert_called_once_with("webhook:processing", task["id"])

    @pytest.mark.asyncio
    async def test_retry_task_exceeds_max_retries(self, connected_queue):
        task = {
            "id": "webhook_process:123",
            "type": "webhook_process",
            "data": {"test": "data"},
            "retry_count": 3,
            "created_at": datetime.now(UTC).isoformat(),
        }
        error = "Persistent error"

        connected_queue.redis_client.srem = AsyncMock()

        with patch("src.webhooks.queue.settings") as mock_settings:
            mock_settings.QUEUE_MAX_RETRIES = 3
            result = await connected_queue.retry_task(task, error)

        assert result is False
        assert task["retry_count"] == 4
        connected_queue.redis_client.srem.assert_called_once_with("webhook:processing", task["id"])

    @pytest.mark.asyncio
    async def test_retry_task_backoff_calculation(self, connected_queue):
        task = {
            "id": "webhook_process:123",
            "type": "webhook_process",
            "data": {"test": "data"},
            "retry_count": 2,
            "created_at": datetime.now(UTC).isoformat(),
        }

        connected_queue.redis_client.zadd = AsyncMock()
        connected_queue.redis_client.srem = AsyncMock()

        with patch("src.webhooks.queue.settings") as mock_settings:
            mock_settings.QUEUE_MAX_RETRIES = 5
            mock_settings.QUEUE_RETRY_DELAY = 1
            mock_settings.QUEUE_RETRY_BACKOFF = 2.0

            await connected_queue.retry_task(task, "error")

        call_args = connected_queue.redis_client.zadd.call_args
        next(iter(call_args[0][1].keys()))
        retry_time = next(iter(call_args[0][1].values()))

        now = datetime.now(UTC).timestamp()
        expected_delay = 1 * (2.0**2)
        assert retry_time > now
        assert retry_time < now + expected_delay + 1

    @pytest.mark.asyncio
    async def test_process_retries_without_connection(self):
        q = TaskQueue()
        with patch("redis.asyncio.from_url", new_callable=AsyncMock) as mock_from_url:
            mock_from_url.side_effect = ConnectionError("Redis connection failed")
            with pytest.raises(
                RuntimeError, match="Redis client not connected and reconnection failed"
            ):
                await q.process_retries()

    @pytest.mark.asyncio
    async def test_process_retries_empty(self, connected_queue):
        connected_queue.redis_client.zrangebyscore = AsyncMock(return_value=[])

        await connected_queue.process_retries()

        connected_queue.redis_client.zrangebyscore.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_retries_with_tasks(self, connected_queue):
        task1 = {
            "id": "webhook_process:123",
            "type": "webhook_process",
            "data": {"test": "data1"},
            "retry_count": 1,
        }
        task2 = {
            "id": "webhook_process:456",
            "type": "webhook_process",
            "data": {"test": "data2"},
            "retry_count": 2,
        }

        task1_json = json.dumps(task1)
        task2_json = json.dumps(task2)

        connected_queue.redis_client.zrangebyscore = AsyncMock(
            return_value=[task1_json, task2_json]
        )
        connected_queue.redis_client.zrem = AsyncMock()
        connected_queue.redis_client.zadd = AsyncMock()

        await connected_queue.process_retries()

        assert connected_queue.redis_client.zrem.call_count == 2
        assert connected_queue.redis_client.zadd.call_count == 2

    @pytest.mark.asyncio
    async def test_get_queue_stats_without_connection(self):
        q = TaskQueue()
        with patch("redis.asyncio.from_url", new_callable=AsyncMock) as mock_from_url:
            mock_from_url.side_effect = ConnectionError("Redis connection failed")
            with pytest.raises(
                RuntimeError, match="Redis client not connected and reconnection failed"
            ):
                await q.get_queue_stats()

    @pytest.mark.asyncio
    async def test_get_queue_stats_success(self, connected_queue):
        connected_queue.redis_client.zcard = AsyncMock(side_effect=[10, 5])
        connected_queue.redis_client.scard = AsyncMock(return_value=3)

        stats = await connected_queue.get_queue_stats()

        assert stats == {"pending": 10, "processing": 3, "retry": 5}


class TestWorkers:
    @pytest.mark.asyncio
    async def test_process_task_worker_processes_task(self):
        mock_task = {"id": "test:123", "type": "test_task", "data": {"key": "value"}}
        mock_db = AsyncMock()
        mock_processor = AsyncMock()
        mock_processor.process_task = AsyncMock()

        with (
            patch.object(task_queue, "dequeue") as mock_dequeue,
            patch.object(task_queue, "complete_task") as mock_complete,
            patch("src.webhooks.queue.get_session_maker") as mock_session_maker,
            patch("src.webhooks.queue.TaskProcessor") as mock_processor_class,
        ):
            call_count = 0

            async def dequeue_side_effect():
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    return mock_task
                return None

            mock_dequeue.side_effect = dequeue_side_effect
            mock_complete.return_value = None
            mock_session_maker.return_value.return_value.__aenter__.return_value = mock_db
            mock_session_maker.return_value.return_value.__aexit__.return_value = None
            mock_processor_class.return_value = mock_processor

            async def run_worker():
                await process_task_worker()

            task = asyncio.create_task(run_worker())
            await asyncio.sleep(0.2)
            task.cancel()

            try:
                await task
            except asyncio.CancelledError:
                pass

            mock_complete.assert_called_once_with(mock_task["id"])

    @pytest.mark.asyncio
    async def test_process_task_worker_handles_errors(self):
        mock_task = {"id": "test:123", "type": "test_task", "data": {"key": "value"}}
        mock_db = AsyncMock()
        mock_processor = AsyncMock()
        mock_processor.process_task = AsyncMock()

        with (
            patch.object(task_queue, "dequeue") as mock_dequeue,
            patch.object(task_queue, "complete_task") as mock_complete,
            patch.object(task_queue, "retry_task") as mock_retry,
            patch("src.webhooks.queue.get_session_maker") as mock_session_maker,
            patch("src.webhooks.queue.TaskProcessor") as mock_processor_class,
        ):
            call_count = 0

            async def dequeue_side_effect():
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    return mock_task
                return None

            mock_dequeue.side_effect = dequeue_side_effect
            mock_complete.side_effect = Exception("Processing error")
            mock_retry.return_value = None
            mock_session_maker.return_value.return_value.__aenter__.return_value = mock_db
            mock_session_maker.return_value.return_value.__aexit__.return_value = None
            mock_processor_class.return_value = mock_processor

            async def run_worker():
                await process_task_worker()

            task = asyncio.create_task(run_worker())
            await asyncio.sleep(0.2)
            task.cancel()

            try:
                await task
            except asyncio.CancelledError:
                pass

            mock_retry.assert_called_once()

    @pytest.mark.asyncio
    async def test_retry_processor_worker_processes_retries(self):
        with patch.object(task_queue, "process_retries") as mock_process:
            mock_process.return_value = None

            async def run_worker():
                await retry_processor_worker()

            task = asyncio.create_task(run_worker())
            await asyncio.sleep(0.1)
            task.cancel()

            try:
                await task
            except asyncio.CancelledError:
                pass

            assert mock_process.call_count >= 1

    @pytest.mark.asyncio
    async def test_retry_processor_worker_handles_errors(self):
        with patch.object(task_queue, "process_retries") as mock_process:
            mock_process.side_effect = Exception("Retry processing error")

            async def run_worker():
                await retry_processor_worker()

            task = asyncio.create_task(run_worker())
            await asyncio.sleep(0.1)
            task.cancel()

            try:
                await task
            except asyncio.CancelledError:
                pass

            assert mock_process.call_count >= 1
