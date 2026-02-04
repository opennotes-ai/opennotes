"""Unit tests for DBOS configuration module.

Tests cover:
- Config construction from settings
- Singleton pattern (get_dbos, reset_dbos)
- URL format conversion (async to sync)
- Schema isolation configuration
- OTLP configuration for GCP observability
"""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.config import get_settings
from src.dbos_workflows.config import (
    _derive_http_otlp_endpoint,
    create_dbos_instance,
    destroy_dbos,
    get_dbos,
    get_dbos_client,
    get_dbos_config,
    reset_dbos,
    reset_dbos_client,
    validate_dbos_connection,
)

pytestmark = pytest.mark.unit

TEST_CREDENTIALS_ENCRYPTION_KEY = "WSaz4Oan5Rx-0zD-6wC7yOfasrJmzZDVViu6WzwSi0Q="
TEST_ENCRYPTION_MASTER_KEY = "F5UG5HjhMjOgapb3ADail98bpydyrnrFfgkH1YB_zuE="
VALID_JWT_KEY = "a" * 32
TEST_DATABASE_URL = "postgresql+asyncpg://user:pass@localhost:5432/testdb"


@pytest.fixture(autouse=True)
def reset_settings_cache():
    """Reset settings singleton between tests to avoid state leakage."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def get_base_env() -> dict[str, str]:
    """Return base environment variables required for valid settings."""
    return {
        "JWT_SECRET_KEY": VALID_JWT_KEY,
        "CREDENTIALS_ENCRYPTION_KEY": TEST_CREDENTIALS_ENCRYPTION_KEY,
        "ENCRYPTION_MASTER_KEY": TEST_ENCRYPTION_MASTER_KEY,
        "DATABASE_URL": TEST_DATABASE_URL,
        "ENVIRONMENT": "development",
    }


class TestDeriveHttpOtlpEndpoint:
    """Tests for _derive_http_otlp_endpoint() function."""

    def test_returns_none_for_empty_endpoint(self) -> None:
        """Returns None when endpoint is empty or None."""
        assert _derive_http_otlp_endpoint(None) is None
        assert _derive_http_otlp_endpoint("") is None

    def test_converts_grpc_port_to_http_port(self) -> None:
        """Converts gRPC port 4317 to HTTP port 4318."""
        result = _derive_http_otlp_endpoint("http://tempo:4317")
        assert result == "http://tempo:4318"

    def test_converts_localhost_grpc_to_http(self) -> None:
        """Converts localhost gRPC endpoint to HTTP."""
        result = _derive_http_otlp_endpoint("http://localhost:4317")
        assert result == "http://localhost:4318"

    def test_preserves_https_endpoints(self) -> None:
        """Preserves HTTPS endpoints with non-4317 ports."""
        result = _derive_http_otlp_endpoint("https://otel-collector:443")
        assert result == "https://otel-collector:443"

    def test_strips_trailing_slash(self) -> None:
        """Strips trailing slash from endpoint."""
        result = _derive_http_otlp_endpoint("http://tempo:4317/")
        assert result == "http://tempo:4318"

    def test_handles_ipv4_address(self) -> None:
        """Handles IPv4 address endpoints."""
        result = _derive_http_otlp_endpoint("http://10.0.0.1:4317")
        assert result == "http://10.0.0.1:4318"

    def test_preserves_hostname_containing_4317(self) -> None:
        """Does not corrupt hostnames containing '4317'."""
        result = _derive_http_otlp_endpoint("http://host4317.example.com:4317")
        assert result == "http://host4317.example.com:4318"

        result = _derive_http_otlp_endpoint("http://otel4317collector:4317")
        assert result == "http://otel4317collector:4318"

    def test_preserves_hostname_containing_4317_with_different_port(self) -> None:
        """Preserves hostname with '4317' when port is not 4317."""
        result = _derive_http_otlp_endpoint("http://host4317.example.com:443")
        assert result == "http://host4317.example.com:443"

    def test_strips_path_from_url(self) -> None:
        """Strips path components to return base URL only."""
        result = _derive_http_otlp_endpoint("http://tempo:4317/v1/traces")
        assert result == "http://tempo:4318"

    def test_handles_url_with_credentials(self) -> None:
        """Handles URLs with username and password."""
        result = _derive_http_otlp_endpoint("http://user:pass@tempo:4317")
        assert result == "http://user:pass@tempo:4318"

    def test_handles_url_with_username_only(self) -> None:
        """Handles URLs with username but no password."""
        result = _derive_http_otlp_endpoint("http://user@tempo:4317")
        assert result == "http://user@tempo:4318"

    def test_handles_ipv6_address(self) -> None:
        """Handles IPv6 address endpoints."""
        result = _derive_http_otlp_endpoint("http://[::1]:4317")
        assert result == "http://[::1]:4318"

    def test_strips_query_string(self) -> None:
        """Strips query string to return base URL only."""
        result = _derive_http_otlp_endpoint("http://tempo:4317?timeout=30")
        assert result == "http://tempo:4318"


class TestGetDbosConfig:
    """Tests for get_dbos_config() function."""

    def test_returns_valid_config_dict(self) -> None:
        """Config dict includes required DBOS fields."""
        with patch("src.dbos_workflows.config.settings") as mock_settings:
            mock_settings.DATABASE_URL = TEST_DATABASE_URL
            mock_settings.OTEL_SERVICE_NAME = "test-service"
            mock_settings.PROJECT_NAME = "Test Project"
            mock_settings.OTLP_ENDPOINT = None
            mock_settings.DBOS_CONDUCTOR_KEY = None

            config: dict[str, Any] = dict(get_dbos_config())

            assert isinstance(config, dict)
            assert "name" in config
            assert "system_database_url" in config

    def test_converts_asyncpg_url_to_sync(self) -> None:
        """Async PostgreSQL URL is converted to sync format for DBOS."""
        with patch("src.dbos_workflows.config.settings") as mock_settings:
            mock_settings.DATABASE_URL = "postgresql+asyncpg://user:pass@host:5432/db"
            mock_settings.OTEL_SERVICE_NAME = "test-service"
            mock_settings.PROJECT_NAME = None
            mock_settings.OTLP_ENDPOINT = None
            mock_settings.DBOS_CONDUCTOR_KEY = None

            config: dict[str, Any] = dict(get_dbos_config())
            db_url = config.get("system_database_url", "")

            assert "postgresql+asyncpg://" not in db_url
            assert "postgresql://" in db_url
            assert db_url == "postgresql://user:pass@host:5432/db"

    def test_app_name_uses_otel_service_name_when_set(self) -> None:
        """Config uses OTEL_SERVICE_NAME when explicitly set."""
        with patch("src.dbos_workflows.config.settings") as mock_settings:
            mock_settings.DATABASE_URL = TEST_DATABASE_URL
            mock_settings.OTEL_SERVICE_NAME = "custom-otel-name"
            mock_settings.PROJECT_NAME = "Open Notes Server"
            mock_settings.OTLP_ENDPOINT = None
            mock_settings.DBOS_CONDUCTOR_KEY = None

            result = dict(get_dbos_config())

            assert result.get("name") == "custom-otel-name"

    def test_app_name_falls_back_to_project_name(self) -> None:
        """Config falls back to PROJECT_NAME when OTEL_SERVICE_NAME is not set."""
        with patch("src.dbos_workflows.config.settings") as mock_settings:
            mock_settings.DATABASE_URL = TEST_DATABASE_URL
            mock_settings.OTEL_SERVICE_NAME = None
            mock_settings.PROJECT_NAME = "Open Notes Server"
            mock_settings.OTLP_ENDPOINT = None
            mock_settings.DBOS_CONDUCTOR_KEY = None

            result = dict(get_dbos_config())

            assert result.get("name") == "Open Notes Server"

    def test_app_name_falls_back_to_default_when_both_unset(self) -> None:
        """Config uses default 'opennotes-server' when both OTEL_SERVICE_NAME and PROJECT_NAME are None."""
        with patch("src.dbos_workflows.config.settings") as mock_settings:
            mock_settings.DATABASE_URL = TEST_DATABASE_URL
            mock_settings.OTEL_SERVICE_NAME = None
            mock_settings.PROJECT_NAME = None
            mock_settings.OTLP_ENDPOINT = None
            mock_settings.DBOS_CONDUCTOR_KEY = None

            result = dict(get_dbos_config())

            assert result.get("name") == "opennotes-server"

    def test_raises_if_database_url_missing(self) -> None:
        """Raises ValueError if DATABASE_URL is not configured."""
        with patch("src.dbos_workflows.config.settings") as mock_settings:
            mock_settings.DATABASE_URL = None

            with pytest.raises(ValueError, match="DATABASE_URL"):
                get_dbos_config()

    def test_raises_if_database_url_empty(self) -> None:
        """Raises ValueError if DATABASE_URL is empty string."""
        with patch("src.dbos_workflows.config.settings") as mock_settings:
            mock_settings.DATABASE_URL = ""

            with pytest.raises(ValueError, match="DATABASE_URL"):
                get_dbos_config()

    def test_includes_otlp_config_when_endpoint_set(self) -> None:
        """Config includes OTLP settings when OTLP_ENDPOINT is configured."""
        with patch("src.dbos_workflows.config.settings") as mock_settings:
            mock_settings.DATABASE_URL = TEST_DATABASE_URL
            mock_settings.OTLP_ENDPOINT = "http://tempo:4317"
            mock_settings.OTEL_SERVICE_NAME = "opennotes-server"
            mock_settings.PROJECT_NAME = "Open Notes Server"
            mock_settings.DBOS_CONDUCTOR_KEY = None

            config: dict[str, Any] = dict(get_dbos_config())

            assert "disable_otlp" not in config
            assert config["otlp_traces_endpoints"] == ["http://tempo:4318/v1/traces"]
            assert config["otlp_logs_endpoints"] == ["http://tempo:4318/v1/logs"]

    def test_disables_otlp_when_no_endpoint(self) -> None:
        """Config disables OTLP when OTLP_ENDPOINT is not set."""
        with patch("src.dbos_workflows.config.settings") as mock_settings:
            mock_settings.DATABASE_URL = TEST_DATABASE_URL
            mock_settings.OTLP_ENDPOINT = None
            mock_settings.OTEL_SERVICE_NAME = None
            mock_settings.PROJECT_NAME = "Open Notes Server"
            mock_settings.DBOS_CONDUCTOR_KEY = None

            config: dict[str, Any] = dict(get_dbos_config())

            assert config["disable_otlp"] is True
            assert "otlp_traces_endpoints" not in config
            assert "otlp_logs_endpoints" not in config

    def test_config_does_not_include_conductor_key(self) -> None:
        with patch("src.dbos_workflows.config.settings") as mock_settings:
            mock_settings.DATABASE_URL = TEST_DATABASE_URL
            mock_settings.OTEL_SERVICE_NAME = "test-service"
            mock_settings.PROJECT_NAME = "Test Project"
            mock_settings.OTLP_ENDPOINT = None
            mock_settings.DBOS_CONDUCTOR_KEY = "test-conductor-api-key-123"

            config: dict[str, Any] = dict(get_dbos_config())

            assert "conductor_key" not in config


class TestDbosInstance:
    """Tests for DBOS singleton management."""

    def test_get_dbos_returns_dbos_instance(self) -> None:
        """get_dbos() returns a DBOS instance."""
        with patch("src.dbos_workflows.config.DBOS") as mock_dbos_class:
            mock_instance = MagicMock()
            mock_dbos_class.return_value = mock_instance

            reset_dbos()
            result = get_dbos()

            assert result == mock_instance
            mock_dbos_class.assert_called_once()

    def test_get_dbos_returns_same_instance(self) -> None:
        """Subsequent calls return the same singleton instance."""
        with patch("src.dbos_workflows.config.DBOS") as mock_dbos_class:
            mock_instance = MagicMock()
            mock_dbos_class.return_value = mock_instance

            reset_dbos()
            first = get_dbos()
            second = get_dbos()

            assert first is second
            assert mock_dbos_class.call_count == 1

    def test_reset_dbos_clears_instance(self) -> None:
        """reset_dbos() clears the cached instance."""
        with patch("src.dbos_workflows.config.DBOS") as mock_dbos_class:
            mock_instance_1 = MagicMock()
            mock_instance_2 = MagicMock()
            mock_dbos_class.side_effect = [mock_instance_1, mock_instance_2]

            reset_dbos()
            first = get_dbos()
            reset_dbos()
            second = get_dbos()

            assert first is not second
            assert mock_dbos_class.call_count == 2

    def test_create_dbos_instance_passes_config(self) -> None:
        """create_dbos_instance() passes config dict to DBOS constructor."""
        with (
            patch("src.dbos_workflows.config.DBOS") as mock_dbos_class,
            patch("src.dbos_workflows.config.get_dbos_config") as mock_get_config,
            patch("src.dbos_workflows.config.settings") as mock_settings,
        ):
            mock_config: dict[str, Any] = {
                "name": "test",
                "system_database_url": "postgresql://",
            }
            mock_get_config.return_value = mock_config
            mock_settings.DBOS_CONDUCTOR_KEY = None

            create_dbos_instance()

            mock_dbos_class.assert_called_once_with(config=mock_config)

    def test_create_dbos_instance_passes_conductor_key(self) -> None:
        """create_dbos_instance() passes conductor_key to DBOS constructor when set."""
        with (
            patch("src.dbos_workflows.config.DBOS") as mock_dbos_class,
            patch("src.dbos_workflows.config.get_dbos_config") as mock_get_config,
            patch("src.dbos_workflows.config.settings") as mock_settings,
        ):
            mock_config: dict[str, Any] = {
                "name": "test",
                "system_database_url": "postgresql://",
            }
            mock_get_config.return_value = mock_config
            mock_settings.DBOS_CONDUCTOR_KEY = "test-key-123"

            create_dbos_instance()

            mock_dbos_class.assert_called_once_with(
                config=mock_config, conductor_key="test-key-123"
            )

    def test_create_dbos_instance_omits_conductor_key_when_empty(self) -> None:
        """create_dbos_instance() omits conductor_key when empty string."""
        with (
            patch("src.dbos_workflows.config.DBOS") as mock_dbos_class,
            patch("src.dbos_workflows.config.get_dbos_config") as mock_get_config,
            patch("src.dbos_workflows.config.settings") as mock_settings,
        ):
            mock_config: dict[str, Any] = {
                "name": "test",
                "system_database_url": "postgresql://",
            }
            mock_get_config.return_value = mock_config
            mock_settings.DBOS_CONDUCTOR_KEY = ""

            create_dbos_instance()

            mock_dbos_class.assert_called_once_with(config=mock_config)

    def test_destroy_dbos_calls_dbos_destroy(self) -> None:
        """destroy_dbos() calls DBOS.destroy() with timeout."""
        with patch("src.dbos_workflows.config.DBOS") as mock_dbos_class:
            mock_instance = MagicMock()
            mock_dbos_class.return_value = mock_instance

            reset_dbos()
            get_dbos()
            destroy_dbos(workflow_completion_timeout_sec=10)

            mock_dbos_class.destroy.assert_called_once_with(
                workflow_completion_timeout_sec=10,
                destroy_registry=False,
            )

    def test_destroy_dbos_clears_instance(self) -> None:
        """destroy_dbos() clears the cached instance after destroying."""
        with patch("src.dbos_workflows.config.DBOS") as mock_dbos_class:
            mock_instance_1 = MagicMock()
            mock_instance_2 = MagicMock()
            mock_dbos_class.side_effect = [mock_instance_1, mock_instance_2]

            reset_dbos()
            get_dbos()
            destroy_dbos()
            second = get_dbos()

            assert second is mock_instance_2

    def test_destroy_dbos_noop_when_no_instance(self) -> None:
        """destroy_dbos() is a no-op when no instance exists."""
        with patch("src.dbos_workflows.config.DBOS") as mock_dbos_class:
            reset_dbos()
            destroy_dbos()

            mock_dbos_class.destroy.assert_not_called()


class TestDbosClientSingleton:
    """Tests for DBOSClient singleton management."""

    def test_get_dbos_client_returns_client_instance(self) -> None:
        """get_dbos_client() returns a DBOSClient instance."""
        with patch("src.dbos_workflows.config.DBOSClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            reset_dbos_client()
            result = get_dbos_client()

            assert result == mock_client
            mock_client_class.assert_called_once()

    def test_get_dbos_client_returns_same_instance(self) -> None:
        """Subsequent calls return the same singleton instance."""
        with patch("src.dbos_workflows.config.DBOSClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            reset_dbos_client()
            first = get_dbos_client()
            second = get_dbos_client()

            assert first is second
            assert mock_client_class.call_count == 1

    def test_reset_dbos_client_clears_instance(self) -> None:
        """reset_dbos_client() clears the cached instance."""
        with patch("src.dbos_workflows.config.DBOSClient") as mock_client_class:
            mock_client_1 = MagicMock()
            mock_client_2 = MagicMock()
            mock_client_class.side_effect = [mock_client_1, mock_client_2]

            reset_dbos_client()
            first = get_dbos_client()
            reset_dbos_client()
            second = get_dbos_client()

            assert first is not second
            assert mock_client_class.call_count == 2


class TestThreadSafety:
    """Tests for thread-safe singleton access."""

    def test_get_dbos_thread_safe(self) -> None:
        """get_dbos() is thread-safe under concurrent access."""
        import threading

        with patch("src.dbos_workflows.config.DBOS") as mock_dbos_class:
            mock_instance = MagicMock()
            mock_dbos_class.return_value = mock_instance

            reset_dbos()
            results: list[Any] = []
            errors: list[Exception] = []

            def call_get_dbos() -> None:
                try:
                    results.append(get_dbos())
                except Exception as e:
                    errors.append(e)

            threads = [threading.Thread(target=call_get_dbos) for _ in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            assert len(errors) == 0
            assert len(results) == 10
            assert all(r is mock_instance for r in results)
            assert mock_dbos_class.call_count == 1

    def test_get_dbos_client_thread_safe(self) -> None:
        """get_dbos_client() is thread-safe under concurrent access."""
        import threading

        with patch("src.dbos_workflows.config.DBOSClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            reset_dbos_client()
            results: list[Any] = []
            errors: list[Exception] = []

            def call_get_client() -> None:
                try:
                    results.append(get_dbos_client())
                except Exception as e:
                    errors.append(e)

            threads = [threading.Thread(target=call_get_client) for _ in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            assert len(errors) == 0
            assert len(results) == 10
            assert all(r is mock_client for r in results)
            assert mock_client_class.call_count == 1


class TestValidateDbosConnection:
    """Tests for validate_dbos_connection() function."""

    def test_raises_runtime_error_on_connection_failure(self) -> None:
        """Raises RuntimeError when database connection fails."""
        import psycopg

        with (
            patch("src.dbos_workflows.config.get_dbos_config") as mock_config,
            patch("psycopg.connect") as mock_connect,
        ):
            mock_config.return_value = {"system_database_url": "postgresql://bad:url@host/db"}
            mock_connect.side_effect = psycopg.Error("Connection refused")

            with pytest.raises(RuntimeError, match="DBOS database connection failed"):
                validate_dbos_connection()

    def test_raises_runtime_error_when_schema_missing(self) -> None:
        """Raises RuntimeError when DBOS schema is not found."""
        with (
            patch("src.dbos_workflows.config.get_dbos_config") as mock_config,
            patch("psycopg.connect") as mock_connect,
        ):
            mock_config.return_value = {"system_database_url": "postgresql://user:pass@host/db"}
            mock_cursor = MagicMock()
            mock_cursor.fetchone.return_value = (False,)
            mock_conn = MagicMock()
            mock_conn.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn.__exit__ = MagicMock(return_value=False)
            mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
            mock_connect.return_value = mock_conn

            with pytest.raises(RuntimeError, match="DBOS system tables not found"):
                validate_dbos_connection()

    def test_returns_true_when_validation_succeeds(self) -> None:
        """Returns True when database connection and schema check succeed."""
        with (
            patch("src.dbos_workflows.config.get_dbos_config") as mock_config,
            patch("psycopg.connect") as mock_connect,
        ):
            mock_config.return_value = {"system_database_url": "postgresql://user:pass@host/db"}
            mock_cursor = MagicMock()
            mock_cursor.fetchone.return_value = (True,)
            mock_conn = MagicMock()
            mock_conn.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn.__exit__ = MagicMock(return_value=False)
            mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
            mock_connect.return_value = mock_conn

            result = validate_dbos_connection()
            assert result is True
