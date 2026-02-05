"""Unit tests for OpenTelemetry error recording utilities."""

from unittest.mock import MagicMock, patch

from opentelemetry.trace import NonRecordingSpan, SpanContext, StatusCode, TraceFlags

from src.monitoring.errors import record_span_error


class TestRecordSpanError:
    def test_records_error_on_provided_span(self) -> None:
        mock_span = MagicMock()
        mock_span.is_recording.return_value = True
        exception = ValueError("test error message")

        record_span_error(exception, span=mock_span)

        mock_span.set_attribute.assert_called_once_with("error.type", "ValueError")
        mock_span.record_exception.assert_called_once_with(exception)
        mock_span.set_status.assert_called_once_with(StatusCode.ERROR, "test error message")

    def test_no_op_when_span_is_non_recording(self) -> None:
        span_context = SpanContext(
            trace_id=1,
            span_id=1,
            is_remote=False,
            trace_flags=TraceFlags(0),
        )
        non_recording_span = NonRecordingSpan(span_context)
        exception = ValueError("should not be recorded")

        record_span_error(exception, span=non_recording_span)

    def test_no_op_when_span_is_none_and_no_current_span(self) -> None:
        span_context = SpanContext(
            trace_id=1,
            span_id=1,
            is_remote=False,
            trace_flags=TraceFlags(0),
        )
        non_recording_span = NonRecordingSpan(span_context)
        exception = ValueError("should not be recorded")

        with patch(
            "src.monitoring.errors.trace.get_current_span",
            return_value=non_recording_span,
        ):
            record_span_error(exception)

    def test_uses_current_span_when_span_not_provided(self) -> None:
        mock_span = MagicMock()
        mock_span.is_recording.return_value = True
        exception = RuntimeError("error from current span")

        with patch("src.monitoring.errors.trace.get_current_span", return_value=mock_span):
            record_span_error(exception)

        mock_span.set_attribute.assert_called_once_with("error.type", "RuntimeError")
        mock_span.record_exception.assert_called_once_with(exception)
        mock_span.set_status.assert_called_once_with(StatusCode.ERROR, "error from current span")

    def test_sets_error_type_attribute_with_exception_class_name(self) -> None:
        mock_span = MagicMock()
        mock_span.is_recording.return_value = True

        class CustomApplicationError(Exception):
            pass

        exception = CustomApplicationError("custom error")
        record_span_error(exception, span=mock_span)

        mock_span.set_attribute.assert_called_once_with("error.type", "CustomApplicationError")

    def test_sets_error_status_with_exception_message(self) -> None:
        mock_span = MagicMock()
        mock_span.is_recording.return_value = True
        exception = ValueError("Something went wrong")

        record_span_error(exception, span=mock_span)

        mock_span.set_status.assert_called_once_with(StatusCode.ERROR, "Something went wrong")

    def test_handles_exception_with_empty_message(self) -> None:
        mock_span = MagicMock()
        mock_span.is_recording.return_value = True
        exception = ValueError("")

        record_span_error(exception, span=mock_span)

        mock_span.set_status.assert_called_once_with(StatusCode.ERROR, "")

    def test_records_exception_object_itself(self) -> None:
        mock_span = MagicMock()
        mock_span.is_recording.return_value = True
        exception = TypeError("type mismatch")

        record_span_error(exception, span=mock_span)

        mock_span.record_exception.assert_called_once_with(exception)

    def test_no_op_when_span_is_none_explicitly(self) -> None:
        span_context = SpanContext(
            trace_id=1,
            span_id=1,
            is_remote=False,
            trace_flags=TraceFlags(0),
        )
        non_recording_span = NonRecordingSpan(span_context)

        with patch(
            "src.monitoring.errors.trace.get_current_span",
            return_value=non_recording_span,
        ):
            record_span_error(ValueError("test"), span=None)
