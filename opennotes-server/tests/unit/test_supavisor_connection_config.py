"""Tests for Supavisor-compatible connection configuration (task-1213).

Verifies:
- All SQLAlchemy engines use NullPool
- asyncpg connect_args disable prepared statement caches
- DBOS psycopg config disables prepared statements
- dispose() pattern updated for NullPool
- Deprecated pool config fields still work
"""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.pool import NullPool

pytestmark = pytest.mark.unit


class TestDatabaseEngineNullPool:
    """AC#1: All SQLAlchemy engines use NullPool."""

    def test_create_engine_uses_null_pool(self) -> None:
        from src.database import _create_engine

        with patch("src.database.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/testdb",
                DEBUG=False,
            )
            engine = _create_engine()

        assert engine.pool.__class__.__name__ == "AsyncAdaptedQueuePool" or isinstance(
            engine.sync_engine.pool, NullPool
        ), "Engine must use NullPool for Supavisor compatibility"
        assert isinstance(engine.sync_engine.pool, NullPool)

    def test_create_engine_does_not_use_pool_size(self) -> None:
        from src.database import _create_engine

        with patch("src.database.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/testdb",
                DEBUG=False,
            )
            engine = _create_engine()

        assert isinstance(engine.sync_engine.pool, NullPool)


class TestAsyncpgConnectArgs:
    """AC#2: asyncpg connect_args disable prepared statement cache."""

    def test_create_engine_disables_prepared_statement_cache(self) -> None:
        with patch("src.database.create_async_engine") as mock_create:
            mock_create.return_value = MagicMock()

            from src.database import _create_engine

            with patch("src.database.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(
                    DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/testdb",
                    DEBUG=False,
                )
                _create_engine()

            call_kwargs = mock_create.call_args[1]
            assert "connect_args" in call_kwargs
            assert call_kwargs["connect_args"]["prepared_statement_cache_size"] == 0
            assert call_kwargs["connect_args"]["statement_cache_size"] == 0


class TestContentMonitoringNullPool:
    """AC#1: content_monitoring ephemeral engines also use NullPool."""

    def test_content_monitoring_create_db_engine_uses_null_pool(self) -> None:
        with patch("src.tasks.content_monitoring_tasks.create_async_engine") as mock_create:
            mock_create.return_value = MagicMock()

            from src.tasks.content_monitoring_tasks import _create_db_engine

            _create_db_engine("postgresql+asyncpg://user:pass@localhost:5432/testdb")

            call_kwargs = mock_create.call_args[1]
            assert call_kwargs.get("poolclass") is NullPool
            assert call_kwargs["connect_args"]["prepared_statement_cache_size"] == 0
            assert call_kwargs["connect_args"]["statement_cache_size"] == 0


class TestDbosConfigSupavisor:
    """AC#3: DBOS psycopg compatibility with Supavisor transaction mode."""

    def test_dbos_config_includes_engine_kwargs_with_null_pool(self) -> None:
        with patch("src.dbos_workflows.config.settings") as mock_settings:
            mock_settings.DATABASE_URL = "postgresql+asyncpg://user:pass@localhost:5432/testdb"
            mock_settings.DBOS_APP_NAME = "test"
            mock_settings.OTLP_ENDPOINT = None
            mock_settings.VERSION = "1.0.0"
            mock_settings.ENVIRONMENT = "test"

            from src.dbos_workflows.config import get_dbos_config

            config: dict[str, Any] = dict(get_dbos_config())

            assert "db_engine_kwargs" in config
            engine_kwargs = config["db_engine_kwargs"]
            assert engine_kwargs["poolclass"] is NullPool
            assert engine_kwargs["connect_args"]["prepare_threshold"] is None


class TestDisposePatternNullPool:
    """AC#7: dispose(close=False) pattern updated for NullPool."""

    def test_get_engine_loop_change_disposes_without_close_false(self) -> None:
        from src import database

        old_loop = MagicMock()
        new_loop = MagicMock()

        mock_sync_engine = MagicMock()
        mock_old_engine = MagicMock()
        mock_old_engine.sync_engine = mock_sync_engine

        mock_new_engine = MagicMock()

        original_engine = database._engine
        original_session_maker = database._async_session_maker
        original_loop = database._engine_loop

        try:
            database._engine = mock_old_engine
            database._engine_loop = old_loop

            with (
                patch("src.database.asyncio.get_running_loop", return_value=new_loop),
                patch("src.database._create_engine", return_value=mock_new_engine),
            ):
                database.get_engine()

            mock_sync_engine.dispose.assert_called_once_with()
        finally:
            database._engine = original_engine
            database._async_session_maker = original_session_maker
            database._engine_loop = original_loop

    def test_reset_database_disposes_without_close_false(self) -> None:
        from src import database

        mock_sync_engine = MagicMock()
        mock_engine = MagicMock()
        mock_engine.sync_engine = mock_sync_engine

        original_engine = database._engine
        original_session_maker = database._async_session_maker
        original_loop = database._engine_loop

        try:
            database._engine = mock_engine
            database._async_session_maker = MagicMock()
            database._engine_loop = MagicMock()

            database._reset_database_for_test_loop()

            mock_sync_engine.dispose.assert_called_once_with()
        finally:
            database._engine = original_engine
            database._async_session_maker = original_session_maker
            database._engine_loop = original_loop


class TestDeprecatedPoolConfig:
    """AC#6: DB_POOL_SIZE and related fields deprecated."""

    def test_pool_size_field_has_deprecation_warning(self) -> None:
        from src.config import Settings

        field_info = Settings.model_fields["DB_POOL_SIZE"]
        assert (
            "deprecated" in (field_info.description or "").lower()
            or field_info.deprecated is not None
        )

    def test_pool_max_overflow_field_has_deprecation_warning(self) -> None:
        from src.config import Settings

        field_info = Settings.model_fields["DB_POOL_MAX_OVERFLOW"]
        assert (
            "deprecated" in (field_info.description or "").lower()
            or field_info.deprecated is not None
        )
