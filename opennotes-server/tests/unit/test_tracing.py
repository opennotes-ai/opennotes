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
