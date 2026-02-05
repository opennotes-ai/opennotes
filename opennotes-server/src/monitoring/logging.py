import logging
import sys
from typing import Any

from opentelemetry import trace
from pythonjsonlogger import jsonlogger

LEVEL_TO_SEVERITY: dict[str, int] = {
    "DEBUG": 5,
    "INFO": 9,
    "WARNING": 13,
    "ERROR": 17,
    "CRITICAL": 21,
}


class CustomJsonFormatter(jsonlogger.JsonFormatter):  # type: ignore[name-defined,misc]
    def add_fields(
        self,
        log_data: dict[str, Any],
        record: logging.LogRecord,
        message_dict: dict[str, Any],
    ) -> None:
        super().add_fields(log_data, record, message_dict)

        try:
            from src.config import get_settings

            gcp_project = get_settings().GCP_PROJECT_ID
        except (ImportError, LookupError):
            gcp_project = None

        trace_id: str | None = None
        span_id: str | None = None
        trace_sampled: bool = False

        otel_trace_id = getattr(record, "otelTraceID", None)
        if otel_trace_id and otel_trace_id != "0":
            trace_id = otel_trace_id
            span_id = getattr(record, "otelSpanID", None)
            trace_sampled = getattr(record, "otelTraceSampled", False) is True
        else:
            span = trace.get_current_span()
            if span and span.get_span_context().is_valid:
                span_context = span.get_span_context()
                trace_id = format(span_context.trace_id, "032x")
                span_id = format(span_context.span_id, "016x")
                trace_sampled = span_context.trace_flags.sampled

        if trace_id:
            if gcp_project:
                log_data["logging.googleapis.com/trace"] = (
                    f"projects/{gcp_project}/traces/{trace_id}"
                )
                log_data["logging.googleapis.com/spanId"] = span_id
                log_data["logging.googleapis.com/trace_sampled"] = trace_sampled
            else:
                log_data["trace_id"] = trace_id
                log_data["span_id"] = span_id

        log_data["severity_text"] = record.levelname
        log_data["severity_number"] = LEVEL_TO_SEVERITY.get(record.levelname, 9)

        try:
            from src.middleware.request_id import get_request_id

            request_id = get_request_id()
            if request_id:
                log_data["request_id"] = request_id
        except (ImportError, LookupError):
            pass

        try:
            from src.monitoring.instance import InstanceMetadata

            instance_metadata = InstanceMetadata.get_instance()
            if instance_metadata:
                log_data["instance_id"] = instance_metadata.instance_id
                if instance_metadata.hostname:
                    log_data["hostname"] = instance_metadata.hostname
        except (ImportError, LookupError):
            pass

        log_data["severity"] = record.levelname
        log_data["logger"] = record.name


class ConsoleFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        span = trace.get_current_span()
        if span and span.get_span_context().is_valid:
            span_context = span.get_span_context()
            record.trace_id = format(span_context.trace_id, "032x")
        else:
            record.trace_id = "no-trace"
        return super().format(record)


_logging_configured = False


def setup_logging(
    log_level: str = "INFO",
    json_format: bool = True,
    service_name: str = "opennotes-server",
    module_levels: dict[str, str] | None = None,
) -> None:
    global _logging_configured  # noqa: PLW0603

    if _logging_configured:
        logging.getLogger(__name__).debug("Logging already configured, skipping setup")
        return

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)

    formatter: logging.Formatter
    if json_format:
        formatter = CustomJsonFormatter(
            "%(asctime)s %(name)s %(levelname)s %(message)s",
            timestamp=True,
        )
    else:
        formatter = ConsoleFormatter(
            "%(asctime)s - %(name)s - %(levelname)s - [%(trace_id)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    handler.setFormatter(formatter)
    root_logger.addHandler(handler)

    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)

    if module_levels:
        for module_name, level in module_levels.items():
            logging.getLogger(module_name).setLevel(getattr(logging, level.upper()))

    root_logger.info(
        f"Logging configured for {service_name}",
        extra={"json_format": json_format, "module_levels": module_levels or {}},
    )

    _logging_configured = True


class LogContext:
    def __init__(self, logger: logging.Logger, parent: "LogContext | None" = None) -> None:
        self.logger = logger
        self._context: dict[str, Any] = {}
        self._parent = parent
        self._context_stack: list[dict[str, Any]] = []

    def bind(self, **kwargs: Any) -> "LogContext":
        self._context.update(kwargs)
        return self

    def unbind(self, *keys: str) -> "LogContext":
        for key in keys:
            self._context.pop(key, None)
        return self

    def push_context(self, **kwargs: Any) -> "LogContext":
        self._context_stack.append(self._context.copy())
        self._context.update(kwargs)
        return self

    def pop_context(self) -> "LogContext":
        if self._context_stack:
            self._context = self._context_stack.pop()
        return self

    def _get_all_context(self) -> dict[str, Any]:
        if self._parent:
            parent_context = self._parent._get_all_context()
            parent_context.update(self._context)
            return parent_context
        return self._context.copy()

    def _log(self, level: int, msg: str, *args: Any, **kwargs: Any) -> None:
        extra = kwargs.get("extra", {})
        extra.update(self._get_all_context())
        kwargs["extra"] = extra
        self.logger.log(level, msg, *args, **kwargs)

    def debug(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self._log(logging.DEBUG, msg, *args, **kwargs)

    def info(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self._log(logging.INFO, msg, *args, **kwargs)

    def warning(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self._log(logging.WARNING, msg, *args, **kwargs)

    def error(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self._log(logging.ERROR, msg, *args, **kwargs)

    def exception(self, msg: str, *args: Any, **kwargs: Any) -> None:
        kwargs["exc_info"] = True
        self._log(logging.ERROR, msg, *args, **kwargs)


def get_logger(name: str) -> LogContext:
    return LogContext(logging.getLogger(name))
