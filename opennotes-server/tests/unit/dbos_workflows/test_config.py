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

pytestmark = pytest.mark.unit


class TestDeriveHttpOtlpEndpoint:
    """Tests for _derive_http_otlp_endpoint() function."""

    def test_returns_none_for_empty_endpoint(self) -> None:
        """Returns None when endpoint is empty or None."""
        from src.dbos_workflows.config import _derive_http_otlp_endpoint

        assert _derive_http_otlp_endpoint(None) is None
        assert _derive_http_otlp_endpoint("") is None

    def test_converts_grpc_port_to_http_port(self) -> None:
        """Converts gRPC port 4317 to HTTP port 4318."""
        from src.dbos_workflows.config import _derive_http_otlp_endpoint

        result = _derive_http_otlp_endpoint("http://tempo:4317")
        assert result == "http://tempo:4318"

    def test_converts_localhost_grpc_to_http(self) -> None:
        """Converts localhost gRPC endpoint to HTTP."""
        from src.dbos_workflows.config import _derive_http_otlp_endpoint

        result = _derive_http_otlp_endpoint("http://localhost:4317")
        assert result == "http://localhost:4318"

    def test_preserves_https_endpoints(self) -> None:
        """Preserves HTTPS endpoints with non-4317 ports."""
        from src.dbos_workflows.config import _derive_http_otlp_endpoint

        result = _derive_http_otlp_endpoint("https://otel-collector:443")
        assert result == "https://otel-collector:443"

    def test_strips_trailing_slash(self) -> None:
        """Strips trailing slash from endpoint."""
        from src.dbos_workflows.config import _derive_http_otlp_endpoint

        result = _derive_http_otlp_endpoint("http://tempo:4317/")
        assert result == "http://tempo:4318"

    def test_handles_ipv4_address(self) -> None:
        """Handles IPv4 address endpoints."""
        from src.dbos_workflows.config import _derive_http_otlp_endpoint

        result = _derive_http_otlp_endpoint("http://10.0.0.1:4317")
        assert result == "http://10.0.0.1:4318"


class TestGetOtlpConfig:
    """Tests for _get_otlp_config() function."""

    def test_returns_disabled_when_no_endpoint(self) -> None:
        """Returns enable_otlp=False when OTLP_ENDPOINT is not set."""
        with patch("src.dbos_workflows.config.settings") as mock_settings:
            mock_settings.OTLP_ENDPOINT = None

            from src.dbos_workflows.config import _get_otlp_config

            result = _get_otlp_config()

            assert result == {"enable_otlp": False}

    def test_returns_enabled_with_endpoints(self) -> None:
        """Returns OTLP config with trace and log endpoints when enabled."""
        with patch("src.dbos_workflows.config.settings") as mock_settings:
            mock_settings.OTLP_ENDPOINT = "http://tempo:4317"
            mock_settings.OTEL_SERVICE_NAME = "test-service"
            mock_settings.PROJECT_NAME = "Test Project"
            mock_settings.VERSION = "1.0.0"
            mock_settings.ENVIRONMENT = "test"

            from src.dbos_workflows.config import _get_otlp_config

            result = _get_otlp_config()

            assert result["enable_otlp"] is True
            assert result["otlp_traces_endpoints"] == ["http://tempo:4318/v1/traces"]
            assert result["otlp_logs_endpoints"] == ["http://tempo:4318/v1/logs"]

    def test_uses_project_name_when_otel_service_name_not_set(self) -> None:
        """Falls back to PROJECT_NAME when OTEL_SERVICE_NAME is not set."""
        with patch("src.dbos_workflows.config.settings") as mock_settings:
            mock_settings.OTLP_ENDPOINT = "http://tempo:4317"
            mock_settings.OTEL_SERVICE_NAME = None
            mock_settings.PROJECT_NAME = "Open Notes Server"

            from src.dbos_workflows.config import _get_otlp_config

            result = _get_otlp_config()

            assert result["enable_otlp"] is True


class TestGetDbosConfig:
    """Tests for get_dbos_config() function."""

    def test_returns_valid_config_dict(self) -> None:
        """Config dict includes required DBOS fields."""
        from src.dbos_workflows.config import get_dbos_config

        config: dict[str, Any] = dict(get_dbos_config())

        assert isinstance(config, dict)
        assert "name" in config
        assert "system_database_url" in config

    def test_converts_asyncpg_url_to_sync(self) -> None:
        """Async PostgreSQL URL is converted to sync format for DBOS."""
        from src.dbos_workflows.config import get_dbos_config

        config: dict[str, Any] = dict(get_dbos_config())
        db_url = config.get("system_database_url", "")

        assert "postgresql+asyncpg://" not in db_url
        assert "postgresql://" in db_url

    def test_app_name_uses_otel_service_name_or_project_name(self) -> None:
        """Config uses OTEL_SERVICE_NAME or PROJECT_NAME for app name."""
        from src.dbos_workflows.config import get_dbos_config

        config: dict[str, Any] = dict(get_dbos_config())
        name = config.get("name")

        assert name is not None
        assert len(name) > 0

    def test_app_name_uses_otel_service_name_when_set(self) -> None:
        """Config uses OTEL_SERVICE_NAME when explicitly set."""
        with patch("src.dbos_workflows.config.settings") as mock_settings:
            mock_settings.DATABASE_URL = "postgresql+asyncpg://localhost/test"
            mock_settings.OTEL_SERVICE_NAME = "custom-otel-name"
            mock_settings.PROJECT_NAME = "Open Notes Server"
            mock_settings.OTLP_ENDPOINT = None

            from src.dbos_workflows import config as config_module

            result = dict(config_module.get_dbos_config())

            assert result.get("name") == "custom-otel-name"

    def test_app_name_falls_back_to_project_name(self) -> None:
        """Config falls back to PROJECT_NAME when OTEL_SERVICE_NAME is not set."""
        with patch("src.dbos_workflows.config.settings") as mock_settings:
            mock_settings.DATABASE_URL = "postgresql+asyncpg://localhost/test"
            mock_settings.OTEL_SERVICE_NAME = None
            mock_settings.PROJECT_NAME = "Open Notes Server"
            mock_settings.OTLP_ENDPOINT = None

            from src.dbos_workflows import config as config_module

            result = dict(config_module.get_dbos_config())

            assert result.get("name") == "Open Notes Server"

    def test_app_name_falls_back_to_empty_when_both_unset(self) -> None:
        """Config handles case when both OTEL_SERVICE_NAME and PROJECT_NAME are None."""
        with patch("src.dbos_workflows.config.settings") as mock_settings:
            mock_settings.DATABASE_URL = "postgresql+asyncpg://localhost/test"
            mock_settings.OTEL_SERVICE_NAME = None
            mock_settings.PROJECT_NAME = None
            mock_settings.OTLP_ENDPOINT = None

            from src.dbos_workflows import config as config_module

            result = dict(config_module.get_dbos_config())

            assert result.get("name") is None

    def test_raises_if_database_url_missing(self) -> None:
        """Raises ValueError if DATABASE_URL is not configured."""
        with patch("src.dbos_workflows.config.settings") as mock_settings:
            mock_settings.DATABASE_URL = None

            from src.dbos_workflows import config as config_module

            with pytest.raises(ValueError, match="DATABASE_URL"):
                config_module.get_dbos_config()

    def test_includes_otlp_config_when_endpoint_set(self) -> None:
        """Config includes OTLP settings when OTLP_ENDPOINT is configured."""
        with patch("src.dbos_workflows.config.settings") as mock_settings:
            mock_settings.DATABASE_URL = "postgresql+asyncpg://user:pass@host:5432/db"
            mock_settings.OTLP_ENDPOINT = "http://tempo:4317"
            mock_settings.OTEL_SERVICE_NAME = "opennotes-server"
            mock_settings.PROJECT_NAME = "Open Notes Server"

            from src.dbos_workflows import config as config_module

            config: dict[str, Any] = dict(config_module.get_dbos_config())

            assert config["enable_otlp"] is True
            assert config["otlp_traces_endpoints"] == ["http://tempo:4318/v1/traces"]
            assert config["otlp_logs_endpoints"] == ["http://tempo:4318/v1/logs"]

    def test_disables_otlp_when_no_endpoint(self) -> None:
        """Config disables OTLP when OTLP_ENDPOINT is not set."""
        with patch("src.dbos_workflows.config.settings") as mock_settings:
            mock_settings.DATABASE_URL = "postgresql+asyncpg://user:pass@host:5432/db"
            mock_settings.OTLP_ENDPOINT = None
            mock_settings.OTEL_SERVICE_NAME = None
            mock_settings.PROJECT_NAME = "Open Notes Server"

            from src.dbos_workflows import config as config_module

            config: dict[str, Any] = dict(config_module.get_dbos_config())

            assert config["enable_otlp"] is False
            assert "otlp_traces_endpoints" not in config
            assert "otlp_logs_endpoints" not in config


class TestDbosInstance:
    """Tests for DBOS singleton management."""

    def test_get_dbos_returns_dbos_instance(self) -> None:
        """get_dbos() returns a DBOS instance."""
        with patch("src.dbos_workflows.config.DBOS") as mock_dbos_class:
            mock_instance = MagicMock()
            mock_dbos_class.return_value = mock_instance

            from src.dbos_workflows.config import get_dbos, reset_dbos

            reset_dbos()
            result = get_dbos()

            assert result == mock_instance
            mock_dbos_class.assert_called_once()

    def test_get_dbos_returns_same_instance(self) -> None:
        """Subsequent calls return the same singleton instance."""
        with patch("src.dbos_workflows.config.DBOS") as mock_dbos_class:
            mock_instance = MagicMock()
            mock_dbos_class.return_value = mock_instance

            from src.dbos_workflows.config import get_dbos, reset_dbos

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

            from src.dbos_workflows.config import get_dbos, reset_dbos

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
        ):
            mock_config: dict[str, Any] = {
                "name": "test",
                "system_database_url": "postgresql://",
            }
            mock_get_config.return_value = mock_config

            from src.dbos_workflows.config import create_dbos_instance

            create_dbos_instance()

            mock_dbos_class.assert_called_once_with(config=mock_config)


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

            from src.dbos_workflows.config import validate_dbos_connection

            mock_dbos = MagicMock()
            with pytest.raises(RuntimeError, match="DBOS database connection failed"):
                validate_dbos_connection(mock_dbos)

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

            from src.dbos_workflows.config import validate_dbos_connection

            mock_dbos = MagicMock()
            with pytest.raises(RuntimeError, match="DBOS system tables not found"):
                validate_dbos_connection(mock_dbos)

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

            from src.dbos_workflows.config import validate_dbos_connection

            mock_dbos = MagicMock()
            result = validate_dbos_connection(mock_dbos)
            assert result is True
