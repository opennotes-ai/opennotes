from unittest.mock import patch

GCP_DETECTOR_PATH = "src.monitoring.gcp_resource_detector.is_cloud_run_environment"
TRACELOOP_PATH = "traceloop.sdk.Traceloop"


class TestShutdownTraceloop:
    def test_resets_traceloop_configured_flag(self):
        import src.monitoring.traceloop as traceloop_mod

        traceloop_mod._traceloop_configured = True
        traceloop_mod.shutdown_traceloop()
        assert traceloop_mod._traceloop_configured is False

    def test_cleans_trace_content_env_var(self):
        import os

        import src.monitoring.traceloop as traceloop_mod

        os.environ["TRACELOOP_TRACE_CONTENT"] = "true"
        traceloop_mod._traceloop_configured = True
        traceloop_mod.shutdown_traceloop()
        assert "TRACELOOP_TRACE_CONTENT" not in os.environ

    def test_idempotent_when_not_configured(self):
        import src.monitoring.traceloop as traceloop_mod

        traceloop_mod._traceloop_configured = False
        traceloop_mod.shutdown_traceloop()
        assert traceloop_mod._traceloop_configured is False

    def test_thread_safety_of_configured_flag(self):
        import threading

        import src.monitoring.traceloop as traceloop_mod

        assert hasattr(traceloop_mod, "_traceloop_lock")
        assert isinstance(traceloop_mod._traceloop_lock, type(threading.Lock()))


class TestShutdownMonitoring:
    @patch(GCP_DETECTOR_PATH, return_value=False)
    def test_calls_both_shutdown_functions(self, mock_is_gcp):
        from src.monitoring import shutdown_monitoring

        with (
            patch("src.monitoring.shutdown_otel") as mock_shutdown_otel,
            patch("src.monitoring.shutdown_traceloop") as mock_shutdown_traceloop,
        ):
            shutdown_monitoring(flush_timeout_millis=100)
            mock_shutdown_otel.assert_called_once_with(flush_timeout_millis=100)
            mock_shutdown_traceloop.assert_called_once()

    def test_exported_from_monitoring_init(self):
        from src.monitoring import __all__

        assert "shutdown_monitoring" in __all__

    @patch(GCP_DETECTOR_PATH, return_value=False)
    def test_passes_default_flush_timeout(self, mock_is_gcp):
        from src.monitoring import shutdown_monitoring

        with (
            patch("src.monitoring.shutdown_otel") as mock_shutdown_otel,
            patch("src.monitoring.shutdown_traceloop"),
        ):
            shutdown_monitoring()
            mock_shutdown_otel.assert_called_once_with(flush_timeout_millis=None)
