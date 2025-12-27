"""
Taskiq broker configuration with NATS JetStream and Redis result backend.

This module configures the taskiq broker for distributed task processing using:
- PullBasedJetStreamBroker: Pull-based NATS JetStream broker for reliable message delivery
- RedisAsyncResultBackend: Redis for storing task results

Usage:
    from src.tasks.broker import broker

    await broker.startup()
    # ... dispatch and execute tasks ...
    await broker.shutdown()
"""

import taskiq_fastapi
from taskiq_nats import PullBasedJetStreamBroker
from taskiq_redis import RedisAsyncResultBackend

from src.config import settings

result_backend = RedisAsyncResultBackend(
    redis_url=settings.REDIS_URL,
    result_ex_time=3600,
)

broker = PullBasedJetStreamBroker(
    servers=[settings.NATS_URL],
    stream_name="OPENNOTES_TASKS",
    durable="opennotes-taskiq-worker",
).with_result_backend(result_backend)

taskiq_fastapi.init(broker, "src.main:app")
