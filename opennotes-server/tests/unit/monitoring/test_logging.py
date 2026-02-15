import logging
import re
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from opentelemetry.trace import SpanContext, TraceFlags
from opentelemetry.trace.span import NonRecordingSpan

from src.monitoring.logging import CustomJsonFormatter


@pytest.fixture
def formatter() -> CustomJsonFormatter:
    with patch("src.config.get_settings", side_effect=ImportError("no settings")):
        return CustomJsonFormatter("%(message)s", timestamp=True)


def create_formatter_with_gcp_project(
    project_id: str,
    service_name: str = "opennotes-server",
    version: str = "0.0.1",
) -> CustomJsonFormatter:
    """Factory function to create a formatter with a specific GCP project ID."""
    mock_settings = MagicMock()
    mock_settings.GCP_PROJECT_ID = project_id
    mock_settings.OTEL_SERVICE_NAME = service_name
    mock_settings.PROJECT_NAME = "Open Notes Server"
    mock_settings.VERSION = version
    with patch("src.config.get_settings", return_value=mock_settings):
        return CustomJsonFormatter("%(message)s", timestamp=True)


@pytest.fixture
def log_record() -> logging.LogRecord:
    return logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname="test.py",
        lineno=1,
        msg="Test message",
        args=(),
        exc_info=None,
    )


class TestGCPTraceFormat:
    def test_gcp_trace_format_with_project_id(self, log_record: logging.LogRecord) -> None:
        formatter = create_formatter_with_gcp_project("open-notes-core")
        trace_id = "a" * 32
        span_id = "b" * 16

        span_context = SpanContext(
            trace_id=int(trace_id, 16),
            span_id=int(span_id, 16),
            is_remote=False,
            trace_flags=TraceFlags(0x01),
        )
        mock_span = NonRecordingSpan(span_context)

        log_data: dict[str, Any] = {}

        with patch("opentelemetry.trace.get_current_span", return_value=mock_span):
            formatter.add_fields(log_data, log_record, {})

        expected_trace = f"projects/open-notes-core/traces/{trace_id}"
        assert log_data.get("logging.googleapis.com/trace") == expected_trace
        assert "trace_id" not in log_data

    def test_span_id_16_char_hex(self, log_record: logging.LogRecord) -> None:
        formatter = create_formatter_with_gcp_project("test-project")
        trace_id = "a" * 32
        span_id = "b" * 16

        span_context = SpanContext(
            trace_id=int(trace_id, 16),
            span_id=int(span_id, 16),
            is_remote=False,
            trace_flags=TraceFlags(0x01),
        )
        mock_span = NonRecordingSpan(span_context)

        log_data: dict[str, Any] = {}

        with patch("opentelemetry.trace.get_current_span", return_value=mock_span):
            formatter.add_fields(log_data, log_record, {})

        span_id_value = log_data.get("logging.googleapis.com/spanId")
        assert span_id_value is not None
        assert len(span_id_value) == 16
        assert re.match(r"^[0-9a-f]{16}$", span_id_value)

    def test_trace_sampled_is_boolean(self, log_record: logging.LogRecord) -> None:
        formatter = create_formatter_with_gcp_project("test-project")
        trace_id = "a" * 32
        span_id = "b" * 16

        span_context_sampled = SpanContext(
            trace_id=int(trace_id, 16),
            span_id=int(span_id, 16),
            is_remote=False,
            trace_flags=TraceFlags(0x01),
        )
        mock_span_sampled = NonRecordingSpan(span_context_sampled)

        log_data: dict[str, Any] = {}

        with patch("opentelemetry.trace.get_current_span", return_value=mock_span_sampled):
            formatter.add_fields(log_data, log_record, {})

        trace_sampled = log_data.get("logging.googleapis.com/trace_sampled")
        assert isinstance(trace_sampled, bool)
        assert trace_sampled is True

        span_context_not_sampled = SpanContext(
            trace_id=int(trace_id, 16),
            span_id=int(span_id, 16),
            is_remote=False,
            trace_flags=TraceFlags(0x00),
        )
        mock_span_not_sampled = NonRecordingSpan(span_context_not_sampled)

        log_data_not_sampled: dict[str, Any] = {}

        with patch("opentelemetry.trace.get_current_span", return_value=mock_span_not_sampled):
            formatter.add_fields(log_data_not_sampled, log_record, {})

        trace_sampled_false = log_data_not_sampled.get("logging.googleapis.com/trace_sampled")
        assert isinstance(trace_sampled_false, bool)
        assert trace_sampled_false is False

    def test_legacy_format_without_project_id(
        self, formatter: CustomJsonFormatter, log_record: logging.LogRecord
    ) -> None:
        trace_id = "c" * 32
        span_id = "d" * 16

        span_context = SpanContext(
            trace_id=int(trace_id, 16),
            span_id=int(span_id, 16),
            is_remote=False,
            trace_flags=TraceFlags(0x01),
        )
        mock_span = NonRecordingSpan(span_context)

        log_data: dict[str, Any] = {}

        with patch("opentelemetry.trace.get_current_span", return_value=mock_span):
            formatter.add_fields(log_data, log_record, {})

        assert log_data.get("trace_id") == trace_id
        assert log_data.get("span_id") == span_id
        assert "logging.googleapis.com/trace" not in log_data
        assert "logging.googleapis.com/spanId" not in log_data
        assert "logging.googleapis.com/trace_sampled" not in log_data


class TestOtelAttributeExtraction:
    def test_uses_otel_trace_id_when_present(self, log_record: logging.LogRecord) -> None:
        formatter = create_formatter_with_gcp_project("otel-project")
        otel_trace_id = "e" * 32
        otel_span_id = "f" * 16

        log_record.otelTraceID = otel_trace_id
        log_record.otelSpanID = otel_span_id
        log_record.otelTraceSampled = True

        log_data: dict[str, Any] = {}

        formatter.add_fields(log_data, log_record, {})

        expected_trace = f"projects/otel-project/traces/{otel_trace_id}"
        assert log_data.get("logging.googleapis.com/trace") == expected_trace
        assert log_data.get("logging.googleapis.com/spanId") == otel_span_id
        assert log_data.get("logging.googleapis.com/trace_sampled") is True

    def test_otel_trace_sampled_treats_non_true_values_as_false(
        self, log_record: logging.LogRecord
    ) -> None:
        """Test that only literal True is treated as sampled.

        The implementation uses `is True` comparison, so any value that is not
        literally True (including truthy strings like "False") results in False.
        """
        formatter = create_formatter_with_gcp_project("test-project")
        log_record.otelTraceID = "a" * 32
        log_record.otelSpanID = "b" * 16

        for non_true_value in [False, None, 0, "", "False"]:
            log_record.otelTraceSampled = non_true_value
            log_data: dict[str, Any] = {}

            formatter.add_fields(log_data, log_record, {})

            assert log_data.get("logging.googleapis.com/trace_sampled") is False


class TestSettingsImportError:
    def test_handles_settings_import_error(
        self, formatter: CustomJsonFormatter, log_record: logging.LogRecord
    ) -> None:
        trace_id = "a" * 32
        span_id = "b" * 16

        span_context = SpanContext(
            trace_id=int(trace_id, 16),
            span_id=int(span_id, 16),
            is_remote=False,
            trace_flags=TraceFlags(0x01),
        )
        mock_span = NonRecordingSpan(span_context)

        log_data: dict[str, Any] = {}

        with patch("opentelemetry.trace.get_current_span", return_value=mock_span):
            formatter.add_fields(log_data, log_record, {})

        assert log_data.get("trace_id") == trace_id
        assert log_data.get("span_id") == span_id
        assert "logging.googleapis.com/trace" not in log_data


class TestErrorReportingFields:
    def test_error_level_gets_reported_error_event_type(self) -> None:
        formatter = create_formatter_with_gcp_project("open-notes-core")
        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="src/api.py",
            lineno=42,
            msg="Something broke",
            args=(),
            exc_info=None,
        )
        log_data: dict[str, Any] = {}
        formatter.add_fields(log_data, record, {})

        assert log_data["@type"] == (
            "type.googleapis.com/google.devtools.clouderrorreporting.v1beta1.ReportedErrorEvent"
        )
        assert "serviceContext" in log_data

    def test_info_level_does_not_get_error_reporting_fields(self) -> None:
        formatter = create_formatter_with_gcp_project("open-notes-core")
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="src/api.py",
            lineno=10,
            msg="All good",
            args=(),
            exc_info=None,
        )
        log_data: dict[str, Any] = {}
        formatter.add_fields(log_data, record, {})

        assert "@type" not in log_data
        assert "serviceContext" not in log_data
        assert "context" not in log_data

    def test_no_gcp_project_no_error_reporting_fields(self) -> None:
        with patch("src.config.get_settings", side_effect=ImportError("no settings")):
            formatter = CustomJsonFormatter("%(message)s", timestamp=True)
        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="src/api.py",
            lineno=42,
            msg="Error without GCP",
            args=(),
            exc_info=None,
        )
        log_data: dict[str, Any] = {}
        formatter.add_fields(log_data, record, {})

        assert "@type" not in log_data
        assert "serviceContext" not in log_data

    def test_service_context_version_from_settings(self) -> None:
        formatter = create_formatter_with_gcp_project(
            "open-notes-core", service_name="opennotes-server", version="a1b2c3d"
        )
        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="src/api.py",
            lineno=42,
            msg="Error",
            args=(),
            exc_info=None,
        )
        log_data: dict[str, Any] = {}
        formatter.add_fields(log_data, record, {})

        assert log_data["serviceContext"]["service"] == "opennotes-server"
        assert log_data["serviceContext"]["version"] == "a1b2c3d"

    def test_exception_includes_stack_trace(self) -> None:
        formatter = create_formatter_with_gcp_project("open-notes-core")
        try:
            raise ValueError("test exception")
        except ValueError:
            import sys

            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="src/api.py",
            lineno=42,
            msg="Caught exception",
            args=(),
            exc_info=exc_info,
        )
        log_data: dict[str, Any] = {}
        formatter.add_fields(log_data, record, {})

        assert "stack_trace" in log_data
        assert "ValueError" in log_data["stack_trace"]
        assert "test exception" in log_data["stack_trace"]

    def test_report_location_from_record(self) -> None:
        formatter = create_formatter_with_gcp_project("open-notes-core")
        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="src/events/nats_client.py",
            lineno=206,
            msg="Publish failed",
            args=(),
            exc_info=None,
        )
        record.funcName = "publish"
        log_data: dict[str, Any] = {}
        formatter.add_fields(log_data, record, {})

        location = log_data["context"]["reportLocation"]
        assert location["filePath"] == "src/events/nats_client.py"
        assert location["lineNumber"] == 206
        assert location["functionName"] == "publish"
