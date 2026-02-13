from __future__ import annotations

import logging
import os
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

import google.cloud.logging as google_cloud_logging
from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
from opentelemetry.sdk.trace.export import SpanExportResult

if TYPE_CHECKING:
    from opentelemetry.sdk.trace import ReadableSpan

logger = logging.getLogger(__name__)

CLOUD_LOGGING_LOG_NAME = "span_telemetry"

CLOUD_LOGGING_URL_TEMPLATE = (
    "https://console.cloud.google.com/logs/query"
    ";query=labels.span_id%3D%22{span_id}%22%0A"
    "labels.type%3D%22span_telemetry%22"
    ";project={project_id}"
)


class CloudTraceLoggingSpanExporter(CloudTraceSpanExporter):
    def __init__(
        self,
        logging_client: google_cloud_logging.Client | None = None,
        project_id: str | None = None,
        max_attribute_length: int = 256,
        **kwargs: Any,
    ) -> None:
        resolved_project_id = project_id or os.environ.get("GOOGLE_CLOUD_PROJECT")
        kwargs["project_id"] = resolved_project_id
        super().__init__(**kwargs)

        self.project_id = resolved_project_id or ""
        self.max_attribute_length = max_attribute_length
        self._logging_client = logging_client or google_cloud_logging.Client(
            project=self.project_id
        )
        self._cloud_logger = self._logging_client.logger(CLOUD_LOGGING_LOG_NAME)

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        for span in spans:
            self._process_span(span)

        return super().export(spans)

    def _process_span(self, span: ReadableSpan) -> None:
        attrs = span._attributes  # pyright: ignore[reportAttributeAccessIssue]
        if attrs is None:
            return

        large_attrs: dict[str, Any] = {}
        for key, value in attrs.items():
            if isinstance(value, str) and len(value) > self.max_attribute_length:
                large_attrs[key] = value

        if not large_attrs:
            return

        span_ctx = span.get_span_context()
        span_id = format(span_ctx.span_id, "016x")
        trace_id = format(span_ctx.trace_id, "032x")

        try:
            self._cloud_logger.log_struct(
                large_attrs,
                labels={
                    "type": CLOUD_LOGGING_LOG_NAME,
                    "span_id": span_id,
                    "trace_id": trace_id,
                    "span_name": span.name,
                },
                severity="INFO",
            )
        except Exception:
            logger.warning("Failed to log span attributes to Cloud Logging", exc_info=True)

        cloud_logging_url = CLOUD_LOGGING_URL_TEMPLATE.format(
            span_id=span_id,
            project_id=self.project_id,
        )

        for key in large_attrs:
            truncated = attrs[key][: self.max_attribute_length] + "...[see Cloud Logging]"
            attrs[key] = truncated

        attrs["cloud_logging_url"] = cloud_logging_url
