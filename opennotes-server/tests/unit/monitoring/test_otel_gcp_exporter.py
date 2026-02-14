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


class TestIsOtelConfiguredWithCloudRun:
    @patch(GCP_DETECTOR_PATH, return_value=True)
    def test_is_otel_configured_returns_true_on_cloud_run(self, mock_is_gcp) -> None:
        from src.monitoring.otel import is_otel_configured

        with patch.dict("os.environ", {}, clear=False):
            os_env_clean = {
                k: v
                for k, v in __import__("os").environ.items()
                if k not in ("OTEL_EXPORTER_OTLP_ENDPOINT", "OTLP_ENDPOINT")
            }
            with patch.dict("os.environ", os_env_clean, clear=True):
                assert is_otel_configured() is True

    @patch(GCP_DETECTOR_PATH, return_value=False)
    def test_is_otel_configured_returns_false_without_endpoint_or_cloud_run(
        self, mock_is_gcp
    ) -> None:
        from src.monitoring.otel import is_otel_configured

        with patch.dict(
            "os.environ",
            {},
            clear=True,
        ):
            assert is_otel_configured() is False

    def test_is_otel_configured_returns_true_with_otlp_endpoint(self) -> None:
        from src.monitoring.otel import is_otel_configured

        with patch.dict(
            "os.environ",
            {"OTLP_ENDPOINT": "http://tempo:4317"},
            clear=True,
        ):
            assert is_otel_configured() is True


class TestGcpImportFallbackToOtlp:
    @patch(GCP_DETECTOR_PATH, return_value=True)
    def test_gcp_import_failure_falls_back_to_otlp(self, mock_is_gcp) -> None:
        import sys

        from src.monitoring.otel import setup_otel, shutdown_otel

        shutdown_otel(flush_timeout_millis=100)

        saved_module = sys.modules.pop("src.monitoring.cloud_trace_logging_exporter", None)
        sys.modules["src.monitoring.cloud_trace_logging_exporter"] = None  # type: ignore[assignment]

        try:
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
                    use_gcp_exporters=True,
                )

                assert result is True

                from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

                from src.monitoring.otel import _span_exporter

                assert isinstance(_span_exporter, OTLPSpanExporter)
        finally:
            if saved_module is not None:
                sys.modules["src.monitoring.cloud_trace_logging_exporter"] = saved_module
            else:
                sys.modules.pop("src.monitoring.cloud_trace_logging_exporter", None)

        shutdown_otel(flush_timeout_millis=100)


class TestUseGcpExportersToggle:
    @patch(GCP_DETECTOR_PATH, return_value=True)
    def test_use_gcp_exporters_false_forces_otlp_on_cloud_run(self, mock_is_gcp) -> None:
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
                use_gcp_exporters=False,
            )

            assert result is True

            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

            from src.monitoring.otel import _span_exporter

            assert isinstance(_span_exporter, OTLPSpanExporter)

        shutdown_otel(flush_timeout_millis=100)


class TestGetSpanExporter:
    @patch(GCP_DETECTOR_PATH, return_value=False)
    def test_get_span_exporter_works(self, mock_is_gcp) -> None:
        from src.monitoring.otel import get_span_exporter, setup_otel, shutdown_otel

        shutdown_otel(flush_timeout_millis=100)

        setup_otel(
            service_name="test-service",
            otlp_endpoint="http://localhost:4317",
        )

        exporter = get_span_exporter()
        assert exporter is not None

        shutdown_otel(flush_timeout_millis=100)

    @patch(GCP_DETECTOR_PATH, return_value=False)
    def test_get_otlp_exporter_alias_works(self, mock_is_gcp) -> None:
        from src.monitoring.otel import (
            get_otlp_exporter,
            get_span_exporter,
            setup_otel,
            shutdown_otel,
        )

        shutdown_otel(flush_timeout_millis=100)

        setup_otel(
            service_name="test-service",
            otlp_endpoint="http://localhost:4317",
        )

        assert get_otlp_exporter is get_span_exporter
        assert get_otlp_exporter() is get_span_exporter()

        shutdown_otel(flush_timeout_millis=100)

    def test_get_span_exporter_returns_none_when_not_initialized(self) -> None:
        from src.monitoring.otel import get_span_exporter, shutdown_otel

        shutdown_otel(flush_timeout_millis=100)

        exporter = get_span_exporter()
        assert exporter is None
