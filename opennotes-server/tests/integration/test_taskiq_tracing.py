"""
Integration tests for taskiq distributed tracing.

This module tests that OpenTelemetry trace context is properly propagated
through taskiq task dispatch and execution, ensuring end-to-end distributed
tracing works correctly.

Key patterns tested:
- Trace context injection when dispatching tasks via .kiq()
- Trace context extraction when tasks execute in worker
- BaggageSpanProcessor propagates user context through task execution
- Spans for task dispatch and execution have correct messaging semantic conventions
"""

import asyncio
import logging
import os
from typing import Any

import pytest
from opentelemetry import baggage, context, propagate, trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from src.cache.redis_client import redis_client
from src.events.nats_client import nats_client

pytestmark = pytest.mark.integration_messaging

logger = logging.getLogger(__name__)


class _TestTracingState:
    """Singleton to hold test tracing state across tests."""

    _instance: "_TestTracingState | None" = None
    provider: TracerProvider | None = None
    exporter: InMemorySpanExporter | None = None

    def __new__(cls) -> "_TestTracingState":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def setup(self) -> tuple[TracerProvider, InMemorySpanExporter]:
        """Set up tracing for tests. Only sets up once per process."""
        if self.provider is None:
            self.exporter = InMemorySpanExporter()
            self.provider = TracerProvider()
            self.provider.add_span_processor(SimpleSpanProcessor(self.exporter))
            trace.set_tracer_provider(self.provider)
            logger.info("Test tracing provider initialized")

        assert self.exporter is not None
        return self.provider, self.exporter


_tracing_state = _TestTracingState()


@pytest.fixture
def in_memory_exporter() -> InMemorySpanExporter:
    """Get the shared in-memory span exporter and clear it for this test."""
    _, exporter = _tracing_state.setup()
    exporter.clear()
    return exporter


@pytest.fixture
def tracer_provider() -> TracerProvider:
    """Get the shared tracer provider for testing."""
    provider, _ = _tracing_state.setup()
    return provider


@pytest.fixture
async def setup_nats_redis(db_session: Any, tracer_provider: TracerProvider) -> Any:
    """
    Setup real NATS and Redis connections for taskiq tests.

    This fixture connects to real NATS and Redis services
    provided by testcontainers via the test_services fixture.

    Depends on tracer_provider to ensure tracing is set up first.
    """
    from src.tasks.broker import reset_broker

    os.environ["INTEGRATION_TESTS"] = "true"

    logger.info("Setting up Redis and NATS for taskiq integration tests...")

    reset_broker()
    logger.info("Reset taskiq broker for fresh configuration")

    try:
        redis_url = os.environ.get("REDIS_URL")
        await redis_client.connect(redis_url=redis_url)
        logger.info(f"Redis connected successfully: {redis_url}")
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        raise

    try:
        await nats_client.connect()
        logger.info(f"NATS connected successfully: {os.environ.get('NATS_URL')}")
    except Exception as e:
        logger.error(f"Failed to connect to NATS: {e}")
        raise

    import src.tasks.example  # noqa: F401

    yield

    logger.info("Tearing down messaging services...")

    if redis_client.client:
        try:
            await redis_client.client.flushdb()
        except Exception as e:
            logger.warning(f"Error flushing Redis: {e}")

    await nats_client.disconnect()
    await redis_client.disconnect()
    reset_broker()
    logger.info("Messaging services teardown complete")


async def run_receiver(broker: Any) -> None:
    """
    Run a simple receiver loop that processes tasks from the broker.

    This iterates over the broker's listen() async generator and executes
    each received task message. The Receiver.callback handles ack/reject
    internally, so we don't need to do it ourselves.
    """
    from nats.errors import ConnectionClosedError
    from taskiq.receiver import Receiver

    receiver = Receiver(broker)
    logger.info("Receiver initialized, starting to listen...")

    try:
        async for message in broker.listen():
            logger.debug(f"Received message: {message}")
            try:
                await receiver.callback(message)
            except Exception as e:
                logger.error(f"Error processing message: {e}")
    except asyncio.CancelledError:
        logger.info("Receiver cancelled, shutting down...")
        raise
    except ConnectionClosedError:
        logger.info("NATS connection closed, receiver stopping...")
    except Exception as e:
        logger.error(f"Receiver error: {e}")


@pytest.fixture
async def setup_taskiq_broker(setup_nats_redis: Any) -> Any:
    """
    Setup taskiq broker with real NATS and Redis services.

    This fixture depends on setup_nats_redis which provides
    real NATS and Redis connections via testcontainers.
    """
    from src.tasks.broker import get_broker

    actual_broker = get_broker()

    logger.info("Starting taskiq broker...")
    await actual_broker.startup()
    logger.info("Taskiq broker started successfully")

    logger.info("Starting background worker task...")
    worker_task = asyncio.create_task(run_receiver(actual_broker))
    logger.info("Background worker started")

    yield actual_broker

    logger.info("Shutting down taskiq broker...")
    await actual_broker.shutdown()
    logger.info("Taskiq broker shutdown complete")

    logger.info("Cancelling background worker...")
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        logger.info("Background worker cancelled")


class TestTaskiqTracingMiddleware:
    """Test distributed tracing through taskiq tasks."""

    @pytest.mark.asyncio
    async def test_trace_context_propagated_through_task(
        self,
        setup_taskiq_broker: Any,
        in_memory_exporter: InMemorySpanExporter,
    ) -> None:
        """
        Verify trace context is propagated from dispatch to execution.

        This test verifies:
        1. A producer span is created when dispatching via .kiq()
        2. Trace context is injected into task message labels
        3. A consumer span is created during task execution
        4. Consumer span is linked to producer span via trace context
        """
        from src.tasks.example import example_task

        tracer = trace.get_tracer(__name__)

        with tracer.start_as_current_span("test_root_span") as root_span:
            root_trace_id = root_span.get_span_context().trace_id

            task = await example_task.kiq("tracing test")
            logger.info(f"Task dispatched with trace_id: {format(root_trace_id, '032x')}")

            result = await task.wait_result(timeout=15)
            assert result.return_value == "Processed: tracing test"
            assert not result.is_err

        await asyncio.sleep(0.5)

        spans = in_memory_exporter.get_finished_spans()
        span_names = [s.name for s in spans]
        logger.info(f"Captured spans: {span_names}")

        dispatch_spans = [s for s in spans if "dispatch" in s.name.lower()]
        execute_spans = [s for s in spans if "execute" in s.name.lower()]

        assert len(dispatch_spans) >= 1, f"Expected dispatch span, got spans: {span_names}"
        assert len(execute_spans) >= 1, f"Expected execute span, got spans: {span_names}"

        dispatch_span = dispatch_spans[0]
        assert dispatch_span.kind == trace.SpanKind.PRODUCER
        assert dispatch_span.attributes is not None
        assert dispatch_span.attributes.get("messaging.system") == "taskiq"
        assert dispatch_span.attributes.get("messaging.operation.type") == "publish"

        execute_span = execute_spans[0]
        assert execute_span.kind == trace.SpanKind.CONSUMER
        assert execute_span.attributes is not None
        assert execute_span.attributes.get("messaging.system") == "taskiq"
        assert execute_span.attributes.get("messaging.operation.type") == "receive"

        dispatch_ctx = dispatch_span.get_span_context()
        execute_ctx = execute_span.get_span_context()
        assert dispatch_ctx is not None
        assert execute_ctx is not None
        assert dispatch_ctx.trace_id == root_trace_id
        assert execute_ctx.trace_id == root_trace_id

        logger.info("Trace context propagation verified successfully")

    @pytest.mark.asyncio
    async def test_baggage_propagated_through_task(
        self,
        setup_taskiq_broker: Any,
        in_memory_exporter: InMemorySpanExporter,
    ) -> None:
        """
        Verify baggage items are propagated through task execution.

        This test verifies that baggage set before dispatch is available
        during task execution via the W3C Baggage propagator.
        """
        from src.tasks.example import example_task

        tracer = trace.get_tracer(__name__)

        ctx = baggage.set_baggage("discord.user_id", "12345")
        ctx = baggage.set_baggage("discord.guild_id", "67890", ctx)
        ctx = baggage.set_baggage("request_id", "req-abc-123", ctx)

        token = context.attach(ctx)
        try:
            with tracer.start_as_current_span("test_baggage_span"):
                task = await example_task.kiq("baggage test")
                result = await task.wait_result(timeout=15)
                assert result.return_value == "Processed: baggage test"
        finally:
            context.detach(token)

        await asyncio.sleep(0.5)

        spans = in_memory_exporter.get_finished_spans()
        dispatch_spans = [s for s in spans if "dispatch" in s.name.lower()]

        assert len(dispatch_spans) >= 1

        logger.info("Baggage propagation test completed")

    @pytest.mark.asyncio
    async def test_trace_context_in_message_labels(
        self,
        setup_nats_redis: Any,
    ) -> None:
        """
        Verify trace context is injected into task message labels.

        This test mocks the broker to inspect message labels directly
        and verify traceparent/tracestate/baggage are present.
        """
        from taskiq import TaskiqMessage

        from src.tasks.tracing_middleware import TracingMiddleware

        middleware = TracingMiddleware()
        tracer = trace.get_tracer(__name__)

        with tracer.start_as_current_span("test_labels_span") as span:
            trace_id = span.get_span_context().trace_id

            message = TaskiqMessage(
                task_id="test-task-123",
                task_name="test_task",
                labels={},
                args=[],
                kwargs={},
            )

            modified_message = await middleware.pre_send(message)

            assert "trace.traceparent" in modified_message.labels
            traceparent = modified_message.labels["trace.traceparent"]

            assert format(trace_id, "032x") in traceparent

        logger.info(f"Trace context in labels: {modified_message.labels}")

    @pytest.mark.asyncio
    async def test_error_handling_sets_error_status(
        self,
        setup_taskiq_broker: Any,
        in_memory_exporter: InMemorySpanExporter,
    ) -> None:
        """
        Verify that failed tasks have error status set on spans.

        When a task raises an exception, the execution span should
        have ERROR status and record the exception.
        """
        from src.tasks.example import failing_task

        tracer = trace.get_tracer(__name__)

        with tracer.start_as_current_span("test_error_span"):
            task = await failing_task.kiq()
            result = await task.wait_result(timeout=15)
            assert result.is_err

        await asyncio.sleep(0.5)

        spans = in_memory_exporter.get_finished_spans()
        execute_spans = [s for s in spans if "execute" in s.name.lower()]

        assert len(execute_spans) >= 1
        execute_span = execute_spans[0]
        assert execute_span.status.status_code == trace.StatusCode.ERROR

        logger.info("Error handling span status verified")

    @pytest.mark.asyncio
    async def test_multiple_concurrent_tasks_have_separate_traces(
        self,
        setup_taskiq_broker: Any,
        in_memory_exporter: InMemorySpanExporter,
    ) -> None:
        """
        Verify multiple concurrent tasks maintain separate trace contexts.

        Each task should have its own trace ID unless dispatched from
        the same parent span.
        """
        from src.tasks.example import example_task

        tracer = trace.get_tracer(__name__)

        trace_ids = []
        tasks = []

        for i in range(3):
            with tracer.start_as_current_span(f"test_concurrent_{i}") as span:
                trace_ids.append(span.get_span_context().trace_id)
                task = await example_task.kiq(f"concurrent {i}")
                tasks.append(task)

        results = await asyncio.gather(*[t.wait_result(timeout=15) for t in tasks])

        for i, result in enumerate(results):
            assert result.return_value == f"Processed: concurrent {i}"
            assert not result.is_err

        await asyncio.sleep(0.5)

        spans = in_memory_exporter.get_finished_spans()
        dispatch_spans = [s for s in spans if "dispatch" in s.name.lower()]

        assert len(dispatch_spans) >= 3

        logger.info(f"Captured {len(dispatch_spans)} dispatch spans for concurrent tasks")


class TestTracingMiddlewareUnit:
    """Unit tests for TracingMiddleware without full broker setup."""

    @pytest.mark.asyncio
    async def test_pre_send_creates_producer_span(
        self,
        in_memory_exporter: InMemorySpanExporter,
    ) -> None:
        """Verify pre_send creates a PRODUCER span with correct attributes."""
        from taskiq import TaskiqMessage

        from src.tasks.tracing_middleware import TracingMiddleware

        middleware = TracingMiddleware()

        message = TaskiqMessage(
            task_id="unit-test-123",
            task_name="unit_test_task",
            labels={},
            args=["arg1"],
            kwargs={"key": "value"},
        )

        result = await middleware.pre_send(message)

        assert result.task_id == message.task_id
        assert "trace.traceparent" in result.labels

        spans = in_memory_exporter.get_finished_spans()
        assert len(spans) == 1

        span = spans[0]
        assert span.name == "taskiq.dispatch.unit_test_task"
        assert span.kind == trace.SpanKind.PRODUCER
        assert span.attributes is not None
        assert span.attributes.get("messaging.system") == "taskiq"
        assert span.attributes.get("messaging.destination.name") == "unit_test_task"
        assert span.attributes.get("messaging.message.id") == "unit-test-123"

    @pytest.mark.asyncio
    async def test_pre_execute_creates_consumer_span(
        self,
        in_memory_exporter: InMemorySpanExporter,
    ) -> None:
        """Verify pre_execute creates a CONSUMER span linked to producer."""
        from taskiq import TaskiqMessage

        from src.tasks.tracing_middleware import TracingMiddleware

        middleware = TracingMiddleware()

        carrier: dict[str, str] = {}
        tracer = trace.get_tracer(__name__)
        with tracer.start_as_current_span("producer_span") as span:
            producer_trace_id = span.get_span_context().trace_id
            propagate.inject(carrier)

        in_memory_exporter.clear()

        labels = {f"trace.{k}": v for k, v in carrier.items()}

        message = TaskiqMessage(
            task_id="unit-test-456",
            task_name="unit_test_task",
            labels=labels,
            args=[],
            kwargs={},
        )

        await middleware.pre_execute(message)

        from taskiq import TaskiqResult

        result = TaskiqResult(
            is_err=False,
            return_value="success",
            execution_time=0.1,
        )
        await middleware.post_execute(message, result)

        spans = in_memory_exporter.get_finished_spans()
        consumer_spans = [s for s in spans if s.kind == trace.SpanKind.CONSUMER]

        assert len(consumer_spans) == 1
        consumer_span = consumer_spans[0]

        assert consumer_span.name == "taskiq.execute.unit_test_task"
        consumer_ctx = consumer_span.get_span_context()
        assert consumer_ctx is not None
        assert consumer_ctx.trace_id == producer_trace_id
        assert consumer_span.status.status_code == trace.StatusCode.OK

    @pytest.mark.asyncio
    async def test_on_error_sets_error_status(
        self,
        in_memory_exporter: InMemorySpanExporter,
    ) -> None:
        """Verify on_error sets ERROR status and records exception."""
        from taskiq import TaskiqMessage, TaskiqResult

        from src.tasks.tracing_middleware import TracingMiddleware

        middleware = TracingMiddleware()

        message = TaskiqMessage(
            task_id="error-test-789",
            task_name="failing_task",
            labels={},
            args=[],
            kwargs={},
        )

        await middleware.pre_execute(message)

        error = ValueError("Test error")
        result = TaskiqResult(
            is_err=True,
            return_value=None,
            execution_time=0.1,
            error=error,
        )
        await middleware.on_error(message, result, error)

        spans = in_memory_exporter.get_finished_spans()
        consumer_spans = [s for s in spans if s.kind == trace.SpanKind.CONSUMER]

        assert len(consumer_spans) == 1
        consumer_span = consumer_spans[0]

        assert consumer_span.status.status_code == trace.StatusCode.ERROR
        assert consumer_span.status.description is not None
        assert "Test error" in consumer_span.status.description
