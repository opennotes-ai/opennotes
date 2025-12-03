import asyncio
import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

import redis.asyncio as redis

from src.cache.redis_client import create_redis_connection
from src.config import settings
from src.database import get_session_maker
from src.webhooks.processor import TaskProcessor
from src.webhooks.types import QueueTaskData

logger = logging.getLogger(__name__)


class TaskQueue:
    def __init__(self) -> None:
        self.redis_client: redis.Redis | None = None
        self.queue_name = "webhook:tasks"
        self.processing_set = "webhook:processing"
        self.retry_set = "webhook:retry"
        self._max_retries = 3
        self._retry_delay = 1.0

    async def connect(self) -> None:
        self.redis_client = await create_redis_connection(decode_responses=True)
        logger.info("Connected to Redis for task queue")

    async def disconnect(self) -> None:
        if self.redis_client:
            await self.redis_client.close()
            self.redis_client = None
            logger.info("Disconnected from Redis")

    async def __aenter__(self) -> "TaskQueue":
        await self.connect()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.disconnect()

    async def is_connected(self) -> bool:
        if not self.redis_client:
            return False
        try:
            await self.redis_client.ping()
            return True
        except Exception as e:
            logger.error(f"Redis ping failed in is_connected: {e}")
            return False

    async def ping(self) -> bool:
        if not self.redis_client:
            return False
        try:
            await self.redis_client.ping()
            return True
        except Exception as e:
            logger.warning(f"Redis ping failed: {e}")
            return False

    async def _ensure_connected(self) -> None:
        if await self.is_connected():
            return

        for attempt in range(self._max_retries):
            try:
                logger.info(
                    f"Attempting to reconnect to Redis (attempt {attempt + 1}/{self._max_retries})"
                )
                await self.connect()
                if await self.is_connected():
                    logger.info("Successfully reconnected to Redis")
                    return
            except Exception as e:
                logger.warning(f"Reconnection attempt {attempt + 1} failed: {e}")
                if attempt < self._max_retries - 1:
                    delay = self._retry_delay * (2**attempt)
                    await asyncio.sleep(delay)

        raise RuntimeError("Redis client not connected and reconnection failed")

    async def enqueue(
        self,
        task_type: str,
        task_data: dict[str, Any],
        priority: int = 0,
    ) -> str:
        await self._ensure_connected()
        assert self.redis_client is not None, "Redis client should be connected"

        task_id = f"{task_type}:{uuid.uuid4()}"
        task = {
            "id": task_id,
            "type": task_type,
            "data": task_data,
            "retry_count": 0,
            "created_at": datetime.now(UTC).isoformat(),
        }

        await self.redis_client.zadd(
            self.queue_name,
            {json.dumps(task): priority},
        )
        logger.info(f"Enqueued task {task_id} with priority {priority}")
        return task_id

    async def dequeue(self) -> QueueTaskData | None:
        await self._ensure_connected()
        assert self.redis_client is not None, "Redis client should be connected"

        result = await self.redis_client.zpopmin(self.queue_name, count=1)
        if not result:
            return None

        task_json, _ = result[0]
        task: QueueTaskData = json.loads(task_json)

        await self.redis_client.sadd(self.processing_set, task["id"])  # type: ignore[misc]
        return task

    async def complete_task(self, task_id: str) -> None:
        await self._ensure_connected()
        assert self.redis_client is not None, "Redis client should be connected"

        await self.redis_client.srem(self.processing_set, task_id)  # type: ignore[misc]
        logger.info(f"Completed task {task_id}")

    async def retry_task(
        self,
        task: dict[str, Any],
        error: str,
    ) -> bool:
        await self._ensure_connected()
        assert self.redis_client is not None, "Redis client should be connected"

        task["retry_count"] += 1
        task["last_error"] = error
        task["last_retry"] = datetime.now(UTC).isoformat()

        if task["retry_count"] > settings.QUEUE_MAX_RETRIES:
            logger.error(f"Task {task['id']} exceeded max retries, dropping")
            await self.redis_client.srem(self.processing_set, task["id"])  # type: ignore[misc]
            return False

        delay = settings.QUEUE_RETRY_DELAY * (
            settings.QUEUE_RETRY_BACKOFF ** (task["retry_count"] - 1)
        )
        retry_time = datetime.now(UTC).timestamp() + delay

        await self.redis_client.zadd(
            self.retry_set,
            {json.dumps(task): retry_time},
        )
        await self.redis_client.srem(self.processing_set, task["id"])  # type: ignore[misc]

        logger.info(f"Task {task['id']} scheduled for retry {task['retry_count']} in {delay}s")
        return True

    async def process_retries(self) -> None:
        await self._ensure_connected()
        assert self.redis_client is not None, "Redis client should be connected"

        now = datetime.now(UTC).timestamp()
        results = await self.redis_client.zrangebyscore(
            self.retry_set,
            min=0,
            max=now,
            withscores=False,
        )

        for task_json in results:
            task = json.loads(task_json)
            await self.redis_client.zrem(self.retry_set, task_json)
            await self.redis_client.zadd(
                self.queue_name,
                {task_json: 0},
            )
            logger.info(f"Moved task {task['id']} from retry to main queue")

    async def get_queue_stats(self) -> dict[str, int]:
        await self._ensure_connected()
        assert self.redis_client is not None, "Redis client should be connected"

        return {
            "pending": await self.redis_client.zcard(self.queue_name),
            "processing": await self.redis_client.scard(self.processing_set),  # type: ignore[misc]
            "retry": await self.redis_client.zcard(self.retry_set),
        }


task_queue = TaskQueue()

shutdown_event = asyncio.Event()


def request_shutdown() -> None:
    """Signal all workers to gracefully shut down."""
    shutdown_event.set()
    logger.info("Shutdown requested for webhook workers")


async def process_task_worker() -> None:
    logger.info("Task worker started")

    try:
        while not shutdown_event.is_set():
            task = None
            try:
                task = await task_queue.dequeue()
                if not task:
                    await asyncio.sleep(0.1)
                    continue

                if shutdown_event.is_set():
                    logger.info("Shutdown requested, re-queuing task")
                    await task_queue.enqueue(
                        task_type=task["type"],
                        task_data=task["data"],
                        priority=0,
                    )
                    break

                logger.info(f"Processing task {task['id']} of type {task['type']}")

                async with get_session_maker()() as db:
                    processor = TaskProcessor(db)
                    await processor.process_task(task)

                await task_queue.complete_task(task["id"])

            except asyncio.CancelledError:
                logger.info("Task worker cancelled")
                if task:
                    await task_queue.enqueue(
                        task_type=task["type"],
                        task_data=task["data"],
                        priority=0,
                    )
                raise
            except Exception as e:
                logger.exception(f"Error processing task: {e}")
                if task:
                    await task_queue.retry_task(dict(task), str(e))

            await asyncio.sleep(0.01)
    finally:
        logger.info("Task worker stopped")


async def retry_processor_worker() -> None:
    logger.info("Retry processor worker started")

    try:
        while not shutdown_event.is_set():
            try:
                await task_queue.process_retries()
            except asyncio.CancelledError:
                logger.info("Retry processor worker cancelled")
                raise
            except Exception as e:
                logger.exception(f"Error processing retries: {e}")

            await asyncio.sleep(1)
    finally:
        logger.info("Retry processor worker stopped")
