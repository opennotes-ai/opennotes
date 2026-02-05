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
    def test_gcp_trace_format_with_project_id(
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

        mock_settings = MagicMock()
        mock_settings.GCP_PROJECT_ID = "open-notes-core"

        log_data: dict[str, Any] = {}

        with (
            patch("src.config.get_settings", return_value=mock_settings),
            patch("opentelemetry.trace.get_current_span", return_value=mock_span),
        ):
            formatter.add_fields(log_data, log_record, {})

        expected_trace = f"projects/open-notes-core/traces/{trace_id}"
        assert log_data.get("logging.googleapis.com/trace") == expected_trace
        assert "trace_id" not in log_data

    def test_span_id_16_char_hex(
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

        mock_settings = MagicMock()
        mock_settings.GCP_PROJECT_ID = "test-project"

        log_data: dict[str, Any] = {}

        with (
            patch("src.config.get_settings", return_value=mock_settings),
            patch("opentelemetry.trace.get_current_span", return_value=mock_span),
        ):
            formatter.add_fields(log_data, log_record, {})

        span_id_value = log_data.get("logging.googleapis.com/spanId")
        assert span_id_value is not None
        assert len(span_id_value) == 16
        assert re.match(r"^[0-9a-f]{16}$", span_id_value)

    def test_trace_sampled_is_boolean(
        self, formatter: CustomJsonFormatter, log_record: logging.LogRecord
    ) -> None:
        trace_id = "a" * 32
        span_id = "b" * 16

        span_context_sampled = SpanContext(
            trace_id=int(trace_id, 16),
            span_id=int(span_id, 16),
            is_remote=False,
            trace_flags=TraceFlags(0x01),
        )
        mock_span_sampled = NonRecordingSpan(span_context_sampled)

        mock_settings = MagicMock()
        mock_settings.GCP_PROJECT_ID = "test-project"

        log_data: dict[str, Any] = {}

        with (
            patch("src.config.get_settings", return_value=mock_settings),
            patch("opentelemetry.trace.get_current_span", return_value=mock_span_sampled),
        ):
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

        with (
            patch("src.config.get_settings", return_value=mock_settings),
            patch("opentelemetry.trace.get_current_span", return_value=mock_span_not_sampled),
        ):
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

        mock_settings = MagicMock()
        mock_settings.GCP_PROJECT_ID = None

        log_data: dict[str, Any] = {}

        with (
            patch("src.config.get_settings", return_value=mock_settings),
            patch("opentelemetry.trace.get_current_span", return_value=mock_span),
        ):
            formatter.add_fields(log_data, log_record, {})

        assert log_data.get("trace_id") == trace_id
        assert log_data.get("span_id") == span_id
        assert "logging.googleapis.com/trace" not in log_data
        assert "logging.googleapis.com/spanId" not in log_data
        assert "logging.googleapis.com/trace_sampled" not in log_data


class TestOtelAttributeExtraction:
    def test_uses_otel_trace_id_when_present(
        self, formatter: CustomJsonFormatter, log_record: logging.LogRecord
    ) -> None:
        otel_trace_id = "e" * 32
        otel_span_id = "f" * 16

        log_record.otelTraceID = otel_trace_id
        log_record.otelSpanID = otel_span_id
        log_record.otelTraceSampled = True

        mock_settings = MagicMock()
        mock_settings.GCP_PROJECT_ID = "otel-project"

        log_data: dict[str, Any] = {}

        with patch("src.config.get_settings", return_value=mock_settings):
            formatter.add_fields(log_data, log_record, {})

        expected_trace = f"projects/otel-project/traces/{otel_trace_id}"
        assert log_data.get("logging.googleapis.com/trace") == expected_trace
        assert log_data.get("logging.googleapis.com/spanId") == otel_span_id
        assert log_data.get("logging.googleapis.com/trace_sampled") is True

    def test_otel_trace_sampled_treats_non_true_values_as_false(
        self, formatter: CustomJsonFormatter, log_record: logging.LogRecord
    ) -> None:
        """Test that only literal True is treated as sampled.

        The implementation uses `is True` comparison, so any value that is not
        literally True (including truthy strings like "False") results in False.
        """
        log_record.otelTraceID = "a" * 32
        log_record.otelSpanID = "b" * 16

        mock_settings = MagicMock()
        mock_settings.GCP_PROJECT_ID = "test-project"

        for non_true_value in [False, None, 0, "", "False"]:
            log_record.otelTraceSampled = non_true_value
            log_data: dict[str, Any] = {}

            with patch("src.config.get_settings", return_value=mock_settings):
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

        with (
            patch("src.config.get_settings", side_effect=ImportError("no settings")),
            patch("opentelemetry.trace.get_current_span", return_value=mock_span),
        ):
            formatter.add_fields(log_data, log_record, {})

        assert log_data.get("trace_id") == trace_id
        assert log_data.get("span_id") == span_id
        assert "logging.googleapis.com/trace" not in log_data
