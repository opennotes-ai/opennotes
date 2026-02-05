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
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.trace import TracerProvider

logger = logging.getLogger(__name__)

_otel_initialized = False
_tracer_provider: "TracerProvider | None" = None
_otlp_exporter: "OTLPSpanExporter | None" = None

BAGGAGE_KEYS_TO_PROPAGATE = [
    "discord.user_id",
    "discord.username",
    "discord.guild_id",
    "request_id",
    "enduser.id",
    "user.username",
]


def setup_otel(
    service_name: str,
    service_version: str = "0.0.1",
    environment: str = "development",
    otlp_endpoint: str | None = None,
    otlp_headers: str | None = None,
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
        sample_rate: Trace sampling rate 0.0-1.0 (default: 0.1 = 10%)
        enable_console_export: Enable console span export for debugging

    Returns:
        True if initialization succeeded, False otherwise
    """
    global _otel_initialized, _tracer_provider

    if _otel_initialized:
        logger.debug("OpenTelemetry already initialized")
        return True

    if os.getenv("OTEL_SDK_DISABLED", "false").lower() == "true":
        logger.info("OpenTelemetry SDK disabled via OTEL_SDK_DISABLED=true")
        return False

    try:
        from opentelemetry import baggage, context, propagate, trace
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
        from opentelemetry.sdk.trace import ReadableSpan, Span, SpanProcessor, TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
        from opentelemetry.sdk.trace.sampling import ParentBasedTraceIdRatio
        from opentelemetry.semconv.resource import ResourceAttributes
        from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

        class BaggageSpanProcessor(SpanProcessor):
            """Copy baggage items to span attributes for visibility."""

            def on_start(self, span: Span, parent_context: context.Context | None = None) -> None:
                ctx = parent_context or context.get_current()
                for key in BAGGAGE_KEYS_TO_PROPAGATE:
                    value = baggage.get_baggage(key, ctx)
                    if value is not None:
                        attr_key = key.replace(".", "_")
                        span.set_attribute(attr_key, str(value))

            def on_end(self, span: ReadableSpan) -> None:
                pass

            def shutdown(self) -> None:
                pass

            def force_flush(self, timeout_millis: int = 30000) -> bool:
                return True

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

        _tracer_provider.add_span_processor(BaggageSpanProcessor())

        global _otlp_exporter
        endpoint = otlp_endpoint or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
        if endpoint:
            headers = _parse_headers(otlp_headers or os.getenv("OTEL_EXPORTER_OTLP_HEADERS"))
            _otlp_exporter = OTLPSpanExporter(endpoint=endpoint, headers=headers, insecure=True)
            _tracer_provider.add_span_processor(BatchSpanProcessor(_otlp_exporter))
            logger.info(f"OTLP exporter configured: {endpoint}")
        else:
            logger.info("OTLP endpoint not configured - OTLP export disabled")

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


def shutdown_otel() -> None:
    """Gracefully shutdown the tracer provider."""
    global _tracer_provider
    if _tracer_provider is not None:
        _tracer_provider.shutdown()
        logger.info("OpenTelemetry tracer provider shut down")


def is_otel_configured() -> bool:
    """Check if OpenTelemetry environment is configured."""
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT") or os.getenv("OTLP_ENDPOINT")
    return bool(endpoint)


def get_otlp_exporter() -> "OTLPSpanExporter | None":
    """Get the configured OTLP span exporter.

    Returns the gRPC OTLP exporter created during setup_otel(), or None
    if OpenTelemetry was not initialized or no OTLP endpoint was configured.

    This allows other components (like Traceloop) to reuse the same exporter
    instead of creating their own, ensuring consistent protocol usage.
    """
    return _otlp_exporter
