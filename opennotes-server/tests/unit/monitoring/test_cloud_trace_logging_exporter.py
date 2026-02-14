from types import MappingProxyType
from unittest.mock import MagicMock, patch

from opentelemetry.sdk.trace import BoundedAttributes, ReadableSpan, StatusCode
from opentelemetry.sdk.trace.export import SpanExportResult
from opentelemetry.trace import SpanContext, SpanKind, TraceFlags


def _make_span(
    trace_id: int = 0xABCDEF1234567890ABCDEF1234567890,
    span_id: int = 0x1234567890ABCDEF,
    name: str = "test-span",
    attributes: dict | None = None,
) -> ReadableSpan:
    ctx = SpanContext(
        trace_id=trace_id,
        span_id=span_id,
        is_remote=False,
        trace_flags=TraceFlags(TraceFlags.SAMPLED),
    )
    span = MagicMock(spec=ReadableSpan)
    span.name = name
    span.context = ctx
    span.get_span_context.return_value = ctx
    span.kind = SpanKind.INTERNAL
    span.status = MagicMock()
    span.status.status_code = StatusCode.UNSET
    span.start_time = 1000000000
    span.end_time = 2000000000
    span.events = []
    span.links = []
    span.resource = MagicMock()
    attrs = attributes or {}
    span._attributes = BoundedAttributes(attributes=attrs)
    span.attributes = MappingProxyType(dict(span._attributes))
    return span


class TestExportDelegatesToParent:
    @patch(
        "src.monitoring.cloud_trace_logging_exporter.CloudTraceSpanExporter.__init__",
        return_value=None,
    )
    @patch("src.monitoring.cloud_trace_logging_exporter.CloudTraceSpanExporter.export")
    @patch("src.monitoring.cloud_trace_logging_exporter.google_cloud_logging")
    def test_export_calls_parent_export(self, mock_gcl, mock_parent_export, _mock_init) -> None:
        mock_parent_export.return_value = SpanExportResult.SUCCESS
        mock_logging_client = MagicMock()
        mock_gcl.Client.return_value = mock_logging_client

        from src.monitoring.cloud_trace_logging_exporter import CloudTraceLoggingSpanExporter

        exporter = CloudTraceLoggingSpanExporter(
            project_id="test-project",
            logging_client=mock_logging_client,
        )

        spans = [_make_span(attributes={"small": "value"})]
        result = exporter.export(spans)

        assert result == SpanExportResult.SUCCESS
        mock_parent_export.assert_called_once()

    @patch(
        "src.monitoring.cloud_trace_logging_exporter.CloudTraceSpanExporter.__init__",
        return_value=None,
    )
    @patch("src.monitoring.cloud_trace_logging_exporter.CloudTraceSpanExporter.export")
    @patch("src.monitoring.cloud_trace_logging_exporter.google_cloud_logging")
    def test_export_returns_parent_result(self, mock_gcl, mock_parent_export, _mock_init) -> None:
        mock_parent_export.return_value = SpanExportResult.FAILURE
        mock_logging_client = MagicMock()

        from src.monitoring.cloud_trace_logging_exporter import CloudTraceLoggingSpanExporter

        exporter = CloudTraceLoggingSpanExporter(
            project_id="test-project",
            logging_client=mock_logging_client,
        )

        spans = [_make_span()]
        result = exporter.export(spans)

        assert result == SpanExportResult.FAILURE


class TestCloudLoggingIntegration:
    @patch(
        "src.monitoring.cloud_trace_logging_exporter.CloudTraceSpanExporter.__init__",
        return_value=None,
    )
    @patch("src.monitoring.cloud_trace_logging_exporter.CloudTraceSpanExporter.export")
    @patch("src.monitoring.cloud_trace_logging_exporter.google_cloud_logging")
    def test_logs_large_attributes_to_cloud_logging(
        self, mock_gcl, mock_parent_export, _mock_init
    ) -> None:
        mock_parent_export.return_value = SpanExportResult.SUCCESS
        mock_logging_client = MagicMock()
        mock_logger = MagicMock()
        mock_logging_client.logger.return_value = mock_logger

        from src.monitoring.cloud_trace_logging_exporter import CloudTraceLoggingSpanExporter

        exporter = CloudTraceLoggingSpanExporter(
            project_id="test-project",
            logging_client=mock_logging_client,
            max_attribute_length=10,
        )

        large_value = "x" * 50
        spans = [_make_span(attributes={"big_attr": large_value})]
        exporter.export(spans)

        mock_logger.log_struct.assert_called_once()
        logged_data = mock_logger.log_struct.call_args[0][0]
        assert logged_data["big_attr"] == large_value

    @patch(
        "src.monitoring.cloud_trace_logging_exporter.CloudTraceSpanExporter.__init__",
        return_value=None,
    )
    @patch("src.monitoring.cloud_trace_logging_exporter.CloudTraceSpanExporter.export")
    @patch("src.monitoring.cloud_trace_logging_exporter.google_cloud_logging")
    def test_does_not_log_when_no_large_attributes(
        self, mock_gcl, mock_parent_export, _mock_init
    ) -> None:
        mock_parent_export.return_value = SpanExportResult.SUCCESS
        mock_logging_client = MagicMock()
        mock_logger = MagicMock()
        mock_logging_client.logger.return_value = mock_logger

        from src.monitoring.cloud_trace_logging_exporter import CloudTraceLoggingSpanExporter

        exporter = CloudTraceLoggingSpanExporter(
            project_id="test-project",
            logging_client=mock_logging_client,
            max_attribute_length=256,
        )

        spans = [_make_span(attributes={"small": "value"})]
        exporter.export(spans)

        mock_logger.log_struct.assert_not_called()

    @patch(
        "src.monitoring.cloud_trace_logging_exporter.CloudTraceSpanExporter.__init__",
        return_value=None,
    )
    @patch("src.monitoring.cloud_trace_logging_exporter.CloudTraceSpanExporter.export")
    @patch("src.monitoring.cloud_trace_logging_exporter.google_cloud_logging")
    def test_log_struct_labels_include_span_and_trace_ids(
        self, mock_gcl, mock_parent_export, _mock_init
    ) -> None:
        mock_parent_export.return_value = SpanExportResult.SUCCESS
        mock_logging_client = MagicMock()
        mock_logger = MagicMock()
        mock_logging_client.logger.return_value = mock_logger

        from src.monitoring.cloud_trace_logging_exporter import CloudTraceLoggingSpanExporter

        exporter = CloudTraceLoggingSpanExporter(
            project_id="test-project",
            logging_client=mock_logging_client,
            max_attribute_length=10,
        )

        spans = [_make_span(attributes={"big": "a" * 20})]
        exporter.export(spans)

        call_kwargs = mock_logger.log_struct.call_args[1]
        labels = call_kwargs["labels"]
        assert labels["type"] == "span_telemetry"
        assert "span_id" in labels
        assert "trace_id" in labels


class TestCloudLoggingUrl:
    @patch(
        "src.monitoring.cloud_trace_logging_exporter.CloudTraceSpanExporter.__init__",
        return_value=None,
    )
    @patch("src.monitoring.cloud_trace_logging_exporter.CloudTraceSpanExporter.export")
    @patch("src.monitoring.cloud_trace_logging_exporter.google_cloud_logging")
    def test_adds_cloud_logging_url_attribute_to_span(
        self, mock_gcl, mock_parent_export, _mock_init
    ) -> None:
        mock_parent_export.return_value = SpanExportResult.SUCCESS
        mock_logging_client = MagicMock()
        mock_logger = MagicMock()
        mock_logging_client.logger.return_value = mock_logger

        from src.monitoring.cloud_trace_logging_exporter import CloudTraceLoggingSpanExporter

        exporter = CloudTraceLoggingSpanExporter(
            project_id="test-project",
            logging_client=mock_logging_client,
            max_attribute_length=10,
        )

        spans = [_make_span(attributes={"big": "a" * 20})]
        exporter.export(spans)

        exported_spans = mock_parent_export.call_args[0][0]
        span = exported_spans[0]
        assert "cloud_logging_url" in span._attributes

    @patch(
        "src.monitoring.cloud_trace_logging_exporter.CloudTraceSpanExporter.__init__",
        return_value=None,
    )
    @patch("src.monitoring.cloud_trace_logging_exporter.CloudTraceSpanExporter.export")
    @patch("src.monitoring.cloud_trace_logging_exporter.google_cloud_logging")
    def test_cloud_logging_url_format(self, mock_gcl, mock_parent_export, _mock_init) -> None:
        mock_parent_export.return_value = SpanExportResult.SUCCESS
        mock_logging_client = MagicMock()
        mock_logger = MagicMock()
        mock_logging_client.logger.return_value = mock_logger

        from src.monitoring.cloud_trace_logging_exporter import CloudTraceLoggingSpanExporter

        exporter = CloudTraceLoggingSpanExporter(
            project_id="my-gcp-project",
            logging_client=mock_logging_client,
            max_attribute_length=10,
        )

        spans = [_make_span(attributes={"big": "a" * 20})]
        exporter.export(spans)

        exported_spans = mock_parent_export.call_args[0][0]
        url = exported_spans[0]._attributes["cloud_logging_url"]
        assert "my-gcp-project" in url
        assert "console.cloud.google.com/logs/query" in url
        assert "span_telemetry" in url


class TestTruncation:
    @patch(
        "src.monitoring.cloud_trace_logging_exporter.CloudTraceSpanExporter.__init__",
        return_value=None,
    )
    @patch("src.monitoring.cloud_trace_logging_exporter.CloudTraceSpanExporter.export")
    @patch("src.monitoring.cloud_trace_logging_exporter.google_cloud_logging")
    def test_large_attribute_values_truncated_before_cloud_trace(
        self, mock_gcl, mock_parent_export, _mock_init
    ) -> None:
        mock_parent_export.return_value = SpanExportResult.SUCCESS
        mock_logging_client = MagicMock()
        mock_logger = MagicMock()
        mock_logging_client.logger.return_value = mock_logger

        from src.monitoring.cloud_trace_logging_exporter import CloudTraceLoggingSpanExporter

        exporter = CloudTraceLoggingSpanExporter(
            project_id="test-project",
            logging_client=mock_logging_client,
            max_attribute_length=10,
        )

        large_value = "x" * 50
        spans = [_make_span(attributes={"big": large_value, "small": "ok"})]
        exporter.export(spans)

        exported_spans = mock_parent_export.call_args[0][0]
        span = exported_spans[0]
        assert len(span._attributes["big"]) < len(large_value)
        assert "...[see Cloud Logging]" in span._attributes["big"]
        assert span._attributes["small"] == "ok"


class TestProjectIdDetection:
    @patch("src.monitoring.cloud_trace_logging_exporter.CloudTraceSpanExporter.__init__")
    @patch("src.monitoring.cloud_trace_logging_exporter.google_cloud_logging")
    def test_uses_constructor_project_id(self, mock_gcl, mock_parent_init) -> None:
        mock_parent_init.return_value = None
        mock_logging_client = MagicMock()

        from src.monitoring.cloud_trace_logging_exporter import CloudTraceLoggingSpanExporter

        exporter = CloudTraceLoggingSpanExporter(
            project_id="explicit-project",
            logging_client=mock_logging_client,
        )

        assert exporter.project_id == "explicit-project"

    @patch("src.monitoring.cloud_trace_logging_exporter.CloudTraceSpanExporter.__init__")
    @patch("src.monitoring.cloud_trace_logging_exporter.google_cloud_logging")
    def test_falls_back_to_env_var(self, mock_gcl, mock_parent_init) -> None:
        mock_parent_init.return_value = None
        mock_logging_client = MagicMock()

        from src.monitoring.cloud_trace_logging_exporter import CloudTraceLoggingSpanExporter

        with patch.dict("os.environ", {"GOOGLE_CLOUD_PROJECT": "env-project"}):
            exporter = CloudTraceLoggingSpanExporter(
                logging_client=mock_logging_client,
            )

        assert exporter.project_id == "env-project"


class TestMultipleSpans:
    @patch(
        "src.monitoring.cloud_trace_logging_exporter.CloudTraceSpanExporter.__init__",
        return_value=None,
    )
    @patch("src.monitoring.cloud_trace_logging_exporter.CloudTraceSpanExporter.export")
    @patch("src.monitoring.cloud_trace_logging_exporter.google_cloud_logging")
    def test_only_logs_spans_with_large_attributes(
        self, mock_gcl, mock_parent_export, _mock_init
    ) -> None:
        mock_parent_export.return_value = SpanExportResult.SUCCESS
        mock_logging_client = MagicMock()
        mock_logger = MagicMock()
        mock_logging_client.logger.return_value = mock_logger

        from src.monitoring.cloud_trace_logging_exporter import CloudTraceLoggingSpanExporter

        exporter = CloudTraceLoggingSpanExporter(
            project_id="test-project",
            logging_client=mock_logging_client,
            max_attribute_length=10,
        )

        spans = [
            _make_span(name="small-span", attributes={"key": "val"}),
            _make_span(name="big-span", attributes={"key": "a" * 50}),
            _make_span(name="another-small", attributes={"k": "v"}),
        ]
        exporter.export(spans)

        assert mock_logger.log_struct.call_count == 1


class TestLoggingFailureDoesNotBlockExport:
    @patch(
        "src.monitoring.cloud_trace_logging_exporter.CloudTraceSpanExporter.__init__",
        return_value=None,
    )
    @patch("src.monitoring.cloud_trace_logging_exporter.CloudTraceSpanExporter.export")
    @patch("src.monitoring.cloud_trace_logging_exporter.google_cloud_logging")
    def test_export_succeeds_even_if_logging_fails(
        self, mock_gcl, mock_parent_export, _mock_init
    ) -> None:
        mock_parent_export.return_value = SpanExportResult.SUCCESS
        mock_logging_client = MagicMock()
        mock_logger = MagicMock()
        mock_logger.log_struct.side_effect = Exception("Cloud Logging unavailable")
        mock_logging_client.logger.return_value = mock_logger

        from src.monitoring.cloud_trace_logging_exporter import CloudTraceLoggingSpanExporter

        exporter = CloudTraceLoggingSpanExporter(
            project_id="test-project",
            logging_client=mock_logging_client,
            max_attribute_length=10,
        )

        spans = [_make_span(attributes={"big": "a" * 50})]
        result = exporter.export(spans)

        assert result == SpanExportResult.SUCCESS
        mock_parent_export.assert_called_once()

    @patch(
        "src.monitoring.cloud_trace_logging_exporter.CloudTraceSpanExporter.__init__",
        return_value=None,
    )
    @patch("src.monitoring.cloud_trace_logging_exporter.CloudTraceSpanExporter.export")
    @patch("src.monitoring.cloud_trace_logging_exporter.google_cloud_logging")
    def test_attributes_preserved_when_logging_fails(
        self, mock_gcl, mock_parent_export, _mock_init
    ) -> None:
        mock_parent_export.return_value = SpanExportResult.SUCCESS
        mock_logging_client = MagicMock()
        mock_logger = MagicMock()
        mock_logger.log_struct.side_effect = Exception("Cloud Logging unavailable")
        mock_logging_client.logger.return_value = mock_logger

        from src.monitoring.cloud_trace_logging_exporter import CloudTraceLoggingSpanExporter

        exporter = CloudTraceLoggingSpanExporter(
            project_id="test-project",
            logging_client=mock_logging_client,
            max_attribute_length=10,
        )

        original_value = "a" * 50
        spans = [_make_span(attributes={"big": original_value, "small": "ok"})]
        exporter.export(spans)

        exported_spans = mock_parent_export.call_args[0][0]
        span = exported_spans[0]
        assert span._attributes["big"] == original_value
        assert span._attributes["small"] == "ok"
        assert "cloud_logging_url" not in span._attributes


class TestCopyOnWrite:
    @patch(
        "src.monitoring.cloud_trace_logging_exporter.CloudTraceSpanExporter.__init__",
        return_value=None,
    )
    @patch("src.monitoring.cloud_trace_logging_exporter.CloudTraceSpanExporter.export")
    @patch("src.monitoring.cloud_trace_logging_exporter.google_cloud_logging")
    def test_original_bounded_attributes_not_mutated(
        self, mock_gcl, mock_parent_export, _mock_init
    ) -> None:
        mock_parent_export.return_value = SpanExportResult.SUCCESS
        mock_logging_client = MagicMock()
        mock_logger = MagicMock()
        mock_logging_client.logger.return_value = mock_logger

        from src.monitoring.cloud_trace_logging_exporter import CloudTraceLoggingSpanExporter

        exporter = CloudTraceLoggingSpanExporter(
            project_id="test-project",
            logging_client=mock_logging_client,
            max_attribute_length=10,
        )

        large_value = "x" * 50
        span = _make_span(attributes={"big": large_value, "small": "ok"})
        original_attrs = span._attributes

        exporter.export([span])

        assert isinstance(original_attrs, BoundedAttributes)
        assert dict(original_attrs) == {"big": large_value, "small": "ok"}
        assert span._attributes is not original_attrs
        assert isinstance(span._attributes, dict)
        assert "cloud_logging_url" in span._attributes
        assert "...[see Cloud Logging]" in span._attributes["big"]

    @patch(
        "src.monitoring.cloud_trace_logging_exporter.CloudTraceSpanExporter.__init__",
        return_value=None,
    )
    @patch("src.monitoring.cloud_trace_logging_exporter.CloudTraceSpanExporter.export")
    @patch("src.monitoring.cloud_trace_logging_exporter.google_cloud_logging")
    def test_attributes_replaced_with_dict_on_success(
        self, mock_gcl, mock_parent_export, _mock_init
    ) -> None:
        mock_parent_export.return_value = SpanExportResult.SUCCESS
        mock_logging_client = MagicMock()
        mock_logger = MagicMock()
        mock_logging_client.logger.return_value = mock_logger

        from src.monitoring.cloud_trace_logging_exporter import CloudTraceLoggingSpanExporter

        exporter = CloudTraceLoggingSpanExporter(
            project_id="test-project",
            logging_client=mock_logging_client,
            max_attribute_length=10,
        )

        span = _make_span(attributes={"big": "a" * 20, "small": "ok"})
        exporter.export([span])

        assert isinstance(span._attributes, dict)
        assert span._attributes["small"] == "ok"


class TestNonStringLargeAttributes:
    @patch(
        "src.monitoring.cloud_trace_logging_exporter.CloudTraceSpanExporter.__init__",
        return_value=None,
    )
    @patch("src.monitoring.cloud_trace_logging_exporter.CloudTraceSpanExporter.export")
    @patch("src.monitoring.cloud_trace_logging_exporter.google_cloud_logging")
    def test_non_string_attributes_are_not_logged(
        self, mock_gcl, mock_parent_export, _mock_init
    ) -> None:
        mock_parent_export.return_value = SpanExportResult.SUCCESS
        mock_logging_client = MagicMock()
        mock_logger = MagicMock()
        mock_logging_client.logger.return_value = mock_logger

        from src.monitoring.cloud_trace_logging_exporter import CloudTraceLoggingSpanExporter

        exporter = CloudTraceLoggingSpanExporter(
            project_id="test-project",
            logging_client=mock_logging_client,
            max_attribute_length=10,
        )

        spans = [
            _make_span(
                attributes={
                    "tuple_attr": tuple(range(100)),
                    "int_attr": 999999999999,
                    "float_attr": 3.14159265358979323846,
                    "bool_attr": True,
                }
            )
        ]
        exporter.export(spans)

        mock_logger.log_struct.assert_not_called()


class TestShutdown:
    @patch(
        "src.monitoring.cloud_trace_logging_exporter.CloudTraceSpanExporter.__init__",
        return_value=None,
    )
    @patch("src.monitoring.cloud_trace_logging_exporter.CloudTraceSpanExporter.shutdown")
    @patch("src.monitoring.cloud_trace_logging_exporter.google_cloud_logging")
    def test_shutdown_closes_logging_client(
        self, mock_gcl, mock_parent_shutdown, _mock_init
    ) -> None:
        mock_logging_client = MagicMock()

        from src.monitoring.cloud_trace_logging_exporter import CloudTraceLoggingSpanExporter

        exporter = CloudTraceLoggingSpanExporter(
            project_id="test-project",
            logging_client=mock_logging_client,
        )

        exporter.shutdown()

        mock_parent_shutdown.assert_called_once()
        mock_logging_client.close.assert_called_once()
