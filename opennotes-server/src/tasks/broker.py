"""
Taskiq broker configuration with NATS JetStream and Redis result backend.

This module configures the taskiq broker for distributed task processing using:
- PullBasedJetStreamBroker: Pull-based NATS JetStream broker for reliable message delivery
- RedisAsyncResultBackend: Redis for storing task results

The broker is lazily initialized to support dynamic configuration in tests.

Usage:
    from src.tasks.broker import broker, register_task

    @register_task()
    async def my_task(arg: str) -> str:
        return f"Processed: {arg}"

    await broker.startup()
    task = await my_task.kiq("test")
    result = await task.wait_result(timeout=10)
    await broker.shutdown()
"""

import logging
from collections.abc import Callable
from typing import Any, TypeVar

import taskiq_fastapi
from taskiq_nats import PullBasedJetStreamBroker
from taskiq_redis import RedisAsyncResultBackend

from src.config import get_settings

logger = logging.getLogger(__name__)

T = TypeVar("T")

_broker_instance: PullBasedJetStreamBroker | None = None
_all_registered_tasks: dict[str, Callable[..., Any]] = {}
_registered_task_objects: dict[str, Any] = {}


def _create_broker() -> PullBasedJetStreamBroker:
    """Create and configure the taskiq broker with current settings."""
    settings = get_settings()

    logger.info(
        f"Creating taskiq broker with NATS: {settings.NATS_URL}, Redis: {settings.REDIS_URL}"
    )

    result_backend = RedisAsyncResultBackend(
        redis_url=settings.REDIS_URL,
        result_ex_time=3600,
    )

    new_broker = PullBasedJetStreamBroker(
        servers=[settings.NATS_URL],
        stream_name="OPENNOTES_TASKS",
        durable="opennotes-taskiq-worker",
    ).with_result_backend(result_backend)

    taskiq_fastapi.init(new_broker, "src.main:app")

    return new_broker


def get_broker() -> PullBasedJetStreamBroker:
    """Get or create the singleton broker instance."""
    global _broker_instance  # noqa: PLW0603
    if _broker_instance is None:
        _broker_instance = _create_broker()
        _register_all_tasks(_broker_instance)
    return _broker_instance


def _register_all_tasks(broker_instance: PullBasedJetStreamBroker) -> None:
    """Register all tasks with the broker instance and store task objects."""
    _registered_task_objects.clear()
    for task_name, func in _all_registered_tasks.items():
        logger.debug(f"Registering task: {task_name}")
        task_obj = broker_instance.register_task(func, task_name=task_name)
        _registered_task_objects[task_name] = task_obj


def reset_broker() -> None:
    """
    Reset the broker instance (for testing).

    This clears the current broker instance so a new one will be created
    with updated settings. All registered tasks will be re-registered
    with the new broker when get_broker() is called.
    """
    global _broker_instance  # noqa: PLW0603
    _broker_instance = None
    _registered_task_objects.clear()


class LazyTask:
    """
    A lazy task wrapper that forwards to the registered taskiq task.

    This wrapper allows tasks to be decorated at import time before the
    broker is created. When methods like .kiq() are called, it looks up
    the actual task from the broker.
    """

    def __init__(self, func: Callable[..., Any], task_name: str) -> None:
        self._func = func
        self._task_name = task_name
        self.__name__ = func.__name__
        self.__doc__ = func.__doc__

    def _get_registered_task(self) -> Any:
        """Get the actual registered task from the broker."""
        get_broker()
        if self._task_name in _registered_task_objects:
            return _registered_task_objects[self._task_name]
        raise RuntimeError(
            f"Task '{self._task_name}' not found in broker. "
            "Make sure the broker has been started and tasks are registered."
        )

    async def kiq(self, *args: Any, **kwargs: Any) -> Any:
        """Dispatch the task asynchronously."""
        task = self._get_registered_task()
        return await task.kiq(*args, **kwargs)

    def kicker(self, *args: Any, **kwargs: Any) -> Any:
        """Get a kicker for this task."""
        task = self._get_registered_task()
        return task.kicker(*args, **kwargs)

    async def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Call the task function directly (for local execution)."""
        return await self._func(*args, **kwargs)

    def __repr__(self) -> str:
        return f"<LazyTask {self._task_name}>"


def register_task(task_name: str | None = None) -> Callable[[Callable[..., T]], LazyTask]:
    """
    Decorator to register a task with the broker.

    This decorator handles lazy broker initialization - if the broker
    doesn't exist yet, the task is queued for registration when the
    broker is created.

    Returns a LazyTask wrapper that provides .kiq() method for
    task dispatch.

    Usage:
        @register_task()
        async def my_task(arg: str) -> str:
            return f"Processed: {arg}"

        # Or with custom name:
        @register_task(task_name="custom_name")
        async def my_task(arg: str) -> str:
            return f"Processed: {arg}"
    """

    def decorator(func: Callable[..., T]) -> LazyTask:
        name = task_name or f"{func.__module__}:{func.__name__}"

        _all_registered_tasks[name] = func

        if _broker_instance is not None:
            task_obj = _broker_instance.register_task(func, task_name=name)
            _registered_task_objects[name] = task_obj

        return LazyTask(func, name)

    return decorator


class _BrokerProxy:
    """
    Proxy object that lazily initializes the broker on first access.

    This allows the broker module to be imported before settings are configured
    (e.g., in tests where testcontainers set URLs dynamically).
    """

    def __getattr__(self, name: str) -> Any:
        return getattr(get_broker(), name)

    def __repr__(self) -> str:
        return f"<BrokerProxy wrapping {get_broker()!r}>"


# Export a proxy that lazily creates the broker
broker = _BrokerProxy()

__all__ = [
    "LazyTask",
    "PullBasedJetStreamBroker",
    "broker",
    "get_broker",
    "register_task",
    "reset_broker",
]
