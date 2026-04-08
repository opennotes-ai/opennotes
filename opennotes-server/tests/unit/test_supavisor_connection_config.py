"""Tests for QueuePool-based connection configuration (task-1253).

Verifies:
- Main engine uses QueuePool with config values (not NullPool)
- statement_cache_size=0 in connect_args (Supavisor transaction mode)
- No async_creator or connection_retry wrapper
- Pool parameters wired from config
"""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.pool import QueuePool

pytestmark = pytest.mark.unit


class TestDatabaseEngineQueuePool:
    """AC#2: Engine uses QueuePool with pool_size, max_overflow, pool_pre_ping, pool_recycle."""

    @pytest.mark.asyncio
    async def test_create_engine_uses_queue_pool(self) -> None:
        from src.database import _create_engine

        with patch("src.database.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/testdb",
                DEBUG=False,
                DB_POOL_SIZE=5,
                DB_POOL_MAX_OVERFLOW=5,
                DB_POOL_TIMEOUT=30,
                DB_POOL_RECYCLE=1800,
            )
            engine = _create_engine()
            try:
                assert isinstance(engine.sync_engine.pool, QueuePool)
            finally:
                await engine.dispose()

    def test_create_engine_passes_pool_kwargs(self) -> None:
        with patch("src.database.create_async_engine") as mock_create:
            mock_create.return_value = MagicMock()

            from src.database import _create_engine

            with patch("src.database.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(
                    DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/testdb",
                    DEBUG=False,
                    DB_POOL_SIZE=5,
                    DB_POOL_MAX_OVERFLOW=5,
                    DB_POOL_TIMEOUT=30,
                    DB_POOL_RECYCLE=1800,
                )
                _create_engine()

            settings = mock_settings.return_value
            call_kwargs = mock_create.call_args[1]
            assert call_kwargs["pool_size"] == settings.DB_POOL_SIZE
            assert call_kwargs["max_overflow"] == settings.DB_POOL_MAX_OVERFLOW
            assert call_kwargs["pool_timeout"] == settings.DB_POOL_TIMEOUT
            assert call_kwargs["pool_recycle"] == settings.DB_POOL_RECYCLE
            assert call_kwargs["pool_pre_ping"] is True

    def test_create_engine_does_not_use_null_pool(self) -> None:
        with patch("src.database.create_async_engine") as mock_create:
            mock_create.return_value = MagicMock()

            from src.database import _create_engine

            with patch("src.database.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(
                    DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/testdb",
                    DEBUG=False,
                    DB_POOL_SIZE=5,
                    DB_POOL_MAX_OVERFLOW=5,
                    DB_POOL_TIMEOUT=30,
                    DB_POOL_RECYCLE=1800,
                )
                _create_engine()

            call_kwargs = mock_create.call_args[1]
            assert "poolclass" not in call_kwargs


class TestStatementCacheDisabled:
    """AC#3: statement_cache_size=0 and prepared_statement_cache_size=0 in connect_args."""

    def test_connect_args_disables_statement_cache(self) -> None:
        with patch("src.database.create_async_engine") as mock_create:
            mock_create.return_value = MagicMock()

            from src.database import _create_engine

            with patch("src.database.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(
                    DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/testdb",
                    DEBUG=False,
                    DB_POOL_SIZE=5,
                    DB_POOL_MAX_OVERFLOW=5,
                    DB_POOL_TIMEOUT=30,
                    DB_POOL_RECYCLE=1800,
                )
                _create_engine()

            call_kwargs = mock_create.call_args[1]
            assert "connect_args" in call_kwargs
            assert call_kwargs["connect_args"]["statement_cache_size"] == 0
            assert call_kwargs["connect_args"]["prepared_statement_cache_size"] == 0


class TestNoAsyncCreatorOrRetry:
    """AC#4: async_creator and connection_retry wrapper removed."""

    def test_no_async_creator_in_engine(self) -> None:
        with patch("src.database.create_async_engine") as mock_create:
            mock_create.return_value = MagicMock()

            from src.database import _create_engine

            with patch("src.database.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(
                    DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/testdb",
                    DEBUG=False,
                    DB_POOL_SIZE=5,
                    DB_POOL_MAX_OVERFLOW=5,
                    DB_POOL_TIMEOUT=30,
                    DB_POOL_RECYCLE=1800,
                )
                _create_engine()

            call_kwargs = mock_create.call_args[1]
            assert "async_creator" not in call_kwargs


class TestSupavisorConnectArgsConstant:
    """Verify SUPAVISOR_CONNECT_ARGS constant contains all required keys."""

    def test_constant_has_statement_cache_size(self) -> None:
        from src.database import SUPAVISOR_CONNECT_ARGS

        assert SUPAVISOR_CONNECT_ARGS["statement_cache_size"] == 0

    def test_constant_has_prepared_statement_cache_size(self) -> None:
        from src.database import SUPAVISOR_CONNECT_ARGS

        assert SUPAVISOR_CONNECT_ARGS["prepared_statement_cache_size"] == 0

    def test_constant_has_prepared_statement_name_func(self) -> None:
        from src.database import SUPAVISOR_CONNECT_ARGS

        func = SUPAVISOR_CONNECT_ARGS["prepared_statement_name_func"]
        assert callable(func)
        assert func() == ""

    def test_constant_has_exactly_three_keys(self) -> None:
        from src.database import SUPAVISOR_CONNECT_ARGS

        assert len(SUPAVISOR_CONNECT_ARGS) == 3

    def test_constant_is_immutable(self) -> None:
        from src.database import SUPAVISOR_CONNECT_ARGS

        with pytest.raises(TypeError):
            SUPAVISOR_CONNECT_ARGS["new_key"] = "value"  # type: ignore[index]


class TestAnonymousPreparedStatements:
    """Verify prepared_statement_name_func returns empty string (anonymous statements)."""

    def test_connect_args_has_prepared_statement_name_func(self) -> None:
        with patch("src.database.create_async_engine") as mock_create:
            mock_create.return_value = MagicMock()

            from src.database import _create_engine

            with patch("src.database.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(
                    DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/testdb",
                    DEBUG=False,
                    DB_POOL_SIZE=5,
                    DB_POOL_MAX_OVERFLOW=5,
                    DB_POOL_TIMEOUT=30,
                    DB_POOL_RECYCLE=1800,
                )
                _create_engine()

            call_kwargs = mock_create.call_args[1]
            func = call_kwargs["connect_args"]["prepared_statement_name_func"]
            assert callable(func)
            assert func() == ""


class TestPoolConfigNotDeprecated:
    """AC#7: DB_POOL_* config fields un-deprecated and wired to QueuePool."""

    def test_pool_size_field_not_deprecated(self) -> None:
        from src.config import Settings

        field_info = Settings.model_fields["DB_POOL_SIZE"]
        assert field_info.deprecated is None or field_info.deprecated == ""

    def test_pool_max_overflow_field_not_deprecated(self) -> None:
        from src.config import Settings

        field_info = Settings.model_fields["DB_POOL_MAX_OVERFLOW"]
        assert field_info.deprecated is None or field_info.deprecated == ""

    def test_pool_timeout_field_not_deprecated(self) -> None:
        from src.config import Settings

        field_info = Settings.model_fields["DB_POOL_TIMEOUT"]
        assert field_info.deprecated is None or field_info.deprecated == ""

    def test_pool_recycle_field_not_deprecated(self) -> None:
        from src.config import Settings

        field_info = Settings.model_fields["DB_POOL_RECYCLE"]
        assert field_info.deprecated is None or field_info.deprecated == ""

    def test_connect_retry_fields_removed(self) -> None:
        from src.config import Settings

        assert "DB_CONNECT_MAX_RETRIES" not in Settings.model_fields
        assert "DB_CONNECT_BACKOFF_BASE_SECONDS" not in Settings.model_fields
