"""OpenTelemetry span processors and attribute utilities.

This module provides custom SpanProcessors and logging filters used by
the unified observability setup in ``src.monitoring.observability``.

The processors are:
- ``AttributeSanitizingSpanProcessor``: strips non-primitive span attributes
  before export (prevents warnings from third-party instrumentors).
- ``BaggageSpanProcessor``: copies W3C Baggage items to span attributes for
  visibility in trace backends.

Created: task-998
Refactored: task-1410 (setup_otel/shutdown_otel moved to observability.py)
"""

import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from opentelemetry import context
    from opentelemetry.sdk.trace import ReadableSpan, Span, SpanProcessor

logger = logging.getLogger(__name__)

BAGGAGE_KEYS_TO_PROPAGATE = [
    "platform.user_id",
    "platform.type",
    "platform.scope",
    "platform.community_id",
    "platform.channel_id",
    "community_server_id",
    "request_id",
    "enduser.id",
    "user.username",
]


VALID_ATTR_TYPES = (bool, str, bytes, int, float)


class InvalidAttributeTypeFilter(logging.Filter):
    """Suppress 'Invalid type ... for attribute' warnings from opentelemetry.attributes.

    Third-party instrumentors (e.g., OpenLLMetry/Traceloop for Anthropic) pass
    sentinel values like ``Omit`` and ``NotGiven`` from provider SDKs as span
    attributes.  The OTel SDK logs a WARNING for each one in ``_clean_attribute()``.

    These warnings are harmless: ``AttributeSanitizingSpanProcessor`` already
    strips non-primitive attributes in ``on_end()`` before export.  The filter
    eliminates the per-attribute log noise (153 warnings per agent turn in prod).
    """

    _SUPPRESSED_PREFIXES = (
        "Invalid type",
        "Attribute",
    )

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return all(not msg.startswith(prefix) for prefix in self._SUPPRESSED_PREFIXES)


def _install_attribute_warning_filter() -> None:
    """Install the InvalidAttributeTypeFilter on the opentelemetry.attributes logger.

    Idempotent: safe to call multiple times.
    """
    otel_attr_logger = logging.getLogger("opentelemetry.attributes")
    if any(isinstance(f, InvalidAttributeTypeFilter) for f in otel_attr_logger.filters):
        return
    otel_attr_logger.addFilter(InvalidAttributeTypeFilter())


def _remove_attribute_warning_filter() -> None:
    """Remove all InvalidAttributeTypeFilter instances from the logger."""
    otel_attr_logger = logging.getLogger("opentelemetry.attributes")
    for f in otel_attr_logger.filters[:]:
        if isinstance(f, InvalidAttributeTypeFilter):
            otel_attr_logger.removeFilter(f)


class AttributeSanitizingSpanProcessor:
    """Filter out non-primitive span attribute values before export.

    OpenTelemetry only accepts bool, str, bytes, int, float (or sequences of these).
    Third-party instrumentors (e.g., Anthropic SDK via Traceloop) may set sentinel
    values like ``Omit``/``NOT_GIVEN`` that cause warnings. This processor silently
    drops such values in on_end() before they reach the exporter.
    """

    instance: "AttributeSanitizingSpanProcessor | None" = None

    def on_start(self, span: "Span", parent_context: "context.Context | None" = None) -> None:
        pass

    def on_end(self, span: "ReadableSpan") -> None:
        try:
            if not hasattr(span, "_attributes") or not span._attributes:
                return
            filtered = {}
            for key, value in span._attributes.items():
                if isinstance(value, VALID_ATTR_TYPES) or (
                    isinstance(value, (list, tuple))
                    and all(isinstance(v, VALID_ATTR_TYPES) for v in value)
                ):
                    filtered[key] = value
            span._attributes = filtered
        except Exception:
            logger.warning("AttributeSanitizingSpanProcessor.on_end failed", exc_info=True)

    def shutdown(self) -> None:
        pass

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True


def _get_attribute_sanitizing_processor() -> "SpanProcessor":
    """Get an AttributeSanitizingSpanProcessor wrapped as a SpanProcessor."""
    from opentelemetry.sdk.trace import SpanProcessor as SpanProcessorBase

    class _AttributeSanitizingProcessorImpl(AttributeSanitizingSpanProcessor, SpanProcessorBase):
        pass

    if AttributeSanitizingSpanProcessor.instance is None:
        AttributeSanitizingSpanProcessor.instance = _AttributeSanitizingProcessorImpl()
    return AttributeSanitizingSpanProcessor.instance  # pyright: ignore[reportReturnType]


class BaggageSpanProcessor:
    """Copy baggage items to span attributes for visibility.

    This processor is initialized lazily via _get_baggage_span_processor()
    to avoid import errors when OpenTelemetry packages are not installed.
    """

    instance: "BaggageSpanProcessor | None" = None

    def on_start(self, span: "Span", parent_context: "context.Context | None" = None) -> None:
        from opentelemetry import baggage
        from opentelemetry import context as otel_context

        ctx = parent_context or otel_context.get_current()
        for key in BAGGAGE_KEYS_TO_PROPAGATE:
            value = baggage.get_baggage(key, ctx)
            if value is not None:
                attr_key = key.replace(".", "_")
                span.set_attribute(attr_key, str(value))

    def on_end(self, span: "ReadableSpan") -> None:
        pass

    def shutdown(self) -> None:
        pass

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True


def _get_baggage_span_processor() -> "SpanProcessor":
    """Get a BaggageSpanProcessor instance that implements SpanProcessor.

    Returns a singleton instance wrapped to satisfy the SpanProcessor protocol.
    """
    from opentelemetry.sdk.trace import SpanProcessor as SpanProcessorBase

    class _BaggageSpanProcessorImpl(BaggageSpanProcessor, SpanProcessorBase):
        pass

    if BaggageSpanProcessor.instance is None:
        BaggageSpanProcessor.instance = _BaggageSpanProcessorImpl()
    return BaggageSpanProcessor.instance  # pyright: ignore[reportReturnType]


def is_otel_configured() -> bool:
    """Check if OpenTelemetry environment is configured."""
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT") or os.getenv("OTLP_ENDPOINT")
    if endpoint:
        return True
    from src.monitoring.gcp_resource_detector import is_cloud_run_environment

    return is_cloud_run_environment()
