"""OpenTelemetry error recording utilities.

Provides helper functions for consistent error recording to trace spans.
Based on OpenTelemetry semantic conventions for exceptions:
- https://opentelemetry.io/docs/specs/otel/trace/exceptions/
- https://opentelemetry.io/docs/specs/semconv/general/recording-errors/

Created: task-1064.05
"""

from opentelemetry import trace
from opentelemetry.trace import Span, StatusCode


def record_span_error(exception: BaseException, span: Span | None = None) -> None:
    """Record an exception to the current or provided trace span.

    Sets the span status to ERROR, records the exception, and adds the
    error.type semantic attribute per OTel conventions.

    Args:
        exception: The exception to record
        span: Optional span to record to. If None, uses current span.

    Note:
        If no span is available (e.g., tracing disabled), this function
        is a no-op and returns silently.
    """
    if span is None:
        span = trace.get_current_span()

    if not span.is_recording():
        return

    span.set_attribute("error.type", type(exception).__name__)
    span.record_exception(exception)
    span.set_status(StatusCode.ERROR, str(exception))
