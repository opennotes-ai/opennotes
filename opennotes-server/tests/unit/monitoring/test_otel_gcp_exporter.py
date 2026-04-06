from unittest.mock import patch

GCP_DETECTOR_PATH = "src.monitoring.gcp_resource_detector.is_cloud_run_environment"


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
