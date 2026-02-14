"""Traceloop SDK setup for LLM observability.

This module provides Traceloop initialization that can be used by both
the main FastAPI server and taskiq workers.
"""

import logging
import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from opentelemetry.sdk.trace.export import SpanExporter

logger = logging.getLogger(__name__)

_traceloop_configured = False


def setup_traceloop(
    app_name: str,
    service_name: str,
    version: str,
    environment: str,
    instance_id: str,
    otlp_endpoint: str | None = None,
    otlp_headers: str | None = None,
    trace_content: bool = False,
    exporter: "SpanExporter | None" = None,
) -> bool:
    """Initialize Traceloop SDK for LLM observability.

    Traceloop provides automatic instrumentation for LiteLLM, OpenAI, and Anthropic
    with GenAI semantic conventions (gen_ai.*, llm.*) for token usage, model info,
    and request/response tracing.

    Args:
        app_name: Application name for Traceloop
        service_name: Service name for OTEL resource attributes
        version: Service version
        environment: Deployment environment
        instance_id: Service instance ID
        otlp_endpoint: OTLP exporter endpoint (used if exporter not provided)
        otlp_headers: Comma-separated key=value pairs for OTLP headers
        trace_content: Whether to log prompt/completion content
        exporter: Pre-configured SpanExporter to use (recommended - avoids
            protocol mismatch between gRPC/HTTP OTLP). If provided, otlp_endpoint
            is ignored and this exporter is used directly.

    Returns:
        True if Traceloop was successfully configured, False otherwise.
    """
    global _traceloop_configured

    if _traceloop_configured:
        logger.debug("Traceloop already configured, skipping setup")
        return True

    if not exporter and not otlp_endpoint:
        logger.warning(
            "Traceloop enabled but no exporter or OTLP_ENDPOINT set - LLM observability disabled"
        )
        return False

    try:
        from traceloop.sdk import Traceloop

        os.environ["TRACELOOP_TRACE_CONTENT"] = str(trace_content).lower()

        init_kwargs: dict[str, Any] = {
            "app_name": app_name.replace(" ", "-").lower(),
            "disable_batch": False,
            "resource_attributes": {
                "service.name": service_name,
                "service.version": version,
                "deployment.environment": environment,
                "service.instance.id": instance_id,
            },
            "enabled": True,
            "telemetry_enabled": False,
        }

        if exporter:
            init_kwargs["exporter"] = exporter
            logger.info(
                f"Traceloop LLM observability enabled with shared exporter, "
                f"trace_content={trace_content}"
            )
        else:
            headers: dict[str, str] = {
                "X-Trace-Source": "traceloop",
            }
            if otlp_headers:
                for raw_pair in otlp_headers.split(","):
                    pair = raw_pair.strip()
                    if "=" in pair:
                        key, value = pair.split("=", 1)
                        headers[key.strip()] = value.strip()

            init_kwargs["api_endpoint"] = otlp_endpoint
            init_kwargs["headers"] = headers if headers else {}
            logger.info(
                f"Traceloop LLM observability enabled: endpoint={otlp_endpoint}, "
                f"trace_content={trace_content}"
            )

        from src.monitoring.gcp_resource_detector import is_cloud_run_environment

        if is_cloud_run_environment():
            try:
                from opentelemetry.exporter.cloud_logging import CloudLoggingExporter
                from opentelemetry.exporter.cloud_monitoring import (
                    CloudMonitoringMetricsExporter,
                )

                init_kwargs["metrics_exporter"] = CloudMonitoringMetricsExporter()
                init_kwargs["logging_exporter"] = CloudLoggingExporter()
                logger.info("Traceloop configured with GCP metrics and logging exporters")
            except ImportError:
                logger.warning("GCP exporter packages not installed, skipping GCP exporters")

        Traceloop.init(**init_kwargs)

        _traceloop_configured = True
        return True

    except ImportError:
        logger.warning("traceloop-sdk package not installed - LLM observability disabled")
        return False
    except Exception as e:
        logger.error(f"Failed to configure Traceloop: {e}")
        return False
