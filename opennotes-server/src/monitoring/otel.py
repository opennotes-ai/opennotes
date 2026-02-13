"""Generic OpenTelemetry setup for vendor-neutral observability.

This module provides standard OpenTelemetry instrumentation using OTLP export,
making the observability stack portable across any OTLP-compatible backend
(Tempo, Jaeger, Middleware.io, Honeycomb, etc).

Usage:
    Call setup_otel() early in main.py BEFORE importing instrumented libraries
    (FastAPI, SQLAlchemy, Redis, etc.) for automatic instrumentation to work.

Environment variables:
    - OTEL_SERVICE_NAME: Service name (defaults to PROJECT_NAME)
    - OTEL_EXPORTER_OTLP_ENDPOINT: OTLP endpoint (optional, OTLP export disabled if not set)
    - OTEL_EXPORTER_OTLP_HEADERS: Auth headers in 'key=value' format
    - OTEL_SDK_DISABLED: Set to 'true' to disable OTel entirely (useful for tests)
    - TRACE_SAMPLE_RATE: Sampling rate 0.0-1.0 (default: 0.1)

Created: task-998
"""

import logging
import os
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from opentelemetry import context
    from opentelemetry.sdk.trace import ReadableSpan, Span, SpanProcessor, TracerProvider
    from opentelemetry.sdk.trace.export import SpanExporter

logger = logging.getLogger(__name__)

_otel_lock = threading.Lock()
_otel_initialized = False
_tracer_provider: "TracerProvider | None" = None
_span_exporter: "SpanExporter | None" = None

BAGGAGE_KEYS_TO_PROPAGATE = [
    "discord.user_id",
    "discord.username",
    "discord.guild_id",
    "request_id",
    "enduser.id",
    "user.username",
]


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

    class _BaggageSpanProcessorImpl(SpanProcessorBase, BaggageSpanProcessor):
        """Concrete implementation that inherits from both SpanProcessor and BaggageSpanProcessor."""

    if BaggageSpanProcessor.instance is None:
        BaggageSpanProcessor.instance = _BaggageSpanProcessorImpl()
    return BaggageSpanProcessor.instance  # pyright: ignore[reportReturnType]


def setup_otel(
    service_name: str,
    service_version: str = "0.0.1",
    environment: str = "development",
    otlp_endpoint: str | None = None,
    otlp_headers: str | None = None,
    otlp_insecure: bool = False,
    sample_rate: float = 0.1,
    enable_console_export: bool = False,
) -> bool:
    """Initialize OpenTelemetry with OTLP export.

    IMPORTANT: Call this BEFORE importing any libraries that need instrumentation
    (FastAPI, SQLAlchemy, Redis, httpx) for auto-instrumentation to work correctly.

    Args:
        service_name: Service name for identification in traces
        service_version: Service version string
        environment: Deployment environment (development, staging, production)
        otlp_endpoint: OTLP gRPC endpoint (optional, OTLP export disabled if not set)
        otlp_headers: Auth headers in 'key=value,key2=value2' format
        otlp_insecure: Use insecure connection (no TLS) for OTLP exporter
        sample_rate: Trace sampling rate 0.0-1.0 (default: 0.1 = 10%)
        enable_console_export: Enable console span export for debugging

    Returns:
        True if initialization succeeded, False otherwise
    """
    global _otel_initialized, _tracer_provider

    with _otel_lock:
        if _otel_initialized:
            logger.debug("OpenTelemetry already initialized")
            return True

        if os.getenv("OTEL_SDK_DISABLED", "false").lower() == "true":
            logger.info("OpenTelemetry SDK disabled via OTEL_SDK_DISABLED=true")
            return False

        try:
            from grpc import Compression as GrpcCompression
            from opentelemetry import propagate, trace
            from opentelemetry.baggage.propagation import W3CBaggagePropagator
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
            from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
            from opentelemetry.instrumentation.redis import RedisInstrumentor
            from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
            from opentelemetry.propagators.composite import CompositePropagator
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
            from opentelemetry.sdk.trace.sampling import ParentBasedTraceIdRatio
            from opentelemetry.semconv.resource import ResourceAttributes
            from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

            from src.config import get_settings

            settings = get_settings()

            resource = Resource.create(
                {
                    ResourceAttributes.SERVICE_NAME: service_name,
                    ResourceAttributes.SERVICE_VERSION: service_version,
                    ResourceAttributes.DEPLOYMENT_ENVIRONMENT: environment,
                }
            )

            from src.monitoring.gcp_resource_detector import detect_gcp_cloud_run_resource

            gcp_resource = detect_gcp_cloud_run_resource()
            if gcp_resource is not None:
                resource = resource.merge(gcp_resource)
                logger.info("Merged GCP Cloud Run resource attributes into trace resource")

            sampler = ParentBasedTraceIdRatio(sample_rate)
            _tracer_provider = TracerProvider(resource=resource, sampler=sampler)

            _tracer_provider.add_span_processor(_get_baggage_span_processor())

            from src.monitoring.gcp_resource_detector import is_cloud_run_environment

            global _span_exporter
            if is_cloud_run_environment():
                from src.monitoring.cloud_trace_logging_exporter import (
                    CloudTraceLoggingSpanExporter,
                )

                gcp_project = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get(
                    "GCP_PROJECT_ID"
                )
                _span_exporter = CloudTraceLoggingSpanExporter(
                    project_id=gcp_project,
                )

                batch_processor = BatchSpanProcessor(
                    _span_exporter,
                    max_queue_size=settings.OTEL_BSP_MAX_QUEUE_SIZE,
                    schedule_delay_millis=settings.OTEL_BSP_SCHEDULE_DELAY_MILLIS,
                    max_export_batch_size=settings.OTEL_BSP_MAX_EXPORT_BATCH_SIZE,
                    export_timeout_millis=settings.OTEL_BSP_EXPORT_TIMEOUT_MILLIS,
                )
                _tracer_provider.add_span_processor(batch_processor)

                logger.info("GCP Cloud Trace exporter configured with Cloud Logging overflow")
            elif otlp_endpoint:
                headers = _parse_headers(otlp_headers)

                compression = None
                if settings.OTEL_EXPORTER_COMPRESSION == "gzip":
                    compression = GrpcCompression.Gzip

                _span_exporter = OTLPSpanExporter(
                    endpoint=otlp_endpoint,
                    headers=headers,
                    insecure=otlp_insecure,
                    compression=compression,
                )

                batch_processor = BatchSpanProcessor(
                    _span_exporter,
                    max_queue_size=settings.OTEL_BSP_MAX_QUEUE_SIZE,
                    schedule_delay_millis=settings.OTEL_BSP_SCHEDULE_DELAY_MILLIS,
                    max_export_batch_size=settings.OTEL_BSP_MAX_EXPORT_BATCH_SIZE,
                    export_timeout_millis=settings.OTEL_BSP_EXPORT_TIMEOUT_MILLIS,
                )
                _tracer_provider.add_span_processor(batch_processor)

                logger.info(
                    f"OTLP exporter configured: {otlp_endpoint}, "
                    f"insecure={otlp_insecure}, "
                    f"compression={settings.OTEL_EXPORTER_COMPRESSION}, "
                    f"queue_size={settings.OTEL_BSP_MAX_QUEUE_SIZE}, "
                    f"batch_size={settings.OTEL_BSP_MAX_EXPORT_BATCH_SIZE}"
                )
            else:
                logger.info("No span exporter configured - export disabled")

            if enable_console_export:
                _tracer_provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
                logger.info("Console span exporter enabled")

            trace.set_tracer_provider(_tracer_provider)

            propagate.set_global_textmap(
                CompositePropagator([W3CBaggagePropagator(), TraceContextTextMapPropagator()])
            )

            FastAPIInstrumentor().instrument()
            HTTPXClientInstrumentor().instrument()
            RedisInstrumentor().instrument()
            SQLAlchemyInstrumentor().instrument(enable_commenter=True)

            _otel_initialized = True
            logger.info(
                f"OpenTelemetry initialized: service={service_name}, "
                f"version={service_version}, env={environment}, sample_rate={sample_rate}"
            )
            return True

        except ImportError as e:
            logger.error(f"OpenTelemetry packages not installed: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to initialize OpenTelemetry: {e}")
            return False


def _parse_headers(headers_str: str | None) -> dict[str, str] | None:
    """Parse OTLP headers from 'key=value,key2=value2' format."""
    if not headers_str:
        return None
    headers: dict[str, str] = {}
    for raw_pair in headers_str.split(","):
        pair = raw_pair.strip()
        if "=" in pair:
            key, value = pair.split("=", 1)
            headers[key.strip()] = value.strip()
    return headers if headers else None


def shutdown_otel(flush_timeout_millis: int | None = None) -> None:
    """Gracefully shutdown the tracer provider with force flush.

    This function uninstruments all auto-instrumented libraries and shuts down
    the tracer provider. After calling this, setup_otel can be called again
    to reinitialize OpenTelemetry.

    Args:
        flush_timeout_millis: Timeout for force_flush(). Defaults to
            OTEL_SHUTDOWN_FLUSH_TIMEOUT_MILLIS from settings.
    """
    global _tracer_provider, _otel_initialized, _span_exporter

    with _otel_lock:
        if not _otel_initialized:
            logger.debug("OpenTelemetry not initialized, nothing to shutdown")
            return

        try:
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
            from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
            from opentelemetry.instrumentation.redis import RedisInstrumentor
            from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

            FastAPIInstrumentor().uninstrument()
            HTTPXClientInstrumentor().uninstrument()
            RedisInstrumentor().uninstrument()
            SQLAlchemyInstrumentor().uninstrument()
            logger.debug("Uninstrumented all auto-instrumented libraries")
        except ImportError:
            logger.debug("OpenTelemetry instrumentation packages not available for uninstrument")
        except Exception as e:
            logger.warning(f"Error during uninstrumentation: {e}")

        if _tracer_provider is not None:
            if flush_timeout_millis is None:
                from src.config import get_settings

                flush_timeout_millis = get_settings().OTEL_SHUTDOWN_FLUSH_TIMEOUT_MILLIS

            try:
                _tracer_provider.force_flush(timeout_millis=flush_timeout_millis)
                logger.info("OpenTelemetry spans flushed before shutdown")
            except Exception as e:
                logger.warning(f"Failed to flush spans during shutdown: {e}")

            _tracer_provider.shutdown()
            logger.info("OpenTelemetry tracer provider shut down")

        _tracer_provider = None
        _span_exporter = None
        _otel_initialized = False
        BaggageSpanProcessor.instance = None
        logger.debug("OpenTelemetry state reset, ready for reinitialization")


def is_otel_configured() -> bool:
    """Check if OpenTelemetry environment is configured."""
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT") or os.getenv("OTLP_ENDPOINT")
    return bool(endpoint)


def get_otlp_exporter() -> "SpanExporter | None":
    """Get the configured span exporter.

    Returns the span exporter created during setup_otel() (either
    CloudTraceLoggingSpanExporter on GCP or OTLPSpanExporter elsewhere),
    or None if OpenTelemetry was not initialized or no exporter was configured.

    This allows other components (like Traceloop) to reuse the same exporter
    instead of creating their own, ensuring consistent protocol usage.
    """
    return _span_exporter
