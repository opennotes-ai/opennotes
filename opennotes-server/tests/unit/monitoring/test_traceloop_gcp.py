from unittest.mock import MagicMock, patch

GCP_DETECTOR_PATH = "src.monitoring.gcp_resource_detector.is_cloud_run_environment"
TRACELOOP_PATH = "traceloop.sdk.Traceloop"


class TestTraceloopGcpExporters:
    @patch(GCP_DETECTOR_PATH, return_value=True)
    @patch(TRACELOOP_PATH)
    def test_no_gcp_metrics_exporter_on_cloud_run(self, mock_traceloop_cls, mock_is_gcp) -> None:
        import src.monitoring.traceloop as traceloop_mod

        traceloop_mod._traceloop_configured = False

        mock_logging_cls = MagicMock()
        mock_span_exporter_cls = MagicMock()
        with (
            patch.dict(
                "os.environ",
                {"K_SERVICE": "test", "GOOGLE_CLOUD_PROJECT": "test-project"},
                clear=False,
            ),
            patch(
                "src.monitoring.cloud_trace_logging_exporter.CloudTraceLoggingSpanExporter",
                mock_span_exporter_cls,
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
                otlp_endpoint="http://localhost:4317",
            )

        assert result is True
        init_kwargs = mock_traceloop_cls.init.call_args[1]
        assert "metrics_exporter" not in init_kwargs

    @patch(GCP_DETECTOR_PATH, return_value=True)
    @patch(TRACELOOP_PATH)
    def test_passes_gcp_logging_exporter_on_cloud_run(
        self, mock_traceloop_cls, mock_is_gcp
    ) -> None:
        import src.monitoring.traceloop as traceloop_mod

        traceloop_mod._traceloop_configured = False

        mock_logging_cls = MagicMock()
        mock_span_exporter_cls = MagicMock()
        with (
            patch.dict(
                "os.environ",
                {"K_SERVICE": "test", "GOOGLE_CLOUD_PROJECT": "test-project"},
                clear=False,
            ),
            patch(
                "src.monitoring.cloud_trace_logging_exporter.CloudTraceLoggingSpanExporter",
                mock_span_exporter_cls,
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
                otlp_endpoint="http://localhost:4317",
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

        result = traceloop_mod.setup_traceloop(
            app_name="test",
            service_name="test-service",
            version="0.0.1",
            environment="test",
            instance_id="inst-1",
            otlp_endpoint="http://localhost:4317",
        )

        assert result is True
        init_kwargs = mock_traceloop_cls.init.call_args[1]
        assert "metrics_exporter" not in init_kwargs
        assert "logging_exporter" not in init_kwargs


class TestTraceloopDedicatedExporter:
    @patch(GCP_DETECTOR_PATH, return_value=True)
    @patch(TRACELOOP_PATH)
    @patch(
        "src.monitoring.cloud_trace_logging_exporter.CloudTraceSpanExporter.__init__",
        return_value=None,
    )
    @patch("src.monitoring.cloud_trace_logging_exporter.google_cloud_logging")
    def test_creates_dedicated_gcp_exporter_on_cloud_run(
        self, mock_gcl, mock_ct_init, mock_traceloop_cls, mock_is_gcp
    ) -> None:
        import src.monitoring.traceloop as traceloop_mod

        traceloop_mod._traceloop_configured = False

        mock_logging_cls = MagicMock()
        with (
            patch.dict(
                "os.environ",
                {"K_SERVICE": "test", "GOOGLE_CLOUD_PROJECT": "test-project"},
                clear=False,
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
                otlp_endpoint="http://localhost:4317",
            )

        assert result is True
        init_kwargs = mock_traceloop_cls.init.call_args[1]
        assert "exporter" in init_kwargs

        from src.monitoring.cloud_trace_logging_exporter import CloudTraceLoggingSpanExporter

        assert isinstance(init_kwargs["exporter"], CloudTraceLoggingSpanExporter)

    @patch(GCP_DETECTOR_PATH, return_value=False)
    @patch(TRACELOOP_PATH)
    def test_uses_api_endpoint_when_not_on_gcp(self, mock_traceloop_cls, mock_is_gcp) -> None:
        import src.monitoring.traceloop as traceloop_mod

        traceloop_mod._traceloop_configured = False

        result = traceloop_mod.setup_traceloop(
            app_name="test",
            service_name="test-service",
            version="0.0.1",
            environment="test",
            instance_id="inst-1",
            otlp_endpoint="http://localhost:4317",
        )

        assert result is True
        init_kwargs = mock_traceloop_cls.init.call_args[1]
        assert "exporter" not in init_kwargs
        assert init_kwargs["api_endpoint"] == "http://localhost:4317"


class TestTraceloopInstrumentsAllowlist:
    @patch(GCP_DETECTOR_PATH, return_value=False)
    @patch(TRACELOOP_PATH)
    def test_uses_llm_only_instruments_allowlist(self, mock_traceloop_cls, mock_is_gcp) -> None:
        import src.monitoring.traceloop as traceloop_mod

        traceloop_mod._traceloop_configured = False

        traceloop_mod.setup_traceloop(
            app_name="test",
            service_name="test-service",
            version="0.0.1",
            environment="test",
            instance_id="inst-1",
            otlp_endpoint="http://localhost:4317",
        )

        init_kwargs = mock_traceloop_cls.init.call_args[1]
        from traceloop.sdk.instruments import Instruments

        assert "instruments" in init_kwargs
        assert "block_instruments" not in init_kwargs
        assert init_kwargs["instruments"] == {
            Instruments.ANTHROPIC,
            Instruments.OPENAI,
            Instruments.VERTEXAI,
        }


class TestTraceloopInstrumentsUnavailable:
    @patch(GCP_DETECTOR_PATH, return_value=False)
    @patch(TRACELOOP_PATH)
    def test_setup_succeeds_when_instruments_enum_unavailable(
        self, mock_traceloop_cls, mock_is_gcp
    ) -> None:
        import src.monitoring.traceloop as traceloop_mod

        traceloop_mod._traceloop_configured = False

        original_import = (
            __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__
        )

        def patched_import(name, *args, **kwargs):
            if name == "traceloop.sdk.instruments":
                raise AttributeError("Instruments enum unavailable")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=patched_import):
            result = traceloop_mod.setup_traceloop(
                app_name="test",
                service_name="test-service",
                version="0.0.1",
                environment="test",
                instance_id="inst-1",
                otlp_endpoint="http://localhost:4317",
            )

        assert result is True
        init_kwargs = mock_traceloop_cls.init.call_args[1]
        assert "instruments" not in init_kwargs


class TestTraceloopGcpImportError:
    @patch(GCP_DETECTOR_PATH, return_value=True)
    @patch(TRACELOOP_PATH)
    def test_graceful_fallback_on_import_error(self, mock_traceloop_cls, mock_is_gcp) -> None:
        import src.monitoring.traceloop as traceloop_mod

        traceloop_mod._traceloop_configured = False

        mock_span_exporter_cls = MagicMock()
        with (
            patch.dict(
                "os.environ",
                {"K_SERVICE": "test", "GOOGLE_CLOUD_PROJECT": "test-project"},
                clear=False,
            ),
            patch(
                "src.monitoring.cloud_trace_logging_exporter.CloudTraceLoggingSpanExporter",
                mock_span_exporter_cls,
            ),
            patch.dict(
                "sys.modules",
                {
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
                otlp_endpoint="http://localhost:4317",
            )

        assert result is True
        init_kwargs = mock_traceloop_cls.init.call_args[1]
        assert "metrics_exporter" not in init_kwargs
        assert "logging_exporter" not in init_kwargs


class TestTraceloopNoExporterParam:
    @patch(GCP_DETECTOR_PATH, return_value=False)
    @patch(TRACELOOP_PATH)
    def test_setup_without_endpoint_returns_false(self, mock_traceloop_cls, mock_is_gcp) -> None:
        import src.monitoring.traceloop as traceloop_mod

        traceloop_mod._traceloop_configured = False

        result = traceloop_mod.setup_traceloop(
            app_name="test",
            service_name="test-service",
            version="0.0.1",
            environment="test",
            instance_id="inst-1",
        )

        assert result is False
