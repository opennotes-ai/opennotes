from unittest.mock import patch

GCP_DETECTOR_PATH = "src.monitoring.gcp_resource_detector.is_cloud_run_environment"


class TestGcpExporterSelection:
    @patch(GCP_DETECTOR_PATH, return_value=True)
    @patch(
        "src.monitoring.cloud_trace_logging_exporter.CloudTraceSpanExporter.__init__",
        return_value=None,
    )
    @patch("src.monitoring.cloud_trace_logging_exporter.google_cloud_logging")
    def test_uses_cloud_trace_exporter_on_gcp(self, mock_gcl, mock_ct_init, mock_is_gcp) -> None:
        from src.monitoring.otel import setup_otel, shutdown_otel

        shutdown_otel(flush_timeout_millis=100)

        with patch.dict(
            "os.environ",
            {
                "K_SERVICE": "opennotes-server",
                "GOOGLE_CLOUD_PROJECT": "test-project",
            },
            clear=False,
        ):
            result = setup_otel(
                service_name="test-service",
                otlp_endpoint="http://localhost:4317",
            )

            assert result is True

            from src.monitoring.cloud_trace_logging_exporter import (
                CloudTraceLoggingSpanExporter,
            )
            from src.monitoring.otel import _span_exporter

            assert isinstance(_span_exporter, CloudTraceLoggingSpanExporter)

        shutdown_otel(flush_timeout_millis=100)

    @patch(GCP_DETECTOR_PATH, return_value=False)
    def test_uses_otlp_exporter_when_not_on_gcp(self, mock_is_gcp) -> None:
        from src.monitoring.otel import setup_otel, shutdown_otel

        shutdown_otel(flush_timeout_millis=100)

        result = setup_otel(
            service_name="test-service",
            otlp_endpoint="http://localhost:4317",
        )

        assert result is True

        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

        from src.monitoring.otel import _span_exporter

        assert isinstance(_span_exporter, OTLPSpanExporter)

        shutdown_otel(flush_timeout_millis=100)


class TestGetOtlpExporterBackwardCompat:
    @patch(GCP_DETECTOR_PATH, return_value=False)
    def test_get_otlp_exporter_returns_span_exporter(self, mock_is_gcp) -> None:
        from src.monitoring.otel import get_otlp_exporter, setup_otel, shutdown_otel

        shutdown_otel(flush_timeout_millis=100)

        setup_otel(
            service_name="test-service",
            otlp_endpoint="http://localhost:4317",
        )

        exporter = get_otlp_exporter()
        assert exporter is not None

        shutdown_otel(flush_timeout_millis=100)

    def test_get_otlp_exporter_returns_none_when_not_initialized(self) -> None:
        from src.monitoring.otel import get_otlp_exporter, shutdown_otel

        shutdown_otel(flush_timeout_millis=100)

        exporter = get_otlp_exporter()
        assert exporter is None
