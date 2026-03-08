"""Tests for Supavisor-compatible connection configuration (task-1213, task-1246.05).

Verifies:
- All SQLAlchemy engines use NullPool
- asyncpg connect_args disable prepared statement caches at SQLAlchemy adapter level
- URL query parameters (sslmode, options, etc.) are preserved through the creator
- DBOS psycopg config disables prepared statements
- Deprecated pool config fields still work
- Connection retry is wired into all engine creation sites
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

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
                DB_CONNECT_MAX_RETRIES=3,
                DB_CONNECT_BACKOFF_BASE_SECONDS=0.5,
            )
            engine = _create_engine()

        assert isinstance(engine.sync_engine.pool, NullPool)

    def test_create_engine_does_not_pass_pool_size_kwargs(self) -> None:
        with patch("src.database.create_async_engine") as mock_create:
            mock_create.return_value = MagicMock()

            from src.database import _create_engine

            with patch("src.database.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(
                    DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/testdb",
                    DEBUG=False,
                    DB_CONNECT_MAX_RETRIES=3,
                    DB_CONNECT_BACKOFF_BASE_SECONDS=0.5,
                )
                _create_engine()

            call_kwargs = mock_create.call_args[1]
            assert "pool_size" not in call_kwargs
            assert "max_overflow" not in call_kwargs
            assert "pool_timeout" not in call_kwargs
            assert "pool_recycle" not in call_kwargs


class TestAsyncpgConnectArgs:
    """AC#2: asyncpg connect_args disable prepared statement cache via async_creator."""

    def test_create_engine_uses_async_creator_with_retry(self) -> None:
        with patch("src.database.create_async_engine") as mock_create:
            mock_create.return_value = MagicMock()

            from src.database import _create_engine

            with patch("src.database.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(
                    DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/testdb",
                    DEBUG=False,
                    DB_CONNECT_MAX_RETRIES=3,
                    DB_CONNECT_BACKOFF_BASE_SECONDS=0.5,
                )
                _create_engine()

            call_kwargs = mock_create.call_args[1]
            assert "async_creator" in call_kwargs
            assert callable(call_kwargs["async_creator"])

    def test_create_engine_passes_prepared_statement_cache_size_zero(self) -> None:
        with patch("src.database.create_async_engine") as mock_create:
            mock_create.return_value = MagicMock()

            from src.database import _create_engine

            with patch("src.database.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(
                    DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/testdb",
                    DEBUG=False,
                    DB_CONNECT_MAX_RETRIES=3,
                    DB_CONNECT_BACKOFF_BASE_SECONDS=0.5,
                )
                _create_engine()

            call_kwargs = mock_create.call_args[1]
            assert "connect_args" in call_kwargs
            assert call_kwargs["connect_args"]["prepared_statement_cache_size"] == 0


class TestContentMonitoringNullPool:
    """AC#1: content_monitoring ephemeral engines also use NullPool with retry."""

    def test_content_monitoring_create_db_engine_uses_null_pool_and_retry(self) -> None:
        with (
            patch("src.tasks.content_monitoring_tasks.create_async_engine") as mock_create,
            patch("src.tasks.content_monitoring_tasks.get_settings") as mock_settings,
        ):
            mock_create.return_value = MagicMock()
            mock_settings.return_value = MagicMock(
                DB_CONNECT_MAX_RETRIES=3,
                DB_CONNECT_BACKOFF_BASE_SECONDS=0.5,
            )

            from src.tasks.content_monitoring_tasks import _create_db_engine

            _create_db_engine("postgresql+asyncpg://user:pass@localhost:5432/testdb")

            call_kwargs = mock_create.call_args[1]
            assert call_kwargs.get("poolclass") is NullPool
            assert "async_creator" in call_kwargs
            assert callable(call_kwargs["async_creator"])

    def test_content_monitoring_passes_prepared_statement_cache_size_zero(self) -> None:
        with (
            patch("src.tasks.content_monitoring_tasks.create_async_engine") as mock_create,
            patch("src.tasks.content_monitoring_tasks.get_settings") as mock_settings,
        ):
            mock_create.return_value = MagicMock()
            mock_settings.return_value = MagicMock(
                DB_CONNECT_MAX_RETRIES=3,
                DB_CONNECT_BACKOFF_BASE_SECONDS=0.5,
            )

            from src.tasks.content_monitoring_tasks import _create_db_engine

            _create_db_engine("postgresql+asyncpg://user:pass@localhost:5432/testdb")

            call_kwargs = mock_create.call_args[1]
            assert "connect_args" in call_kwargs
            assert call_kwargs["connect_args"]["prepared_statement_cache_size"] == 0


class TestUrlQueryParamsPreserved:
    """AC#2 (task-1246.05): URL query parameters preserved through the creator."""

    @pytest.mark.asyncio
    async def test_raw_connect_preserves_sslmode(self) -> None:
        captured_raw_connect = None

        def capture_retry(creator, **kwargs):
            nonlocal captured_raw_connect
            captured_raw_connect = creator
            return creator

        with (
            patch("src.database.asyncpg.connect", new_callable=AsyncMock) as mock_connect,
            patch("src.database.async_connect_with_retry", side_effect=capture_retry),
            patch("src.database.create_async_engine") as mock_create,
            patch("src.database.get_settings") as mock_settings,
        ):
            mock_create.return_value = MagicMock()
            mock_connect.return_value = MagicMock()
            mock_settings.return_value = MagicMock(
                DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/testdb?sslmode=require",
                DEBUG=False,
                DB_CONNECT_MAX_RETRIES=0,
                DB_CONNECT_BACKOFF_BASE_SECONDS=0.5,
            )

            from src.database import _create_engine

            _create_engine()

            assert captured_raw_connect is not None
            await captured_raw_connect()

            mock_connect.assert_called_once()
            connect_kwargs = mock_connect.call_args.kwargs
            dsn_value = connect_kwargs.get("dsn", "")
            assert "sslmode=require" in str(dsn_value)

    @pytest.mark.asyncio
    async def test_raw_connect_preserves_application_name(self) -> None:
        captured_raw_connect = None

        def capture_retry(creator, **kwargs):
            nonlocal captured_raw_connect
            captured_raw_connect = creator
            return creator

        with (
            patch("src.database.asyncpg.connect", new_callable=AsyncMock) as mock_connect,
            patch("src.database.async_connect_with_retry", side_effect=capture_retry),
            patch("src.database.create_async_engine") as mock_create,
            patch("src.database.get_settings") as mock_settings,
        ):
            mock_create.return_value = MagicMock()
            mock_connect.return_value = MagicMock()
            mock_settings.return_value = MagicMock(
                DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/testdb?application_name=opennotes",
                DEBUG=False,
                DB_CONNECT_MAX_RETRIES=0,
                DB_CONNECT_BACKOFF_BASE_SECONDS=0.5,
            )

            from src.database import _create_engine

            _create_engine()

            assert captured_raw_connect is not None
            await captured_raw_connect()

            mock_connect.assert_called_once()
            connect_kwargs = mock_connect.call_args.kwargs
            dsn_value = connect_kwargs.get("dsn", "")
            assert "application_name=opennotes" in str(dsn_value)

    @pytest.mark.asyncio
    async def test_raw_connect_strips_asyncpg_dialect_prefix(self) -> None:
        captured_raw_connect = None

        def capture_retry(creator, **kwargs):
            nonlocal captured_raw_connect
            captured_raw_connect = creator
            return creator

        with (
            patch("src.database.asyncpg.connect", new_callable=AsyncMock) as mock_connect,
            patch("src.database.async_connect_with_retry", side_effect=capture_retry),
            patch("src.database.create_async_engine") as mock_create,
            patch("src.database.get_settings") as mock_settings,
        ):
            mock_create.return_value = MagicMock()
            mock_connect.return_value = MagicMock()
            mock_settings.return_value = MagicMock(
                DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/testdb",
                DEBUG=False,
                DB_CONNECT_MAX_RETRIES=0,
                DB_CONNECT_BACKOFF_BASE_SECONDS=0.5,
            )

            from src.database import _create_engine

            _create_engine()

            assert captured_raw_connect is not None
            await captured_raw_connect()

            mock_connect.assert_called_once()
            connect_kwargs = mock_connect.call_args.kwargs
            dsn_value = str(connect_kwargs.get("dsn", ""))
            assert "postgresql://" in dsn_value
            assert "+asyncpg" not in dsn_value

    @pytest.mark.asyncio
    async def test_raw_connect_passes_statement_cache_size_zero(self) -> None:
        captured_raw_connect = None

        def capture_retry(creator, **kwargs):
            nonlocal captured_raw_connect
            captured_raw_connect = creator
            return creator

        with (
            patch("src.database.asyncpg.connect", new_callable=AsyncMock) as mock_connect,
            patch("src.database.async_connect_with_retry", side_effect=capture_retry),
            patch("src.database.create_async_engine") as mock_create,
            patch("src.database.get_settings") as mock_settings,
        ):
            mock_create.return_value = MagicMock()
            mock_connect.return_value = MagicMock()
            mock_settings.return_value = MagicMock(
                DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/testdb",
                DEBUG=False,
                DB_CONNECT_MAX_RETRIES=0,
                DB_CONNECT_BACKOFF_BASE_SECONDS=0.5,
            )

            from src.database import _create_engine

            _create_engine()

            assert captured_raw_connect is not None
            await captured_raw_connect()

            mock_connect.assert_called_once()
            connect_kwargs = mock_connect.call_args.kwargs
            assert connect_kwargs.get("statement_cache_size") == 0


class TestRetryConfigValidation:
    """AC#2 (task-1246.08): Config fields have appropriate Pydantic validators."""

    def test_max_retries_rejects_negative(self) -> None:
        from pydantic import ValidationError

        from src.config import Settings

        with pytest.raises(ValidationError, match="DB_CONNECT_MAX_RETRIES"):
            Settings(
                DB_CONNECT_MAX_RETRIES=-1,
                DATABASE_URL="postgresql+asyncpg://u:p@h:5432/db",
            )

    def test_max_retries_accepts_zero(self) -> None:
        from src.config import Settings

        field_info = Settings.model_fields["DB_CONNECT_MAX_RETRIES"]
        assert field_info.metadata is not None
        ge_constraint = [m for m in field_info.metadata if hasattr(m, "ge")]
        assert len(ge_constraint) > 0
        assert ge_constraint[0].ge == 0

    def test_backoff_base_rejects_zero(self) -> None:
        from pydantic import ValidationError

        from src.config import Settings

        with pytest.raises(ValidationError, match="DB_CONNECT_BACKOFF_BASE_SECONDS"):
            Settings(
                DB_CONNECT_BACKOFF_BASE_SECONDS=0,
                DATABASE_URL="postgresql+asyncpg://u:p@h:5432/db",
            )

    def test_backoff_base_rejects_negative(self) -> None:
        from pydantic import ValidationError

        from src.config import Settings

        with pytest.raises(ValidationError, match="DB_CONNECT_BACKOFF_BASE_SECONDS"):
            Settings(
                DB_CONNECT_BACKOFF_BASE_SECONDS=-0.5,
                DATABASE_URL="postgresql+asyncpg://u:p@h:5432/db",
            )


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


class TestDbosClientConfig:
    """AC#3/4: DBOS client engine uses NullPool with creator-based retry."""

    def test_dbos_client_engine_uses_nullpool_and_creator(self) -> None:
        with (
            patch("src.dbos_workflows.config.settings") as mock_settings,
            patch("src.dbos_workflows.config.sa.create_engine") as mock_create_engine,
            patch("src.dbos_workflows.config.DBOSClient") as mock_client_cls,
        ):
            mock_settings.DATABASE_URL = "postgresql+asyncpg://user:pass@localhost:5432/testdb"
            mock_settings.DB_CONNECT_MAX_RETRIES = 3
            mock_settings.DB_CONNECT_BACKOFF_BASE_SECONDS = 0.5
            mock_create_engine.return_value = MagicMock()
            mock_client_cls.return_value = MagicMock()

            from src.dbos_workflows.config import get_dbos_client, reset_dbos_client

            reset_dbos_client()
            try:
                get_dbos_client()
            finally:
                reset_dbos_client()

            call_kwargs = mock_create_engine.call_args[1]
            assert call_kwargs.get("poolclass") is NullPool
            assert "creator" in call_kwargs
            assert callable(call_kwargs["creator"])


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

    def test_pool_timeout_field_has_deprecation_warning(self) -> None:
        from src.config import Settings

        field_info = Settings.model_fields["DB_POOL_TIMEOUT"]
        assert (
            "deprecated" in (field_info.description or "").lower()
            or field_info.deprecated is not None
        )

    def test_pool_recycle_field_has_deprecation_warning(self) -> None:
        from src.config import Settings

        field_info = Settings.model_fields["DB_POOL_RECYCLE"]
        assert (
            "deprecated" in (field_info.description or "").lower()
            or field_info.deprecated is not None
        )
