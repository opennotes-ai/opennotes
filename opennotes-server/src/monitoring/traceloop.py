import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_traceloop_configured = False


def _parse_otlp_headers(otlp_headers: str | None) -> dict[str, str]:
    headers: dict[str, str] = {"X-Trace-Source": "traceloop"}
    if otlp_headers:
        for raw_pair in otlp_headers.split(","):
            pair = raw_pair.strip()
            if "=" in pair:
                key, value = pair.split("=", 1)
                headers[key.strip()] = value.strip()
    return headers


def _configure_span_exporter(
    init_kwargs: dict[str, Any],
    otlp_endpoint: str,
    otlp_headers: str | None,
    trace_content: bool,
) -> None:
    from src.monitoring.gcp_resource_detector import is_cloud_run_environment

    if not is_cloud_run_environment():
        _configure_otlp_exporter(init_kwargs, otlp_endpoint, otlp_headers, trace_content)
        return

    try:
        from src.monitoring.cloud_trace_logging_exporter import (
            CloudTraceLoggingSpanExporter,
        )

        gcp_project = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCP_PROJECT_ID")
        init_kwargs["exporter"] = CloudTraceLoggingSpanExporter(project_id=gcp_project)
        logger.info(
            f"Traceloop LLM observability enabled with dedicated GCP exporter, "
            f"trace_content={trace_content}"
        )
    except ImportError:
        logger.warning(
            "GCP exporter packages not available for Traceloop, falling back to OTLP endpoint"
        )
        _configure_otlp_exporter(init_kwargs, otlp_endpoint, otlp_headers, trace_content)


def _configure_otlp_exporter(
    init_kwargs: dict[str, Any],
    otlp_endpoint: str,
    otlp_headers: str | None,
    trace_content: bool,
) -> None:
    headers = _parse_otlp_headers(otlp_headers)
    init_kwargs["api_endpoint"] = otlp_endpoint
    init_kwargs["headers"] = headers if headers else {}
    logger.info(
        f"Traceloop LLM observability enabled: endpoint={otlp_endpoint}, "
        f"trace_content={trace_content}"
    )


def setup_traceloop(
    app_name: str,
    service_name: str,
    version: str,
    environment: str,
    instance_id: str,
    otlp_endpoint: str | None = None,
    otlp_headers: str | None = None,
    trace_content: bool = False,
) -> bool:
    global _traceloop_configured

    if _traceloop_configured:
        logger.debug("Traceloop already configured, skipping setup")
        return True

    if not otlp_endpoint:
        logger.warning("Traceloop enabled but no OTLP_ENDPOINT set - LLM observability disabled")
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

        _configure_span_exporter(init_kwargs, otlp_endpoint, otlp_headers, trace_content)

        from src.monitoring.gcp_resource_detector import is_cloud_run_environment

        if is_cloud_run_environment():
            try:
                from opentelemetry.exporter.cloud_logging import CloudLoggingExporter

                init_kwargs["logging_exporter"] = CloudLoggingExporter()
                logger.info("Traceloop configured with GCP logging exporter")
            except ImportError:
                logger.warning("GCP exporter packages not installed, skipping GCP exporters")

        try:
            from traceloop.sdk.instruments import Instruments

            init_kwargs["block_instruments"] = {Instruments.REDIS}
        except (ImportError, AttributeError):
            logger.warning("Could not configure block_instruments — Instruments enum unavailable")

        Traceloop.init(**init_kwargs)

        _traceloop_configured = True
        return True

    except ImportError:
        logger.warning("traceloop-sdk package not installed - LLM observability disabled")
        return False
    except Exception as e:
        logger.error(f"Failed to configure Traceloop: {e}")
        return False
