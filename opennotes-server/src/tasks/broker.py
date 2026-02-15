"""
Taskiq broker configuration with NATS JetStream and Redis result backend.

This module configures the taskiq broker for distributed task processing using:
- PullBasedJetStreamBroker: Pull-based NATS JetStream broker for reliable message delivery
- RedisAsyncResultBackend: Redis for storing task results
- RetryWithFinalCallbackMiddleware: Automatic retry for failed tasks with callback on final failure
- SafeOpenTelemetryMiddleware: Distributed tracing with W3C Trace Context propagation
  (wraps OpenTelemetryMiddleware with safe context detach for async tasks)
- TaskIQMetricsMiddleware: Prometheus metrics for task execution duration

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

import functools
import logging
from collections.abc import Callable
from typing import Any, TypeVar

import redis.asyncio as aioredis
from nats.js.api import StreamConfig
from nats.js.errors import BadRequestError
from opentelemetry import context as context_api
from taskiq import AsyncBroker, TaskiqMessage, TaskiqResult
from taskiq.middlewares.opentelemetry_middleware import (
    OpenTelemetryMiddleware,
    detach_context,
    retrieve_context,
)
from taskiq_nats import PullBasedJetStreamBroker
from taskiq_redis import RedisAsyncResultBackend

from src.cache.redis_client import create_redis_connection, get_redis_connection_kwargs
from src.config import get_settings
from src.tasks.metrics_middleware import TaskIQMetricsMiddleware
from src.tasks.middleware import RetryCallbackHandlerRegistry, RetryWithFinalCallbackMiddleware
from src.tasks.rate_limit_middleware import DistributedRateLimitMiddleware

logger = logging.getLogger(__name__)

T = TypeVar("T")
R = TypeVar("R")


class SafeOpenTelemetryMiddleware(OpenTelemetryMiddleware):
    """
    OpenTelemetry middleware with safe context detach for async tasks.

    This middleware wraps the standard OpenTelemetryMiddleware to handle the
    "Token was created in a different Context" ValueError that occurs when
    async tasks run concurrently.

    The issue occurs because:
    1. OpenTelemetry context uses Python's contextvars
    2. In async execution, context tokens can be created in one coroutine context
    3. When detach() is called in a different coroutine context, it fails

    This wrapper catches the ValueError during context detach and logs it as a
    warning instead of letting it propagate. The span tracking itself is unaffected
    since the span has already been ended before detach is called.

    See: https://github.com/google/adk-python/issues/860
    """

    def post_save(
        self,
        message: TaskiqMessage,
        result: TaskiqResult[R],  # noqa: ARG002 (required by parent interface)
    ) -> None:
        """
        Close span from pre_execute with safe context detach.

        This overrides the parent method to catch ValueError during context
        detach, which can occur when async tasks run in different coroutine
        contexts than where the context was attached.
        """
        ctx = retrieve_context(message)

        if ctx is None:
            logger.warning("no existing span found for task_id=%s", message.task_id)
            return

        span, activation, token = ctx

        if span.is_recording():
            span.set_attribute("taskiq.action", "execute")
            span.set_attribute("taskiq.task_name", message.task_name)

        activation.__exit__(None, None, None)
        detach_context(message)

        if token is not None:
            try:
                context_api.detach(token)  # pyright: ignore[reportArgumentType]
            except ValueError as e:
                if "was created in a different Context" in str(e):
                    logger.debug(
                        "Context token detach skipped (async context mismatch) for task_id=%s: %s",
                        message.task_id,
                        e,
                    )
                else:
                    raise


class ResilientJetStreamBroker(PullBasedJetStreamBroker):
    async def startup(self) -> None:
        await AsyncBroker.startup(self)
        await self.client.connect(self.servers, **self.connection_kwargs)
        self.js = self.client.jetstream()
        if self.stream_config.name is None:
            self.stream_config.name = self.stream_name
        if not self.stream_config.subjects:
            self.stream_config.subjects = [self.subject]
        try:
            await self.js.add_stream(config=self.stream_config)
        except BadRequestError as exc:
            if exc.err_code == 10058:
                logger.warning(
                    "Stream %s already exists with different config (err_code=10058), updating",
                    self.stream_config.name,
                )
                await self.js.update_stream(config=self.stream_config)
            else:
                raise
        await self._startup_consumer()


_broker_instance: PullBasedJetStreamBroker | None = None
_all_registered_tasks: dict[str, tuple[Callable[..., Any], dict[str, Any]]] = {}
_registered_task_objects: dict[str, Any] = {}

# Global registry for task-specific final-retry error handlers
retry_callback_registry = RetryCallbackHandlerRegistry()


RATE_LIMITER_SOCKET_TIMEOUT = 120
"""Socket timeout (seconds) for rate limiter's dedicated Redis client.

The rate limiter uses the `limiters` library's AsyncSemaphore which internally
uses BLPOP (a blocking Redis command) with max_sleep=30s by default. The standard
Redis client uses REDIS_SOCKET_TIMEOUT=5s, which causes TimeoutError when BLPOP
blocks waiting for a semaphore permit.

This dedicated client uses a higher timeout (120s) to allow blocking commands to
complete. The value should exceed the maximum expected wait time for semaphore
acquisition (rate_limit_max_sleep defaults to 30s, but can be configured higher).

See TASK-1032 for full root cause analysis.
"""


def _create_broker() -> PullBasedJetStreamBroker:
    """Create and configure the taskiq broker with current settings."""
    settings = get_settings()

    logger.info(
        f"Creating taskiq broker with NATS cluster: {settings.NATS_SERVERS}, Redis: {settings.REDIS_URL}"
    )
    logger.info(
        f"Taskiq config: stream={settings.TASKIQ_STREAM_NAME}, "
        f"result_expiry={settings.TASKIQ_RESULT_EXPIRY}s, "
        f"retry_count={settings.TASKIQ_DEFAULT_RETRY_COUNT}"
    )

    redis_kwargs = get_redis_connection_kwargs(settings.REDIS_URL)
    ssl_ca_certs = redis_kwargs.get("ssl_ca_certs")

    result_backend_kwargs: dict[str, Any] = {
        "redis_url": settings.REDIS_URL,
        "result_ex_time": settings.TASKIQ_RESULT_EXPIRY,
    }
    if ssl_ca_certs is not None:
        result_backend_kwargs["ssl_ca_certs"] = ssl_ca_certs
        result_backend_kwargs["ssl_cert_reqs"] = redis_kwargs.get("ssl_cert_reqs", "required")
        logger.info("TaskIQ Redis result backend configured with SSL CA cert")

    result_backend: RedisAsyncResultBackend[Any] = RedisAsyncResultBackend(**result_backend_kwargs)

    rate_limiter_redis_kwargs = get_redis_connection_kwargs(
        settings.REDIS_URL,
        socket_timeout=RATE_LIMITER_SOCKET_TIMEOUT,
    )
    rate_limiter_redis_client = aioredis.Redis.from_url(
        settings.REDIS_URL, **rate_limiter_redis_kwargs
    )
    if rate_limiter_redis_kwargs.get("ssl_ca_certs") is not None:
        logger.info("Rate limiter Redis client configured with SSL CA cert")
    logger.info(
        f"Rate limiter Redis client configured with socket_timeout={RATE_LIMITER_SOCKET_TIMEOUT}s "
        f"(allows BLPOP blocking commands to complete)"
    )

    retry_middleware = RetryWithFinalCallbackMiddleware(
        default_retry_count=settings.TASKIQ_DEFAULT_RETRY_COUNT,
        on_error_last_retry=retry_callback_registry.dispatch,
    )

    tracing_middleware = SafeOpenTelemetryMiddleware()

    metrics_middleware = TaskIQMetricsMiddleware(
        instance_id=settings.INSTANCE_ID,
    )

    rate_limit_middleware = DistributedRateLimitMiddleware(
        redis_client=rate_limiter_redis_client,
        instance_id=settings.INSTANCE_ID,
    )

    connection_kwargs: dict[str, Any] = {
        "connect_timeout": settings.NATS_CONNECT_TIMEOUT,
    }
    if settings.NATS_USERNAME and settings.NATS_PASSWORD:
        connection_kwargs["user"] = settings.NATS_USERNAME
        connection_kwargs["password"] = settings.NATS_PASSWORD
        logger.info("Taskiq broker configured with NATS authentication")

    stream_config = StreamConfig(
        name=settings.TASKIQ_STREAM_NAME,
        max_age=settings.TASKIQ_STREAM_MAX_AGE_SECONDS,
    )
    logger.info(
        f"Taskiq stream configured with max_age={settings.TASKIQ_STREAM_MAX_AGE_SECONDS}s "
        f"({settings.TASKIQ_STREAM_MAX_AGE_SECONDS // 86400} days)"
    )

    new_broker = (
        ResilientJetStreamBroker(
            servers=settings.NATS_SERVERS,
            stream_name=settings.TASKIQ_STREAM_NAME,
            stream_config=stream_config,
            durable="opennotes-taskiq-worker",
            **connection_kwargs,
        )
        .with_result_backend(result_backend)
        .with_middlewares(
            tracing_middleware, rate_limit_middleware, metrics_middleware, retry_middleware
        )
    )

    logger.info(
        "Taskiq broker configured with middlewares: "
        "tracing, rate_limit, metrics, retry (in execution order)"
    )

    return new_broker


def get_broker() -> PullBasedJetStreamBroker:
    """Get or create the singleton broker instance."""
    global _broker_instance  # noqa: PLW0603
    if _broker_instance is None:
        from src.config import get_settings
        from src.monitoring.logging import parse_log_level_overrides, setup_logging
        from src.monitoring.otel import get_span_exporter, setup_otel
        from src.monitoring.traceloop import setup_traceloop

        settings = get_settings()
        setup_logging(
            log_level=settings.LOG_LEVEL,
            json_format=True,
            service_name="opennotes-taskiq-worker",
            module_levels=parse_log_level_overrides(settings.LOG_LEVEL_OVERRIDES),
        )

        if settings.ENABLE_TRACING:
            setup_otel(
                service_name="opennotes-taskiq-worker",
                service_version=settings.VERSION,
                environment=settings.ENVIRONMENT,
                otlp_endpoint=settings.OTLP_ENDPOINT,
                otlp_headers=settings.OTLP_HEADERS,
                otlp_insecure=settings.OTLP_INSECURE,
                sample_rate=settings.TRACING_SAMPLE_RATE,
                use_gcp_exporters=settings.USE_GCP_EXPORTERS,
            )

        if settings.TRACELOOP_ENABLED:
            setup_traceloop(
                app_name=settings.PROJECT_NAME,
                service_name="opennotes-taskiq-worker",
                version=settings.VERSION,
                environment=settings.ENVIRONMENT,
                instance_id=settings.INSTANCE_ID,
                otlp_endpoint=settings.OTLP_ENDPOINT,
                otlp_headers=settings.OTLP_HEADERS,
                trace_content=settings.TRACELOOP_TRACE_CONTENT,
                exporter=get_span_exporter(),
            )

        _broker_instance = _create_broker()
        _register_all_tasks(_broker_instance)
    return _broker_instance


def _register_all_tasks(broker_instance: PullBasedJetStreamBroker) -> None:
    """Register all tasks with the broker instance and store task objects."""
    _registered_task_objects.clear()
    for task_name, task_data in _all_registered_tasks.items():
        func, labels = task_data
        logger.debug(f"Registering task: {task_name} with labels: {labels}")
        task_obj = broker_instance.register_task(func, task_name=task_name, **labels)
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

    Uses functools.update_wrapper to preserve the original function's
    metadata (__name__, __doc__, __annotations__, __module__, etc.).
    """

    __name__: str
    __doc__: str | None
    __annotations__: dict[str, Any]
    __module__: str
    __qualname__: str
    __wrapped__: Callable[..., Any]

    def __init__(self, func: Callable[..., Any], task_name: str) -> None:
        self._func = func
        self._task_name = task_name
        self.__name__ = func.__name__
        self.__wrapped__ = func
        functools.update_wrapper(self, func)

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


def register_task(
    task_name: str | None = None, **labels: Any
) -> Callable[[Callable[..., T]], LazyTask]:
    """
    Decorator to register a task with the broker.

    This decorator handles lazy broker initialization - if the broker
    doesn't exist yet, the task is queued for registration when the
    broker is created.

    Returns a LazyTask wrapper that provides .kiq() method for
    task dispatch.

    Args:
        task_name: Optional custom task name. Defaults to module:function_name.
        **labels: Optional labels for the task (e.g., component="rechunk", task_type="batch").
            Labels are passed to the broker and can be used for routing, filtering,
            and observability in dashboards and traces.

    Usage:
        @register_task()
        async def my_task(arg: str) -> str:
            return f"Processed: {arg}"

        # Or with custom name:
        @register_task(task_name="custom_name")
        async def my_task(arg: str) -> str:
            return f"Processed: {arg}"

        # Or with labels for observability:
        @register_task(task_name="rechunk:fact_check", component="rechunk", task_type="batch")
        async def process_rechunk(arg: str) -> str:
            return f"Processed: {arg}"
    """

    def decorator(func: Callable[..., T]) -> LazyTask:
        name = task_name or f"{func.__module__}:{func.__name__}"

        _all_registered_tasks[name] = (func, labels)

        if _broker_instance is not None:
            task_obj = _broker_instance.register_task(func, task_name=name, **labels)
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


def is_broker_initialized() -> bool:
    """
    Check if the broker has been initialized.

    Returns True if the broker instance has been created, False otherwise.
    This is useful for health checks to verify the broker is ready.
    """
    return _broker_instance is not None


def get_broker_health() -> dict[str, Any]:
    """
    Get health status of the taskiq broker.

    Returns a dict with:
    - initialized: Whether the broker instance exists
    - stream_name: The configured NATS stream name
    - registered_tasks: Number of registered tasks

    This is used by the /health/taskiq endpoint.
    """
    settings = get_settings()

    if _broker_instance is None:
        return {
            "initialized": False,
            "stream_name": settings.TASKIQ_STREAM_NAME,
            "registered_tasks": 0,
        }

    return {
        "initialized": True,
        "stream_name": settings.TASKIQ_STREAM_NAME,
        "registered_tasks": len(_registered_task_objects),
    }


def get_registered_tasks() -> dict[str, tuple[Callable[..., Any], dict[str, Any]]]:
    """
    Get all registered tasks with their labels.

    Returns a dict mapping task names to (function, labels) tuples.
    This is useful for testing task registration and inspecting labels.

    Example:
        tasks = get_registered_tasks()
        if "my:task" in tasks:
            func, labels = tasks["my:task"]
            assert labels.get("component") == "my_component"
    """
    return dict(_all_registered_tasks)


async def check_redis_ssl_connectivity() -> dict[str, Any]:
    """
    Check Redis SSL connectivity for TaskIQ result backend.

    This health check verifies that the Redis connection can be established
    with proper SSL configuration. It's useful for validating TLS connectivity
    at worker startup.

    Returns a dict with:
    - healthy: Whether connection succeeded
    - ssl_enabled: Whether SSL is configured (rediss:// URL)
    - ssl_cert_reqs: The ssl_cert_reqs setting if SSL is enabled
    - error: Error message if connection failed (only present on failure)
    """
    settings = get_settings()
    redis_url = settings.REDIS_URL
    ssl_enabled = redis_url.startswith("rediss://")

    result: dict[str, Any] = {
        "healthy": False,
        "ssl_enabled": ssl_enabled,
    }

    if ssl_enabled:
        redis_kwargs = get_redis_connection_kwargs(redis_url)
        result["ssl_cert_reqs"] = redis_kwargs.get("ssl_cert_reqs")

    try:
        client = await create_redis_connection(redis_url)
        try:
            await client.ping()
            result["healthy"] = True
            logger.info(
                "Redis SSL connectivity check passed (ssl_enabled=%s, ssl_cert_reqs=%s)",
                ssl_enabled,
                result.get("ssl_cert_reqs"),
            )
        finally:
            await client.aclose()
    except aioredis.RedisError as e:
        result["error"] = str(e)
        logger.error("Redis SSL connectivity check failed: %s", e)
    except Exception as e:
        result["error"] = str(e)
        logger.error("Redis SSL connectivity check failed with unexpected error: %s", e)

    return result


# Export a proxy that lazily creates the broker
broker = _BrokerProxy()

__all__ = [
    "LazyTask",
    "PullBasedJetStreamBroker",
    "ResilientJetStreamBroker",
    "SafeOpenTelemetryMiddleware",
    "broker",
    "check_redis_ssl_connectivity",
    "get_broker",
    "get_broker_health",
    "get_registered_tasks",
    "is_broker_initialized",
    "register_task",
    "reset_broker",
    "retry_callback_registry",
]
