from unittest.mock import MagicMock, patch

import pytest

MODULE_STARTUP = "src.startup_migrations"
MODULE_DBOS = "src.dbos_workflows.config"

pytestmark = pytest.mark.unit


class TestStartupMigrationsRetryWiring:
    def test_engine_creation_uses_sync_connect_with_retry_creator(self):
        mock_engine, mock_conn = MagicMock(), MagicMock()
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)

        mock_settings = MagicMock()
        mock_settings.DATABASE_URL = "postgresql+asyncpg://user:pass@host:5432/db"
        mock_settings.DB_CONNECT_MAX_RETRIES = 3
        mock_settings.DB_CONNECT_BACKOFF_BASE_SECONDS = 0.5

        with (
            patch(f"{MODULE_STARTUP}.create_engine", return_value=mock_engine) as mock_ce,
            patch(f"{MODULE_STARTUP}.get_settings", return_value=mock_settings),
            patch(f"{MODULE_STARTUP}.sync_connect_with_retry") as mock_retry,
        ):
            mock_retry.return_value = MagicMock()
            from src.startup_migrations import _run_migrations_sync

            _run_migrations_sync(is_worker=True)

        mock_retry.assert_called_once()
        _, retry_kwargs = mock_retry.call_args
        assert retry_kwargs["max_retries"] == 3
        assert retry_kwargs["backoff_base"] == 0.5

        ce_kwargs = mock_ce.call_args.kwargs
        assert "creator" in ce_kwargs
        assert ce_kwargs["creator"] is mock_retry.return_value

    def test_engine_creation_no_longer_uses_connect_args(self):
        mock_engine, mock_conn = MagicMock(), MagicMock()
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)

        mock_settings = MagicMock()
        mock_settings.DATABASE_URL = "postgresql+asyncpg://user:pass@host:5432/db"
        mock_settings.DB_CONNECT_MAX_RETRIES = 3
        mock_settings.DB_CONNECT_BACKOFF_BASE_SECONDS = 0.5

        with (
            patch(f"{MODULE_STARTUP}.create_engine", return_value=mock_engine) as mock_ce,
            patch(f"{MODULE_STARTUP}.get_settings", return_value=mock_settings),
            patch(f"{MODULE_STARTUP}.sync_connect_with_retry", return_value=MagicMock()),
        ):
            from src.startup_migrations import _run_migrations_sync

            _run_migrations_sync(is_worker=True)

        ce_kwargs = mock_ce.call_args.kwargs
        assert "connect_args" not in ce_kwargs


class TestDbosClientRetryWiring:
    def test_get_dbos_client_engine_uses_sync_connect_with_retry(self):
        with (
            patch(f"{MODULE_DBOS}.DBOSClient") as mock_client_class,
            patch(f"{MODULE_DBOS}.sa.create_engine") as mock_create_engine,
            patch(f"{MODULE_DBOS}.settings") as mock_settings,
            patch(f"{MODULE_DBOS}.sync_connect_with_retry") as mock_retry,
        ):
            mock_settings.DATABASE_URL = "postgresql+asyncpg://user:pass@host/db"
            mock_settings.DB_CONNECT_MAX_RETRIES = 5
            mock_settings.DB_CONNECT_BACKOFF_BASE_SECONDS = 1.0
            mock_create_engine.return_value = MagicMock()
            mock_client_class.return_value = MagicMock()
            mock_retry.return_value = MagicMock()

            from src.dbos_workflows.config import get_dbos_client, reset_dbos_client

            reset_dbos_client()
            try:
                get_dbos_client()
            finally:
                reset_dbos_client()

        mock_retry.assert_called_once()
        _, retry_kwargs = mock_retry.call_args
        assert retry_kwargs["max_retries"] == 5
        assert retry_kwargs["backoff_base"] == 1.0

        ce_kwargs = mock_create_engine.call_args.kwargs
        assert "creator" in ce_kwargs
        assert ce_kwargs["creator"] is mock_retry.return_value

    def test_get_dbos_client_engine_no_longer_uses_connect_args(self):
        with (
            patch(f"{MODULE_DBOS}.DBOSClient") as mock_client_class,
            patch(f"{MODULE_DBOS}.sa.create_engine") as mock_create_engine,
            patch(f"{MODULE_DBOS}.settings") as mock_settings,
            patch(f"{MODULE_DBOS}.sync_connect_with_retry", return_value=MagicMock()),
        ):
            mock_settings.DATABASE_URL = "postgresql+asyncpg://user:pass@host/db"
            mock_settings.DB_CONNECT_MAX_RETRIES = 3
            mock_settings.DB_CONNECT_BACKOFF_BASE_SECONDS = 0.5
            mock_create_engine.return_value = MagicMock()
            mock_client_class.return_value = MagicMock()

            from src.dbos_workflows.config import get_dbos_client, reset_dbos_client

            reset_dbos_client()
            try:
                get_dbos_client()
            finally:
                reset_dbos_client()

        ce_kwargs = mock_create_engine.call_args.kwargs
        assert "connect_args" not in ce_kwargs


class TestValidateDbosConnectionRetryWiring:
    def test_validate_uses_sync_connect_with_retry(self):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (True,)
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        with (
            patch(f"{MODULE_DBOS}.settings") as mock_settings,
            patch(f"{MODULE_DBOS}.sync_connect_with_retry") as mock_retry,
        ):
            mock_settings.DATABASE_URL = "postgresql+asyncpg://user:pass@host/db"
            mock_settings.DBOS_APP_NAME = "test"
            mock_settings.VERSION = "0.0.0"
            mock_settings.ENVIRONMENT = "test"
            mock_settings.OTLP_ENDPOINT = None
            mock_settings.DB_CONNECT_MAX_RETRIES = 3
            mock_settings.DB_CONNECT_BACKOFF_BASE_SECONDS = 0.5

            mock_connect_fn = MagicMock(return_value=mock_conn)
            mock_retry.return_value = mock_connect_fn

            from src.dbos_workflows.config import validate_dbos_connection

            result = validate_dbos_connection()

        assert result is True
        mock_retry.assert_called_once()
        _, retry_kwargs = mock_retry.call_args
        assert retry_kwargs["max_retries"] == 3
        assert retry_kwargs["backoff_base"] == 0.5
        mock_connect_fn.assert_called_once()

    def test_validate_retries_transient_dns_error(self):
        from src.common.connection_retry import sync_connect_with_retry

        call_count = 0
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (True,)
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        def flaky_connect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                import psycopg

                raise psycopg.OperationalError("connection failed: could not translate host name")
            return mock_conn

        with (
            patch(f"{MODULE_DBOS}.settings") as mock_settings,
            patch(f"{MODULE_DBOS}.sync_connect_with_retry", side_effect=sync_connect_with_retry),
            patch("psycopg.connect", side_effect=flaky_connect),
        ):
            mock_settings.DATABASE_URL = "postgresql+asyncpg://user:pass@host/db"
            mock_settings.DBOS_APP_NAME = "test"
            mock_settings.VERSION = "0.0.0"
            mock_settings.ENVIRONMENT = "test"
            mock_settings.OTLP_ENDPOINT = None
            mock_settings.DB_CONNECT_MAX_RETRIES = 3
            mock_settings.DB_CONNECT_BACKOFF_BASE_SECONDS = 0.01

            from src.dbos_workflows.config import validate_dbos_connection

            result = validate_dbos_connection()

        assert result is True
        assert call_count == 3
