"""Unit tests for DBOS configuration module.

Tests cover:
- Config construction from settings
- Singleton pattern (get_dbos, reset_dbos)
- URL format conversion (async to sync)
- Schema isolation configuration
"""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


class TestGetDbosConfig:
    """Tests for get_dbos_config() function."""

    def test_returns_valid_config_dict(self) -> None:
        """Config dict includes required DBOS fields."""
        from src.dbos_workflows.config import get_dbos_config

        config: dict[str, Any] = dict(get_dbos_config())

        assert isinstance(config, dict)
        assert "name" in config
        assert "system_database_url" in config
        assert "dbos_system_schema" in config

    def test_uses_dbos_schema_isolation(self) -> None:
        """Config specifies 'dbos' schema for system tables."""
        from src.dbos_workflows.config import get_dbos_config

        config: dict[str, Any] = dict(get_dbos_config())

        assert config.get("dbos_system_schema") == "dbos"

    def test_converts_asyncpg_url_to_sync(self) -> None:
        """Async PostgreSQL URL is converted to sync format for DBOS."""
        from src.dbos_workflows.config import get_dbos_config

        config: dict[str, Any] = dict(get_dbos_config())
        db_url = config.get("system_database_url", "")

        assert "postgresql+asyncpg://" not in db_url
        assert "postgresql://" in db_url

    def test_app_name_is_opennotes_server(self) -> None:
        """Config uses correct application name."""
        from src.dbos_workflows.config import get_dbos_config

        config: dict[str, Any] = dict(get_dbos_config())

        assert config.get("name") == "opennotes-server"

    def test_raises_if_database_url_missing(self) -> None:
        """Raises ValueError if DATABASE_URL is not configured."""
        with patch("src.dbos_workflows.config.settings") as mock_settings:
            mock_settings.DATABASE_URL = None

            from src.dbos_workflows import config as config_module

            with pytest.raises(ValueError, match="DATABASE_URL"):
                config_module.get_dbos_config()


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
