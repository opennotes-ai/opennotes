"""Unified observability setup using Pydantic Logfire.

Replaces both setup_otel() and setup_traceloop() with a single entry point
that uses logfire.configure() as the OTel TracerProvider, with Cloud Trace
as an additional export destination.

Call setup_observability() early in main.py BEFORE importing instrumented
libraries (FastAPI, SQLAlchemy, Redis, etc.) for auto-instrumentation to work.
"""

import logging
import os
import threading

logger = logging.getLogger(__name__)

_observability_lock = threading.Lock()
_observability_initialized = False


def setup_observability(
    service_name: str,
    service_version: str = "0.0.1",
    environment: str = "development",
    logfire_token: str | None = None,
    trace_content: bool = False,
    sample_rate: float = 0.1,
    use_gcp_exporters: bool = True,
    enable_console_export: bool = False,
) -> bool:
    """Initialize observability with Logfire + Cloud Trace dual export.

    Args:
        service_name: Service name for identification in traces
        service_version: Service version string
        environment: Deployment environment
        logfire_token: Logfire write token (also reads LOGFIRE_TOKEN env var)
        trace_content: Enable logging prompts/completions in traces
        sample_rate: Trace sampling rate 0.0-1.0
        use_gcp_exporters: Use GCP-native exporters on Cloud Run
        enable_console_export: Enable console span export for debugging

    Returns:
        True if initialization succeeded, False otherwise
    """
    global _observability_initialized

    with _observability_lock:
        if _observability_initialized:
            logger.debug("Observability already initialized")
            return True

        if os.getenv("OTEL_SDK_DISABLED", "false").lower() == "true":
            logger.info("OpenTelemetry SDK disabled via OTEL_SDK_DISABLED=true")
            return False

        try:
            import logfire

            from src.monitoring.otel import (
                _get_attribute_sanitizing_processor,
                _get_baggage_span_processor,
                _install_attribute_warning_filter,
            )

            _install_attribute_warning_filter()

            additional_processors = [
                _get_attribute_sanitizing_processor(),
                _get_baggage_span_processor(),
            ]

            from src.monitoring.gcp_resource_detector import is_cloud_run_environment

            if is_cloud_run_environment() and use_gcp_exporters:
                try:
                    from opentelemetry.sdk.trace.export import BatchSpanProcessor

                    from src.config import get_settings
                    from src.monitoring.cloud_trace_logging_exporter import (
                        CloudTraceLoggingSpanExporter,
                    )

                    settings = get_settings()
                    gcp_project = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get(
                        "GCP_PROJECT_ID"
                    )
                    cloud_trace_exporter = CloudTraceLoggingSpanExporter(project_id=gcp_project)
                    cloud_trace_processor = BatchSpanProcessor(
                        cloud_trace_exporter,
                        max_queue_size=settings.OTEL_BSP_MAX_QUEUE_SIZE,
                        schedule_delay_millis=settings.OTEL_BSP_SCHEDULE_DELAY_MILLIS,
                        max_export_batch_size=settings.OTEL_BSP_MAX_EXPORT_BATCH_SIZE,
                        export_timeout_millis=settings.OTEL_BSP_EXPORT_TIMEOUT_MILLIS,
                    )
                    additional_processors.append(cloud_trace_processor)
                    logger.info("Cloud Trace exporter configured as additional Logfire processor")
                except Exception as exc:
                    logger.warning(
                        "GCP exporter setup failed, Cloud Trace export disabled: %s", exc
                    )

            from logfire import SamplingOptions

            logfire.configure(
                token=logfire_token,
                service_name=service_name,
                service_version=service_version,
                environment=environment,
                send_to_logfire="if-token-present" if not logfire_token else True,
                additional_span_processors=additional_processors,
                sampling=SamplingOptions(head=sample_rate),
                scrubbing=False if trace_content else None,
            )

            logfire.instrument_anthropic()
            logfire.instrument_openai()
            logfire.instrument_httpx(capture_all=True)

            try:
                from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
                from opentelemetry.instrumentation.logging import LoggingInstrumentor
                from opentelemetry.instrumentation.redis import RedisInstrumentor
                from opentelemetry.instrumentation.sqlalchemy import (
                    SQLAlchemyInstrumentor,
                )

                FastAPIInstrumentor().instrument()
                RedisInstrumentor().instrument()
                SQLAlchemyInstrumentor().instrument(enable_commenter=True)
                LoggingInstrumentor().instrument(set_logging_format=False)
            except ImportError as e:
                logger.warning(f"Some OTel instrumentors not available: {e}")

            if enable_console_export:
                os.environ.setdefault("LOGFIRE_CONSOLE", "true")

            _observability_initialized = True
            logger.info(
                f"Observability initialized via Logfire: service={service_name}, "
                f"version={service_version}, env={environment}, "
                f"send_to_logfire={'if-token-present' if not logfire_token else True}"
            )
            return True

        except ImportError:
            logger.warning("logfire package not installed - observability disabled")
            return False
        except Exception as e:
            logger.error(f"Failed to initialize observability: {e}")
            return False


def shutdown_observability(flush_timeout_millis: int | None = None) -> None:
    """Gracefully shutdown observability (Logfire TracerProvider + instrumentors)."""
    global _observability_initialized

    with _observability_lock:
        if not _observability_initialized:
            logger.debug("Observability not initialized, nothing to shutdown")
            return

        try:
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
            from opentelemetry.instrumentation.logging import LoggingInstrumentor
            from opentelemetry.instrumentation.redis import RedisInstrumentor
            from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

            FastAPIInstrumentor().uninstrument()
            LoggingInstrumentor().uninstrument()
            RedisInstrumentor().uninstrument()
            SQLAlchemyInstrumentor().uninstrument()
            logger.debug("Uninstrumented all auto-instrumented libraries")
        except ImportError:
            logger.debug("OTel instrumentation packages not available for uninstrument")
        except Exception as e:
            logger.warning(f"Error during uninstrumentation: {e}")

        try:
            import logfire

            timeout = flush_timeout_millis if flush_timeout_millis is not None else 30000
            logfire.shutdown(timeout_millis=timeout)
            logger.info("Logfire shut down")
        except Exception as e:
            logger.warning(f"Error during Logfire shutdown: {e}")

        try:
            from src.monitoring.otel import (
                AttributeSanitizingSpanProcessor,
                BaggageSpanProcessor,
                _remove_attribute_warning_filter,
            )

            AttributeSanitizingSpanProcessor.instance = None
            BaggageSpanProcessor.instance = None
            _remove_attribute_warning_filter()
        except Exception as e:
            logger.warning(f"Error resetting processor state: {e}")
        finally:
            _observability_initialized = False
            logger.debug("Observability state reset")
