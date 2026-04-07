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
from sqlalchemy.pool import NullPool

from src.config import get_settings
from src.dbos_workflows.config import (
    _derive_http_otlp_endpoint,
    create_dbos_instance,
    destroy_dbos,
    get_dbos,
    get_dbos_config,
    reset_dbos,
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
    get_settings.cache_clear()  # type: ignore[attr-defined]
    yield
    get_settings.cache_clear()  # type: ignore[attr-defined]


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

    def test_handles_missing_scheme(self) -> None:
        """Returns None when scheme is missing (invalid URL)."""
        result = _derive_http_otlp_endpoint("tempo:4317")
        assert result is None

    def test_handles_no_port_specified(self) -> None:
        """Handles URL without explicit port."""
        result = _derive_http_otlp_endpoint("http://tempo")
        assert result == "http://tempo"


class TestGetDbosConfig:
    """Tests for get_dbos_config() function."""

    def test_returns_valid_config_dict(self) -> None:
        """Config dict includes required DBOS fields."""
        with patch("src.dbos_workflows.config.settings") as mock_settings:
            mock_settings.DATABASE_URL = TEST_DATABASE_URL
            mock_settings.DATABASE_DIRECT_URL = None
            mock_settings.OTEL_SERVICE_NAME = "test-service"
            mock_settings.PROJECT_NAME = "Test Project"
            mock_settings.OTLP_ENDPOINT = None
            mock_settings.DBOS_CONDUCTOR_KEY = None
            mock_settings.VERSION = "1.0.0"
            mock_settings.ENVIRONMENT = "test"

            config: dict[str, Any] = dict(get_dbos_config())

            assert isinstance(config, dict)
            assert "name" in config
            assert "system_database_url" in config

    def test_converts_asyncpg_url_to_sync(self) -> None:
        """Async PostgreSQL URL is converted to sync format for DBOS."""
        with patch("src.dbos_workflows.config.settings") as mock_settings:
            mock_settings.DATABASE_URL = "postgresql+asyncpg://user:pass@host:5432/db"
            mock_settings.DATABASE_DIRECT_URL = None
            mock_settings.OTEL_SERVICE_NAME = "test-service"
            mock_settings.PROJECT_NAME = None
            mock_settings.OTLP_ENDPOINT = None
            mock_settings.DBOS_CONDUCTOR_KEY = None
            mock_settings.VERSION = "1.0.0"
            mock_settings.ENVIRONMENT = "test"

            config: dict[str, Any] = dict(get_dbos_config())
            db_url = config.get("system_database_url", "")

            assert "postgresql+asyncpg://" not in db_url
            assert "postgresql://" in db_url
            assert db_url == "postgresql://user:pass@host:5432/db"

    def test_app_name_uses_dbos_app_name_setting(self) -> None:
        """Config uses DBOS_APP_NAME setting directly."""
        with patch("src.dbos_workflows.config.settings") as mock_settings:
            mock_settings.DATABASE_URL = TEST_DATABASE_URL
            mock_settings.DATABASE_DIRECT_URL = None
            mock_settings.DBOS_APP_NAME = "custom-dbos-app"
            mock_settings.OTLP_ENDPOINT = None
            mock_settings.DBOS_CONDUCTOR_KEY = None
            mock_settings.VERSION = "1.0.0"
            mock_settings.ENVIRONMENT = "test"

            result = dict(get_dbos_config())

            assert result.get("name") == "custom-dbos-app"

    def test_raises_if_database_url_missing(self) -> None:
        """Raises ValueError if DATABASE_URL is not configured."""
        with patch("src.dbos_workflows.config.settings") as mock_settings:
            mock_settings.DATABASE_URL = None
            mock_settings.DATABASE_DIRECT_URL = None

            with pytest.raises(ValueError, match="DATABASE_URL"):
                get_dbos_config()

    def test_raises_if_database_url_empty(self) -> None:
        """Raises ValueError if DATABASE_URL is empty string."""
        with patch("src.dbos_workflows.config.settings") as mock_settings:
            mock_settings.DATABASE_URL = ""
            mock_settings.DATABASE_DIRECT_URL = None

            with pytest.raises(ValueError, match="DATABASE_URL"):
                get_dbos_config()

    def test_includes_otlp_config_when_endpoint_set(self) -> None:
        """Config includes OTLP settings when OTLP_ENDPOINT is configured."""
        with patch("src.dbos_workflows.config.settings") as mock_settings:
            mock_settings.DATABASE_URL = TEST_DATABASE_URL
            mock_settings.OTLP_ENDPOINT = "http://tempo:4317"
            mock_settings.LOGFIRE_ENABLED = False
            mock_settings.OTEL_SERVICE_NAME = "opennotes-server"
            mock_settings.PROJECT_NAME = "Open Notes Server"
            mock_settings.DBOS_CONDUCTOR_KEY = None
            mock_settings.VERSION = "1.0.0"
            mock_settings.ENVIRONMENT = "test"

            config: dict[str, Any] = dict(get_dbos_config())

            assert config.get("enable_otlp") is True
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
            mock_settings.VERSION = "1.0.0"
            mock_settings.ENVIRONMENT = "test"

            config: dict[str, Any] = dict(get_dbos_config())

            assert "enable_otlp" not in config
            assert "otlp_traces_endpoints" not in config
            assert "otlp_logs_endpoints" not in config

    def test_includes_admin_port_from_settings(self) -> None:
        """Config includes admin_port from DBOS_ADMIN_PORT setting."""
        with patch("src.dbos_workflows.config.settings") as mock_settings:
            mock_settings.DATABASE_URL = TEST_DATABASE_URL
            mock_settings.DBOS_APP_NAME = "opennotes-server"
            mock_settings.DBOS_ADMIN_PORT = 9999
            mock_settings.DBOS_RUN_ADMIN_SERVER = True
            mock_settings.OTLP_ENDPOINT = None
            mock_settings.DBOS_CONDUCTOR_KEY = None
            mock_settings.VERSION = "1.0.0"
            mock_settings.ENVIRONMENT = "test"

            config: dict[str, Any] = dict(get_dbos_config())

            assert config["admin_port"] == 9999

    def test_includes_run_admin_server_from_settings(self) -> None:
        """Config includes run_admin_server from DBOS_RUN_ADMIN_SERVER setting."""
        with patch("src.dbos_workflows.config.settings") as mock_settings:
            mock_settings.DATABASE_URL = TEST_DATABASE_URL
            mock_settings.DBOS_APP_NAME = "opennotes-server"
            mock_settings.DBOS_ADMIN_PORT = 3001
            mock_settings.DBOS_RUN_ADMIN_SERVER = False
            mock_settings.OTLP_ENDPOINT = None
            mock_settings.DBOS_CONDUCTOR_KEY = None
            mock_settings.VERSION = "1.0.0"
            mock_settings.ENVIRONMENT = "test"

            config: dict[str, Any] = dict(get_dbos_config())

            assert config["run_admin_server"] is False

    def test_admin_port_defaults(self) -> None:
        """Config uses default admin_port and run_admin_server values."""
        with patch("src.dbos_workflows.config.settings") as mock_settings:
            mock_settings.DATABASE_URL = TEST_DATABASE_URL
            mock_settings.DBOS_APP_NAME = "opennotes-server"
            mock_settings.DBOS_ADMIN_PORT = 3001
            mock_settings.DBOS_RUN_ADMIN_SERVER = True
            mock_settings.OTLP_ENDPOINT = None
            mock_settings.DBOS_CONDUCTOR_KEY = None
            mock_settings.VERSION = "1.0.0"
            mock_settings.ENVIRONMENT = "test"

            config: dict[str, Any] = dict(get_dbos_config())

            assert config["admin_port"] == 3001
            assert config["run_admin_server"] is True

    def test_prefers_direct_url_for_system_database(self) -> None:
        with patch("src.dbos_workflows.config.settings") as mock_settings:
            mock_settings.DATABASE_URL = "postgresql+asyncpg://user:pass@pooler:6543/db"
            mock_settings.DATABASE_DIRECT_URL = "postgresql+asyncpg://user:pass@direct:5432/db"
            mock_settings.DBOS_APP_NAME = "test"
            mock_settings.DBOS_ADMIN_PORT = 3001
            mock_settings.DBOS_RUN_ADMIN_SERVER = False
            mock_settings.DBOS_CONDUCTOR_KEY = None
            mock_settings.OTLP_ENDPOINT = None
            mock_settings.VERSION = "1.0.0"
            mock_settings.ENVIRONMENT = "test"

            config = dict(get_dbos_config())

            assert "direct:5432" in config["system_database_url"]
            assert "pooler:6543" not in config["system_database_url"]

    def test_falls_back_to_database_url_when_direct_url_is_none(self) -> None:
        with patch("src.dbos_workflows.config.settings") as mock_settings:
            mock_settings.DATABASE_URL = "postgresql+asyncpg://user:pass@pooler:6543/db"
            mock_settings.DATABASE_DIRECT_URL = None
            mock_settings.DBOS_APP_NAME = "test"
            mock_settings.DBOS_ADMIN_PORT = 3001
            mock_settings.DBOS_RUN_ADMIN_SERVER = False
            mock_settings.DBOS_CONDUCTOR_KEY = None
            mock_settings.OTLP_ENDPOINT = None
            mock_settings.VERSION = "1.0.0"
            mock_settings.ENVIRONMENT = "test"

            config = dict(get_dbos_config())

            assert "pooler:6543" in config["system_database_url"]

    def test_config_does_not_include_conductor_key(self) -> None:
        with patch("src.dbos_workflows.config.settings") as mock_settings:
            mock_settings.DATABASE_URL = TEST_DATABASE_URL
            mock_settings.OTEL_SERVICE_NAME = "test-service"
            mock_settings.PROJECT_NAME = "Test Project"
            mock_settings.OTLP_ENDPOINT = None
            mock_settings.DBOS_CONDUCTOR_KEY = "test-conductor-api-key-123"
            mock_settings.VERSION = "1.0.0"
            mock_settings.ENVIRONMENT = "test"

            config: dict[str, Any] = dict(get_dbos_config())

            assert (
                "conductor_key" not in config
            )  # conductor_key is set in create_dbos_instance, not get_dbos_config


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
        """create_dbos_instance() adds conductor_key to config dict when set."""
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

            assert mock_config["conductor_key"] == "test-key-123"
            mock_dbos_class.assert_called_once_with(config=mock_config)

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


class TestDbosNullPoolCompatibility:
    """Tests for DBOS NullPool compatibility on supported upstream releases."""

    def test_uses_upstream_configure_db_engine_parameters(self) -> None:
        from dbos._dbos_config import configure_db_engine_parameters

        assert configure_db_engine_parameters.__module__ == "dbos._dbos_config"

    def test_strips_pool_kwargs_when_nullpool(self) -> None:
        """DBOS strips pool-sizing kwargs after merging defaults for NullPool."""
        from dbos._dbos_config import DatabaseConfig, configure_db_engine_parameters

        data: DatabaseConfig = {
            "db_engine_kwargs": {
                "poolclass": NullPool,
                "connect_args": {"prepare_threshold": None},
            },
        }
        configure_db_engine_parameters(data)

        engine_kwargs = data["db_engine_kwargs"]
        assert engine_kwargs is not None
        assert engine_kwargs["poolclass"] is NullPool
        for forbidden_key in ("pool_timeout", "max_overflow", "pool_size", "pool_pre_ping"):
            assert forbidden_key not in engine_kwargs, (
                f"{forbidden_key} must not be in db_engine_kwargs when NullPool is configured"
            )

    def test_preserves_pool_kwargs_without_nullpool(self) -> None:
        """DBOS preserves pool kwargs for normal pool classes."""
        from dbos._dbos_config import DatabaseConfig, configure_db_engine_parameters

        data: DatabaseConfig = {
            "db_engine_kwargs": {
                "connect_args": {"prepare_threshold": None},
            },
        }
        configure_db_engine_parameters(data)

        engine_kwargs = data["db_engine_kwargs"]
        assert engine_kwargs is not None
        assert "pool_timeout" in engine_kwargs
        assert "pool_size" in engine_kwargs

    def test_strips_from_sys_db_engine_kwargs_too(self) -> None:
        """DBOS also strips pool kwargs from sys_db_engine_kwargs."""
        from dbos._dbos_config import DatabaseConfig, configure_db_engine_parameters

        data: DatabaseConfig = {
            "db_engine_kwargs": {
                "poolclass": NullPool,
                "connect_args": {"prepare_threshold": None},
            },
        }
        configure_db_engine_parameters(data)

        sys_kwargs = data.get("sys_db_engine_kwargs", {})
        assert sys_kwargs is not None
        for forbidden_key in ("pool_timeout", "max_overflow", "pool_size", "pool_pre_ping"):
            assert forbidden_key not in sys_kwargs


class TestValidateDbosConnection:
    """Tests for validate_dbos_connection() function."""

    def test_passes_prepare_threshold_none(self) -> None:
        """validate_dbos_connection() passes prepare_threshold=None to psycopg.connect()."""
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

            validate_dbos_connection()

            call_kwargs = mock_connect.call_args.kwargs
            assert "prepare_threshold" in call_kwargs
            assert call_kwargs["prepare_threshold"] is None

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
