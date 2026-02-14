from unittest.mock import MagicMock, patch

GCP_DETECTOR_PATH = "src.monitoring.gcp_resource_detector.is_cloud_run_environment"
TRACELOOP_PATH = "traceloop.sdk.Traceloop"


class TestTraceloopGcpExporters:
    @patch(GCP_DETECTOR_PATH, return_value=True)
    @patch(TRACELOOP_PATH)
    def test_passes_gcp_metrics_exporter_on_cloud_run(
        self, mock_traceloop_cls, mock_is_gcp
    ) -> None:
        import src.monitoring.traceloop as traceloop_mod

        traceloop_mod._traceloop_configured = False

        mock_exporter = MagicMock()
        mock_metrics_cls = MagicMock()
        mock_logging_cls = MagicMock()
        with (
            patch.dict("os.environ", {"K_SERVICE": "test"}, clear=False),
            patch(
                "opentelemetry.exporter.cloud_monitoring.CloudMonitoringMetricsExporter",
                mock_metrics_cls,
            ),
            patch(
                "opentelemetry.exporter.cloud_logging.CloudLoggingExporter",
                mock_logging_cls,
            ),
        ):
            result = traceloop_mod.setup_traceloop(
                app_name="test",
                service_name="test-service",
                version="0.0.1",
                environment="test",
                instance_id="inst-1",
                exporter=mock_exporter,
            )

        assert result is True
        init_kwargs = mock_traceloop_cls.init.call_args[1]
        assert "metrics_exporter" in init_kwargs
        assert init_kwargs["metrics_exporter"] is not None

    @patch(GCP_DETECTOR_PATH, return_value=True)
    @patch(TRACELOOP_PATH)
    def test_passes_gcp_logging_exporter_on_cloud_run(
        self, mock_traceloop_cls, mock_is_gcp
    ) -> None:
        import src.monitoring.traceloop as traceloop_mod

        traceloop_mod._traceloop_configured = False

        mock_exporter = MagicMock()
        mock_metrics_cls = MagicMock()
        mock_logging_cls = MagicMock()
        with (
            patch.dict("os.environ", {"K_SERVICE": "test"}, clear=False),
            patch(
                "opentelemetry.exporter.cloud_monitoring.CloudMonitoringMetricsExporter",
                mock_metrics_cls,
            ),
            patch(
                "opentelemetry.exporter.cloud_logging.CloudLoggingExporter",
                mock_logging_cls,
            ),
        ):
            result = traceloop_mod.setup_traceloop(
                app_name="test",
                service_name="test-service",
                version="0.0.1",
                environment="test",
                instance_id="inst-1",
                exporter=mock_exporter,
            )

        assert result is True
        init_kwargs = mock_traceloop_cls.init.call_args[1]
        assert "logging_exporter" in init_kwargs
        assert init_kwargs["logging_exporter"] is not None

    @patch(GCP_DETECTOR_PATH, return_value=False)
    @patch(TRACELOOP_PATH)
    def test_no_gcp_exporters_when_not_on_cloud_run(self, mock_traceloop_cls, mock_is_gcp) -> None:
        import src.monitoring.traceloop as traceloop_mod

        traceloop_mod._traceloop_configured = False

        mock_exporter = MagicMock()
        result = traceloop_mod.setup_traceloop(
            app_name="test",
            service_name="test-service",
            version="0.0.1",
            environment="test",
            instance_id="inst-1",
            exporter=mock_exporter,
        )

        assert result is True
        init_kwargs = mock_traceloop_cls.init.call_args[1]
        assert "metrics_exporter" not in init_kwargs
        assert "logging_exporter" not in init_kwargs


class TestTraceloopGcpImportError:
    @patch(GCP_DETECTOR_PATH, return_value=True)
    @patch(TRACELOOP_PATH)
    def test_graceful_fallback_on_import_error(self, mock_traceloop_cls, mock_is_gcp) -> None:
        import src.monitoring.traceloop as traceloop_mod

        traceloop_mod._traceloop_configured = False

        mock_exporter = MagicMock()

        with (
            patch.dict("os.environ", {"K_SERVICE": "test"}, clear=False),
            patch.dict(
                "sys.modules",
                {
                    "opentelemetry.exporter.cloud_monitoring": None,
                    "opentelemetry.exporter.cloud_logging": None,
                },
            ),
        ):
            result = traceloop_mod.setup_traceloop(
                app_name="test",
                service_name="test-service",
                version="0.0.1",
                environment="test",
                instance_id="inst-1",
                exporter=mock_exporter,
            )

        assert result is True
        init_kwargs = mock_traceloop_cls.init.call_args[1]
        assert "metrics_exporter" not in init_kwargs
        assert "logging_exporter" not in init_kwargs
