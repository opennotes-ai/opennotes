import logging

from src.monitoring.tracing import TracingManager


class TestTracingManagerSecurity:
    def test_otlp_insecure_defaults_to_false(self):
        tm = TracingManager(
            service_name="test",
            service_version="1.0.0",
            environment="production",
            otlp_endpoint="https://tempo.production:4317",
        )
        assert tm.otlp_insecure is False

    def test_otlp_insecure_can_be_enabled(self):
        tm = TracingManager(
            service_name="test",
            service_version="1.0.0",
            environment="development",
            otlp_endpoint="http://localhost:4317",
            otlp_insecure=True,
        )
        assert tm.otlp_insecure is True

    def test_otlp_insecure_explicitly_disabled(self):
        tm = TracingManager(
            service_name="test",
            service_version="1.0.0",
            environment="development",
            otlp_endpoint="https://tempo.dev:4317",
            otlp_insecure=False,
        )
        assert tm.otlp_insecure is False

    def test_production_with_secure_connection(self):
        tm = TracingManager(
            service_name="production-service",
            service_version="1.0.0",
            environment="production",
            otlp_endpoint="https://tempo.production:4317",
            otlp_insecure=False,
        )
        assert tm.environment == "production"
        assert tm.otlp_insecure is False

    def test_development_with_insecure_connection(self):
        tm = TracingManager(
            service_name="dev-service",
            service_version="1.0.0",
            environment="development",
            otlp_endpoint="http://localhost:4317",
            otlp_insecure=True,
        )
        assert tm.environment == "development"
        assert tm.otlp_insecure is True

    def test_tracing_manager_initialization_parameters(self):
        tm = TracingManager(
            service_name="test-service",
            service_version="1.0.0",
            environment="staging",
            otlp_endpoint="http://tempo:4317",
            otlp_insecure=True,
            enable_console_export=True,
        )

        assert tm.service_name == "test-service"
        assert tm.service_version == "1.0.0"
        assert tm.environment == "staging"
        assert tm.otlp_endpoint == "http://tempo:4317"
        assert tm.otlp_insecure is True
        assert tm.enable_console_export is True


class TestTracingManagerHeaders:
    def test_otlp_headers_defaults_to_none(self):
        tm = TracingManager(
            service_name="test",
            service_version="1.0.0",
            environment="production",
            otlp_endpoint="https://middleware.io:443",
        )
        assert tm.otlp_headers is None
        assert tm._parse_headers() is None

    def test_otlp_headers_single_header(self):
        tm = TracingManager(
            service_name="test",
            service_version="1.0.0",
            environment="production",
            otlp_endpoint="https://middleware.io:443",
            otlp_headers="authorization=my-api-key",
        )
        assert tm.otlp_headers == "authorization=my-api-key"
        assert tm._parse_headers() == {"authorization": "my-api-key"}

    def test_otlp_headers_multiple_headers(self):
        tm = TracingManager(
            service_name="test",
            service_version="1.0.0",
            environment="production",
            otlp_endpoint="https://middleware.io:443",
            otlp_headers="authorization=key123,x-custom=value",
        )
        headers = tm._parse_headers()
        assert headers == {"authorization": "key123", "x-custom": "value"}

    def test_otlp_headers_with_spaces(self):
        tm = TracingManager(
            service_name="test",
            service_version="1.0.0",
            environment="production",
            otlp_endpoint="https://middleware.io:443",
            otlp_headers=" authorization = my-api-key , x-header = value ",
        )
        headers = tm._parse_headers()
        assert headers == {"authorization": "my-api-key", "x-header": "value"}

    def test_otlp_headers_empty_string(self):
        tm = TracingManager(
            service_name="test",
            service_version="1.0.0",
            environment="production",
            otlp_endpoint="https://middleware.io:443",
            otlp_headers="",
        )
        assert tm._parse_headers() is None

    def test_otlp_headers_value_with_equals(self):
        tm = TracingManager(
            service_name="test",
            service_version="1.0.0",
            environment="production",
            otlp_endpoint="https://middleware.io:443",
            otlp_headers="authorization=key=with=equals",
        )
        headers = tm._parse_headers()
        assert headers == {"authorization": "key=with=equals"}


class TestOtelLogLevel:
    def test_otel_log_level_defaults_to_none(self):
        tm = TracingManager(
            service_name="test",
            service_version="1.0.0",
            environment="production",
        )
        assert tm.otel_log_level is None

    def test_otel_log_level_can_be_set(self):
        tm = TracingManager(
            service_name="test",
            service_version="1.0.0",
            environment="development",
            otel_log_level="DEBUG",
        )
        assert tm.otel_log_level == "DEBUG"

    def test_configure_otel_logging_sets_debug_level(self):
        tm = TracingManager(
            service_name="test",
            service_version="1.0.0",
            environment="development",
            otel_log_level="DEBUG",
        )
        tm._configure_otel_logging()

        otel_logger = logging.getLogger("opentelemetry")
        assert otel_logger.level == logging.DEBUG

    def test_configure_otel_logging_sets_info_level(self):
        tm = TracingManager(
            service_name="test",
            service_version="1.0.0",
            environment="development",
            otel_log_level="INFO",
        )
        tm._configure_otel_logging()

        otel_logger = logging.getLogger("opentelemetry")
        assert otel_logger.level == logging.INFO

    def test_configure_otel_logging_sets_warning_level(self):
        tm = TracingManager(
            service_name="test",
            service_version="1.0.0",
            environment="development",
            otel_log_level="WARNING",
        )
        tm._configure_otel_logging()

        otel_logger = logging.getLogger("opentelemetry")
        assert otel_logger.level == logging.WARNING

    def test_configure_otel_logging_sets_error_level(self):
        tm = TracingManager(
            service_name="test",
            service_version="1.0.0",
            environment="development",
            otel_log_level="ERROR",
        )
        tm._configure_otel_logging()

        otel_logger = logging.getLogger("opentelemetry")
        assert otel_logger.level == logging.ERROR

    def test_configure_otel_logging_case_insensitive(self):
        tm = TracingManager(
            service_name="test",
            service_version="1.0.0",
            environment="development",
            otel_log_level="debug",
        )
        tm._configure_otel_logging()

        otel_logger = logging.getLogger("opentelemetry")
        assert otel_logger.level == logging.DEBUG

    def test_configure_otel_logging_skips_when_none(self):
        original_level = logging.getLogger("opentelemetry").level

        tm = TracingManager(
            service_name="test",
            service_version="1.0.0",
            environment="development",
            otel_log_level=None,
        )
        tm._configure_otel_logging()

        otel_logger = logging.getLogger("opentelemetry")
        assert otel_logger.level == original_level

    def test_configure_otel_logging_invalid_level_warns(self, caplog):
        tm = TracingManager(
            service_name="test",
            service_version="1.0.0",
            environment="development",
            otel_log_level="INVALID",
        )

        with caplog.at_level(logging.WARNING):
            tm._configure_otel_logging()

        assert "Invalid OTEL_LOG_LEVEL" in caplog.text
        assert "INVALID" in caplog.text
