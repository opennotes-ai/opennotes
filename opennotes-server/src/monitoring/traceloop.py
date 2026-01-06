"""Traceloop SDK setup for LLM observability.

This module provides Traceloop initialization that can be used by both
the main FastAPI server and taskiq workers.
"""

import logging
import os

logger = logging.getLogger(__name__)

_traceloop_configured = False


def setup_traceloop(
    app_name: str,
    service_name: str,
    version: str,
    environment: str,
    instance_id: str,
    otlp_endpoint: str | None,
    otlp_headers: str | None = None,
    trace_content: bool = False,
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
        otlp_endpoint: OTLP exporter endpoint
        otlp_headers: Comma-separated key=value pairs for OTLP headers
        trace_content: Whether to log prompt/completion content

    Returns:
        True if Traceloop was successfully configured, False otherwise.
    """
    global _traceloop_configured  # noqa: PLW0603

    if _traceloop_configured:
        logger.debug("Traceloop already configured, skipping setup")
        return True

    if not otlp_endpoint:
        logger.warning("Traceloop enabled but OTLP_ENDPOINT not set - LLM observability disabled")
        return False

    try:
        from traceloop.sdk import Traceloop  # noqa: PLC0415

        os.environ["TRACELOOP_TRACE_CONTENT"] = str(trace_content).lower()

        headers: dict[str, str] = {
            "X-Trace-Source": "traceloop",
        }
        if otlp_headers:
            for raw_pair in otlp_headers.split(","):
                pair = raw_pair.strip()
                if "=" in pair:
                    key, value = pair.split("=", 1)
                    headers[key.strip()] = value.strip()

        Traceloop.init(
            app_name=app_name.replace(" ", "-").lower(),
            api_endpoint=otlp_endpoint,
            headers=headers if headers else {},
            disable_batch=False,
            resource_attributes={
                "service.name": service_name,
                "service.version": version,
                "deployment.environment": environment,
                "service.instance.id": instance_id,
            },
            enabled=True,
            telemetry_enabled=False,
        )

        logger.info(
            f"Traceloop LLM observability enabled: endpoint={otlp_endpoint}, "
            f"trace_content={trace_content}"
        )
        _traceloop_configured = True
        return True

    except ImportError:
        logger.warning("traceloop-sdk package not installed - LLM observability disabled")
        return False
    except Exception as e:
        logger.error(f"Failed to configure Traceloop: {e}")
        return False
