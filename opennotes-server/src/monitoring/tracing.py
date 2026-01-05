import logging
from typing import Any

from opentelemetry import baggage, context, propagate, trace
from opentelemetry.baggage.propagation import W3CBaggagePropagator
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
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

logger = logging.getLogger(__name__)

BAGGAGE_KEYS_TO_PROPAGATE = [
    "discord.user_id",
    "discord.username",
    "discord.guild_id",
    "request_id",
]


class BaggageSpanProcessor(SpanProcessor):
    """SpanProcessor that copies baggage items to span attributes.

    This ensures context like user ID, guild ID, and request ID are visible
    on every span without requiring explicit attribute setting.
    """

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

    def force_flush(self, timeout_millis: int = 30000) -> bool:  # noqa: ARG002
        return True


class TracingManager:
    def __init__(
        self,
        service_name: str,
        service_version: str,
        environment: str,
        otlp_endpoint: str | None = None,
        otlp_insecure: bool = False,
        otlp_headers: str | None = None,
        enable_console_export: bool = False,
        sample_rate: float = 0.1,
        otel_log_level: str | None = None,
    ) -> None:
        self.service_name = service_name
        self.service_version = service_version
        self.environment = environment
        self.otlp_endpoint = otlp_endpoint
        self.otlp_insecure = otlp_insecure
        self.otlp_headers = otlp_headers
        self.enable_console_export = enable_console_export
        self.sample_rate = sample_rate
        self.otel_log_level = otel_log_level
        self._tracer_provider: TracerProvider | None = None
        self._instrumented_components: set[str] = set()

    def _parse_headers(self) -> dict[str, str] | None:
        """Parse OTLP headers from 'key=value,key2=value2' format to dict."""
        if not self.otlp_headers:
            return None
        headers: dict[str, str] = {}
        for raw_pair in self.otlp_headers.split(","):
            pair = raw_pair.strip()
            if "=" in pair:
                key, value = pair.split("=", 1)
                headers[key.strip()] = value.strip()
        return headers if headers else None

    def _configure_otel_logging(self) -> None:
        """Configure OpenTelemetry SDK logging level for debugging export issues."""
        if not self.otel_log_level:
            return

        level_map = {
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "WARNING": logging.WARNING,
            "ERROR": logging.ERROR,
        }
        level = level_map.get(self.otel_log_level.upper())
        if level is None:
            logger.warning(
                f"Invalid OTEL_LOG_LEVEL: {self.otel_log_level}. "
                f"Valid values: DEBUG, INFO, WARNING, ERROR"
            )
            return

        otel_logger = logging.getLogger("opentelemetry")
        otel_logger.setLevel(level)

        if not otel_logger.handlers:
            handler = logging.StreamHandler()
            handler.setLevel(level)
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            handler.setFormatter(formatter)
            otel_logger.addHandler(handler)

        logger.info(f"OpenTelemetry SDK logging set to {self.otel_log_level}")

    def setup(self) -> None:
        if self._tracer_provider is not None:
            logger.warning("Tracing already initialized, skipping setup")
            return

        self._configure_otel_logging()

        resource = Resource.create(
            {
                ResourceAttributes.SERVICE_NAME: self.service_name,
                ResourceAttributes.SERVICE_VERSION: self.service_version,
                ResourceAttributes.DEPLOYMENT_ENVIRONMENT: self.environment,
            }
        )

        sampler = ParentBasedTraceIdRatio(self.sample_rate)
        self._tracer_provider = TracerProvider(resource=resource, sampler=sampler)
        trace.set_tracer_provider(self._tracer_provider)

        # Configure W3C Trace Context + Baggage propagation
        propagate.set_global_textmap(
            CompositePropagator(
                [
                    TraceContextTextMapPropagator(),
                    W3CBaggagePropagator(),
                ]
            )
        )
        logger.info("W3C Trace Context and Baggage propagators configured")

        self._tracer_provider.add_span_processor(BaggageSpanProcessor())
        logger.info("Baggage span processor enabled")

        if self.otlp_endpoint:
            headers = self._parse_headers()
            endpoint_url = self.otlp_endpoint
            if not endpoint_url.endswith("/v1/traces"):
                endpoint_url = endpoint_url.rstrip("/") + "/v1/traces"
            otlp_exporter = OTLPSpanExporter(
                endpoint=endpoint_url,
                headers=headers,
            )
            self._tracer_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
            headers_status = "with auth" if headers else "no auth"
            logger.info(f"OTLP HTTP tracing enabled: {endpoint_url} ({headers_status})")

        if self.enable_console_export:
            console_exporter = ConsoleSpanExporter()
            self._tracer_provider.add_span_processor(BatchSpanProcessor(console_exporter))
            logger.info("Console span export enabled")

        if "redis" not in self._instrumented_components:
            RedisInstrumentor().instrument()
            self._instrumented_components.add("redis")
            logger.info("Redis instrumentation enabled")

        if "httpx" not in self._instrumented_components:
            HTTPXClientInstrumentor().instrument()
            self._instrumented_components.add("httpx")
            logger.info("HTTPX instrumentation enabled")

        logger.info(
            f"Tracing configured (sample_rate={self.sample_rate}, version={self.service_version})"
        )

    def instrument_fastapi(self, app: Any) -> None:
        if "fastapi" in self._instrumented_components:
            logger.warning("FastAPI already instrumented, skipping")
            return
        FastAPIInstrumentor.instrument_app(app)
        self._instrumented_components.add("fastapi")
        logger.info("FastAPI instrumentation enabled")

    def instrument_sqlalchemy(self, engine: Any) -> None:
        if "sqlalchemy" in self._instrumented_components:
            logger.warning("SQLAlchemy already instrumented, skipping")
            return
        SQLAlchemyInstrumentor().instrument(
            engine=engine,
            enable_commenter=True,
            commenter_options={
                "opentelemetry_values": True,
            },
            enable_attribute_commenter=True,
        )
        self._instrumented_components.add("sqlalchemy")
        logger.info("SQLAlchemy instrumentation enabled with query-level tracing")

    def shutdown(self) -> None:
        if self._tracer_provider:
            self._tracer_provider.shutdown()
            logger.info("Tracing shut down")


def get_tracer(name: str) -> trace.Tracer:
    return trace.get_tracer(name)
