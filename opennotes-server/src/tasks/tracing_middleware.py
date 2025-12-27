"""
OpenTelemetry tracing middleware for taskiq.

This middleware provides distributed tracing for taskiq tasks by:
- Injecting W3C Trace Context and Baggage into task message labels on dispatch
- Extracting trace context when tasks execute in workers
- Creating producer spans for task dispatch and consumer spans for task execution

The middleware follows the same patterns as NATS event tracing (publisher.py/subscriber.py)
and works with the BaggageSpanProcessor to propagate user context through task execution.
"""

import logging
from typing import Any

from opentelemetry import context, propagate, trace
from taskiq import TaskiqMessage, TaskiqMiddleware, TaskiqResult

logger = logging.getLogger(__name__)

TRACE_CONTEXT_KEYS = ("traceparent", "tracestate", "baggage")


class TracingMiddleware(TaskiqMiddleware):
    """Middleware that adds distributed tracing to taskiq tasks.

    On task dispatch (pre_send):
    - Creates a PRODUCER span for the task dispatch operation
    - Injects W3C Trace Context (traceparent, tracestate) and Baggage into message labels

    On task execution (pre_execute/post_execute/on_error):
    - Extracts trace context from message labels
    - Creates a CONSUMER span linked to the producer span
    - Propagates baggage items (user context) to span attributes via BaggageSpanProcessor
    """

    def __init__(self) -> None:
        super().__init__()
        self._active_spans: dict[str, tuple[trace.Span, object]] = {}

    @property
    def _tracer(self) -> trace.Tracer:
        """Get tracer lazily to pick up the current global TracerProvider.

        This allows tests to set their own TracerProvider and have the
        middleware use it, rather than caching the tracer at init time.
        """
        return trace.get_tracer(__name__)

    def _inject_trace_context(self, labels: dict[str, Any]) -> dict[str, Any]:
        """Inject W3C Trace Context and Baggage into task message labels."""
        carrier: dict[str, str] = {}
        propagate.inject(carrier)

        for key in TRACE_CONTEXT_KEYS:
            if key in carrier:
                labels[f"trace.{key}"] = carrier[key]

        return labels

    def _extract_trace_context(self, labels: dict[str, Any]) -> context.Context:
        """Extract W3C Trace Context from task message labels."""
        carrier: dict[str, str] = {}

        for key in TRACE_CONTEXT_KEYS:
            label_key = f"trace.{key}"
            if label_key in labels:
                carrier[key] = str(labels[label_key])

        return propagate.extract(carrier)

    async def pre_send(self, message: TaskiqMessage) -> TaskiqMessage:
        """Inject trace context before sending task to broker.

        Creates a PRODUCER span that represents the task dispatch operation.
        The trace context is injected into message labels so the worker can
        extract it and create a linked CONSUMER span.
        """
        task_name = message.task_name
        task_id = message.task_id

        with self._tracer.start_as_current_span(
            f"taskiq.dispatch.{task_name}",
            kind=trace.SpanKind.PRODUCER,
        ) as span:
            span.set_attribute("messaging.system", "taskiq")
            span.set_attribute("messaging.operation.type", "publish")
            span.set_attribute("messaging.destination.name", task_name)
            span.set_attribute("messaging.message.id", task_id)

            message.labels = self._inject_trace_context(dict(message.labels))

            span.set_status(trace.StatusCode.OK)

        return message

    async def pre_execute(self, message: TaskiqMessage) -> TaskiqMessage:
        """Extract trace context before task execution.

        Creates a CONSUMER span linked to the producer span via the extracted
        trace context. The span remains active during task execution and is
        ended in post_execute or on_error.
        """
        task_name = message.task_name
        task_id = message.task_id

        parent_ctx = self._extract_trace_context(dict(message.labels))

        span = self._tracer.start_span(
            f"taskiq.execute.{task_name}",
            context=parent_ctx,
            kind=trace.SpanKind.CONSUMER,
        )

        span.set_attribute("messaging.system", "taskiq")
        span.set_attribute("messaging.operation.type", "receive")
        span.set_attribute("messaging.destination.name", task_name)
        span.set_attribute("messaging.message.id", task_id)

        token = context.attach(trace.set_span_in_context(span, parent_ctx))
        self._active_spans[task_id] = (span, token)

        logger.debug(f"Started execution span for task {task_id}")

        return message

    async def post_execute(
        self,
        message: TaskiqMessage,
        result: TaskiqResult[Any],  # noqa: ARG002
    ) -> None:
        """Complete the execution span after successful task completion."""
        task_id = message.task_id

        if task_id in self._active_spans:
            span, token = self._active_spans.pop(task_id)
            span.set_status(trace.StatusCode.OK)
            span.end()
            context.detach(token)  # type: ignore[arg-type]
            logger.debug(f"Completed execution span for task {task_id}")

    async def on_error(
        self,
        message: TaskiqMessage,
        result: TaskiqResult[Any],  # noqa: ARG002
        exception: BaseException,
    ) -> None:
        """Complete the execution span with error status when task fails."""
        task_id = message.task_id

        if task_id in self._active_spans:
            span, token = self._active_spans.pop(task_id)
            span.set_status(trace.StatusCode.ERROR, str(exception))
            span.record_exception(exception)
            span.end()
            context.detach(token)  # type: ignore[arg-type]
            logger.debug(f"Completed execution span for task {task_id} with error")
