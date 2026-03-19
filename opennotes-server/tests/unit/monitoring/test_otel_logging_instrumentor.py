from unittest.mock import MagicMock, patch

LOGGING_INSTRUMENTOR_PATH = "opentelemetry.instrumentation.logging.LoggingInstrumentor"


class TestLoggingInstrumentorInSetupOtel:
    def _reset_otel(self):
        import src.monitoring.otel as otel_mod

        otel_mod._otel_initialized = False
        otel_mod._tracer_provider = None
        otel_mod._span_exporter = None
        otel_mod._meter_provider = None

    def test_setup_otel_calls_logging_instrumentor(self) -> None:
        self._reset_otel()

        mock_logging_instrumentor = MagicMock()
        mock_logging_instrumentor.is_instrumented_by_opentelemetry = False
        mock_logging_cls = MagicMock(return_value=mock_logging_instrumentor)

        with patch(LOGGING_INSTRUMENTOR_PATH, mock_logging_cls):
            from src.monitoring.otel import setup_otel

            setup_otel(
                service_name="test",
                service_version="0.0.1",
                environment="test",
                sample_rate=1.0,
            )

        mock_logging_cls.assert_called_once()
        mock_logging_instrumentor.instrument.assert_called_once_with(set_logging_format=False)
        self._reset_otel()

    def test_setup_otel_skips_logging_instrumentor_when_already_initialized(self) -> None:
        import src.monitoring.otel as otel_mod

        otel_mod._otel_initialized = True

        mock_logging_cls = MagicMock()
        with patch(LOGGING_INSTRUMENTOR_PATH, mock_logging_cls):
            from src.monitoring.otel import setup_otel

            result = setup_otel(
                service_name="test",
                service_version="0.0.1",
                environment="test",
            )

        assert result is True
        mock_logging_cls.assert_not_called()
        self._reset_otel()
