import sys
from unittest.mock import MagicMock, patch

import pytest

MODULE = "src.startup_migrations"


def _make_subprocess_result(returncode=0, stdout="", stderr=""):
    result = MagicMock()
    result.returncode = returncode
    result.stdout = stdout
    result.stderr = stderr
    return result


def _make_mock_engine():
    mock_conn = MagicMock()
    mock_engine = MagicMock()
    mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
    mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)
    return mock_engine, mock_conn


def _execute_call_strings(mock_conn):
    return [str(c.args[0]) for c in mock_conn.execute.call_args_list]


@pytest.mark.asyncio
class TestRunStartupMigrationsServerSuccess:
    async def test_server_success_acquires_lock_runs_upgrade_releases_lock(self):
        mock_engine, mock_conn = _make_mock_engine()
        current_result = _make_subprocess_result(stdout="abc123 (head)\n")
        upgrade_result = _make_subprocess_result(stdout="Running upgrade abc123 -> def456")

        mock_settings = MagicMock()
        mock_settings.DATABASE_URL = "postgresql+asyncpg://user:pass@host/db"

        with (
            patch(f"{MODULE}.create_engine", return_value=mock_engine),
            patch(f"{MODULE}.get_settings", return_value=mock_settings),
            patch(f"{MODULE}.subprocess.run", side_effect=[current_result, upgrade_result]),
        ):
            from src.startup_migrations import run_startup_migrations

            await run_startup_migrations("full")

        sql_calls = _execute_call_strings(mock_conn)
        assert any("pg_advisory_lock" in s for s in sql_calls)
        assert any("pg_advisory_unlock" in s for s in sql_calls)

        lock_idx = next(
            i for i, s in enumerate(sql_calls) if "pg_advisory_lock(" in s and "unlock" not in s
        )
        unlock_idx = next(i for i, s in enumerate(sql_calls) if "pg_advisory_unlock" in s)
        assert lock_idx < unlock_idx

    async def test_server_success_captures_current_revision(self):
        mock_engine, _mock_conn = _make_mock_engine()
        current_result = _make_subprocess_result(stdout="abc123 (head)\n")
        upgrade_result = _make_subprocess_result(stdout="Applied migrations")

        mock_settings = MagicMock()
        mock_settings.DATABASE_URL = "postgresql+asyncpg://user:pass@host/db"

        with (
            patch(f"{MODULE}.create_engine", return_value=mock_engine),
            patch(f"{MODULE}.get_settings", return_value=mock_settings),
            patch(
                f"{MODULE}.subprocess.run", side_effect=[current_result, upgrade_result]
            ) as mock_run,
        ):
            from src.startup_migrations import run_startup_migrations

            await run_startup_migrations("full")

        first_call = mock_run.call_args_list[0]
        assert "current" in first_call.args[0]

        second_call = mock_run.call_args_list[1]
        assert "upgrade" in second_call.args[0]
        assert "head" in second_call.args[0]

    async def test_server_success_uses_sys_executable(self):
        mock_engine, _mock_conn = _make_mock_engine()
        current_result = _make_subprocess_result(stdout="abc123 (head)\n")
        upgrade_result = _make_subprocess_result(stdout="")

        mock_settings = MagicMock()
        mock_settings.DATABASE_URL = "postgresql+asyncpg://user:pass@host/db"

        with (
            patch(f"{MODULE}.create_engine", return_value=mock_engine),
            patch(f"{MODULE}.get_settings", return_value=mock_settings),
            patch(
                f"{MODULE}.subprocess.run", side_effect=[current_result, upgrade_result]
            ) as mock_run,
        ):
            from src.startup_migrations import run_startup_migrations

            await run_startup_migrations("full")

        for c in mock_run.call_args_list:
            assert c.args[0][0] == sys.executable

    async def test_server_success_logs_info(self):
        mock_engine, _mock_conn = _make_mock_engine()
        current_result = _make_subprocess_result(stdout="abc123 (head)\n")
        upgrade_result = _make_subprocess_result(stdout="Running upgrade abc123 -> def456")

        mock_settings = MagicMock()
        mock_settings.DATABASE_URL = "postgresql+asyncpg://user:pass@host/db"

        with (
            patch(f"{MODULE}.create_engine", return_value=mock_engine),
            patch(f"{MODULE}.get_settings", return_value=mock_settings),
            patch(f"{MODULE}.subprocess.run", side_effect=[current_result, upgrade_result]),
            patch(f"{MODULE}.logger") as mock_logger,
        ):
            from src.startup_migrations import run_startup_migrations

            await run_startup_migrations("full")

        info_messages = [str(c) for c in mock_logger.info.call_args_list]
        assert any("applied" in m.lower() or "success" in m.lower() for m in info_messages)


@pytest.mark.asyncio
class TestRunStartupMigrationsServerFailure:
    async def test_failure_triggers_rollback_to_pre_deploy_revision(self):
        mock_engine, _mock_conn = _make_mock_engine()
        current_result = _make_subprocess_result(stdout="abc123 (head)\n")
        upgrade_result = _make_subprocess_result(returncode=1, stderr="Migration error")
        downgrade_result = _make_subprocess_result(stdout="Downgraded")

        mock_settings = MagicMock()
        mock_settings.DATABASE_URL = "postgresql+asyncpg://user:pass@host/db"

        with (
            patch(f"{MODULE}.create_engine", return_value=mock_engine),
            patch(f"{MODULE}.get_settings", return_value=mock_settings),
            patch(
                f"{MODULE}.subprocess.run",
                side_effect=[current_result, upgrade_result, downgrade_result],
            ) as mock_run,
        ):
            from src.startup_migrations import run_startup_migrations

            await run_startup_migrations("full")

        downgrade_call = mock_run.call_args_list[2]
        assert "downgrade" in downgrade_call.args[0]
        assert "abc123" in downgrade_call.args[0]

    async def test_failure_logs_critical_with_alert_type(self):
        mock_engine, _mock_conn = _make_mock_engine()
        current_result = _make_subprocess_result(stdout="abc123 (head)\n")
        upgrade_result = _make_subprocess_result(returncode=1, stderr="boom")
        downgrade_result = _make_subprocess_result(stdout="ok")

        mock_settings = MagicMock()
        mock_settings.DATABASE_URL = "postgresql+asyncpg://user:pass@host/db"

        with (
            patch(f"{MODULE}.create_engine", return_value=mock_engine),
            patch(f"{MODULE}.get_settings", return_value=mock_settings),
            patch(
                f"{MODULE}.subprocess.run",
                side_effect=[current_result, upgrade_result, downgrade_result],
            ),
            patch(f"{MODULE}.logger") as mock_logger,
        ):
            from src.startup_migrations import run_startup_migrations

            await run_startup_migrations("full")

        mock_logger.critical.assert_called()
        critical_call = mock_logger.critical.call_args_list[0]
        extra = critical_call.kwargs.get("extra", {})
        assert extra.get("alert_type") == "migration_failure"

    async def test_failure_still_releases_lock(self):
        mock_engine, mock_conn = _make_mock_engine()
        current_result = _make_subprocess_result(stdout="abc123 (head)\n")
        upgrade_result = _make_subprocess_result(returncode=1, stderr="boom")
        downgrade_result = _make_subprocess_result(stdout="ok")

        mock_settings = MagicMock()
        mock_settings.DATABASE_URL = "postgresql+asyncpg://user:pass@host/db"

        with (
            patch(f"{MODULE}.create_engine", return_value=mock_engine),
            patch(f"{MODULE}.get_settings", return_value=mock_settings),
            patch(
                f"{MODULE}.subprocess.run",
                side_effect=[current_result, upgrade_result, downgrade_result],
            ),
        ):
            from src.startup_migrations import run_startup_migrations

            await run_startup_migrations("full")

        sql_calls = _execute_call_strings(mock_conn)
        assert any("pg_advisory_unlock" in s for s in sql_calls)

    async def test_rollback_failure_logs_second_critical(self):
        mock_engine, _mock_conn = _make_mock_engine()
        current_result = _make_subprocess_result(stdout="abc123 (head)\n")
        upgrade_result = _make_subprocess_result(returncode=1, stderr="upgrade failed")
        downgrade_result = _make_subprocess_result(returncode=1, stderr="downgrade also failed")

        mock_settings = MagicMock()
        mock_settings.DATABASE_URL = "postgresql+asyncpg://user:pass@host/db"

        with (
            patch(f"{MODULE}.create_engine", return_value=mock_engine),
            patch(f"{MODULE}.get_settings", return_value=mock_settings),
            patch(
                f"{MODULE}.subprocess.run",
                side_effect=[current_result, upgrade_result, downgrade_result],
            ),
            patch(f"{MODULE}.logger") as mock_logger,
        ):
            from src.startup_migrations import run_startup_migrations

            await run_startup_migrations("full")

        assert mock_logger.critical.call_count >= 2
        rollback_critical = mock_logger.critical.call_args_list[1]
        extra = rollback_critical.kwargs.get("extra", {})
        assert extra.get("alert_type") == "migration_rollback_failure"


@pytest.mark.asyncio
class TestRunStartupMigrationsWorker:
    async def test_worker_acquires_and_immediately_releases_lock(self):
        mock_engine, mock_conn = _make_mock_engine()

        mock_settings = MagicMock()
        mock_settings.DATABASE_URL = "postgresql+asyncpg://user:pass@host/db"

        with (
            patch(f"{MODULE}.create_engine", return_value=mock_engine),
            patch(f"{MODULE}.get_settings", return_value=mock_settings),
            patch(f"{MODULE}.subprocess.run") as mock_run,
        ):
            from src.startup_migrations import run_startup_migrations

            await run_startup_migrations("dbos_worker")

        mock_run.assert_not_called()

        sql_calls = _execute_call_strings(mock_conn)
        assert any("pg_advisory_lock(" in s and "unlock" not in s for s in sql_calls)
        assert any("pg_advisory_unlock" in s for s in sql_calls)

    async def test_worker_does_not_run_alembic_commands(self):
        mock_engine, _mock_conn = _make_mock_engine()

        mock_settings = MagicMock()
        mock_settings.DATABASE_URL = "postgresql+asyncpg://user:pass@host/db"

        with (
            patch(f"{MODULE}.create_engine", return_value=mock_engine),
            patch(f"{MODULE}.get_settings", return_value=mock_settings),
            patch(f"{MODULE}.subprocess.run") as mock_run,
        ):
            from src.startup_migrations import run_startup_migrations

            await run_startup_migrations("dbos_worker")

        mock_run.assert_not_called()


@pytest.mark.asyncio
class TestRunStartupMigrationsExceptionHandling:
    async def test_unexpected_exception_releases_lock(self):
        mock_engine = MagicMock()
        mock_engine.connect.return_value.__enter__ = MagicMock(
            side_effect=RuntimeError("connection failed")
        )
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)

        mock_unlock_conn = MagicMock()
        mock_unlock_engine = MagicMock()
        mock_unlock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_unlock_conn)
        mock_unlock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)

        mock_settings = MagicMock()
        mock_settings.DATABASE_URL = "postgresql+asyncpg://user:pass@host/db"

        call_count = 0
        engines = [mock_engine, mock_unlock_engine]

        def create_engine_side_effect(*args, **kwargs):
            nonlocal call_count
            if call_count < len(engines):
                eng = engines[call_count]
                call_count += 1
                return eng
            return mock_unlock_engine

        with (
            patch(f"{MODULE}.create_engine", side_effect=create_engine_side_effect),
            patch(f"{MODULE}.get_settings", return_value=mock_settings),
            patch(f"{MODULE}.logger") as mock_logger,
        ):
            from src.startup_migrations import run_startup_migrations

            await run_startup_migrations("full")

        mock_logger.critical.assert_called()
        critical_extra = mock_logger.critical.call_args_list[0].kwargs.get("extra", {})
        assert critical_extra.get("alert_type") == "migration_failure"

    async def test_unexpected_exception_logs_critical_with_alert_type(self):
        mock_engine, mock_conn = _make_mock_engine()
        mock_conn.execute.side_effect = RuntimeError("db error")

        mock_settings = MagicMock()
        mock_settings.DATABASE_URL = "postgresql+asyncpg://user:pass@host/db"

        with (
            patch(f"{MODULE}.create_engine", return_value=mock_engine),
            patch(f"{MODULE}.get_settings", return_value=mock_settings),
            patch(f"{MODULE}.logger") as mock_logger,
        ):
            from src.startup_migrations import run_startup_migrations

            await run_startup_migrations("full")

        mock_logger.critical.assert_called()
        critical_extra = mock_logger.critical.call_args_list[0].kwargs.get("extra", {})
        assert critical_extra.get("alert_type") == "migration_failure"


@pytest.mark.asyncio
class TestDatabaseUrlConversion:
    async def test_converts_asyncpg_url_to_sync(self):
        mock_engine, _mock_conn = _make_mock_engine()
        current_result = _make_subprocess_result(stdout="abc123 (head)\n")
        upgrade_result = _make_subprocess_result(stdout="")

        mock_settings = MagicMock()
        mock_settings.DATABASE_URL = "postgresql+asyncpg://user:pass@host:5432/mydb"

        with (
            patch(f"{MODULE}.create_engine", return_value=mock_engine) as mock_ce,
            patch(f"{MODULE}.get_settings", return_value=mock_settings),
            patch(f"{MODULE}.subprocess.run", side_effect=[current_result, upgrade_result]),
        ):
            from src.startup_migrations import run_startup_migrations

            await run_startup_migrations("full")

        db_url_arg = mock_ce.call_args.args[0]
        assert db_url_arg == "postgresql://user:pass@host:5432/mydb"
        assert "asyncpg" not in db_url_arg


@pytest.mark.asyncio
class TestMigrationLockId:
    async def test_uses_expected_lock_id(self):
        mock_engine, mock_conn = _make_mock_engine()

        mock_settings = MagicMock()
        mock_settings.DATABASE_URL = "postgresql+asyncpg://user:pass@host/db"

        with (
            patch(f"{MODULE}.create_engine", return_value=mock_engine),
            patch(f"{MODULE}.get_settings", return_value=mock_settings),
            patch(f"{MODULE}.subprocess.run"),
        ):
            from src.startup_migrations import run_startup_migrations

            await run_startup_migrations("dbos_worker")

        sql_calls = _execute_call_strings(mock_conn)
        assert any("1847334512" in s for s in sql_calls)


@pytest.mark.asyncio
class TestNoMigrationsPending:
    async def test_no_pending_migrations_logs_info(self):
        mock_engine, _mock_conn = _make_mock_engine()
        current_result = _make_subprocess_result(stdout="abc123 (head)\n")
        upgrade_result = _make_subprocess_result(stdout="")

        mock_settings = MagicMock()
        mock_settings.DATABASE_URL = "postgresql+asyncpg://user:pass@host/db"

        with (
            patch(f"{MODULE}.create_engine", return_value=mock_engine),
            patch(f"{MODULE}.get_settings", return_value=mock_settings),
            patch(f"{MODULE}.subprocess.run", side_effect=[current_result, upgrade_result]),
            patch(f"{MODULE}.logger") as mock_logger,
        ):
            from src.startup_migrations import run_startup_migrations

            await run_startup_migrations("full")

        info_messages = [str(c) for c in mock_logger.info.call_args_list]
        assert any("no pending" in m.lower() for m in info_messages)


@pytest.mark.asyncio
class TestBaseRevisionFallback:
    async def test_empty_current_rev_uses_base(self):
        mock_engine, _mock_conn = _make_mock_engine()
        current_result = _make_subprocess_result(stdout="")
        upgrade_result = _make_subprocess_result(returncode=1, stderr="fail")
        downgrade_result = _make_subprocess_result(stdout="ok")

        mock_settings = MagicMock()
        mock_settings.DATABASE_URL = "postgresql+asyncpg://user:pass@host/db"

        with (
            patch(f"{MODULE}.create_engine", return_value=mock_engine),
            patch(f"{MODULE}.get_settings", return_value=mock_settings),
            patch(
                f"{MODULE}.subprocess.run",
                side_effect=[current_result, upgrade_result, downgrade_result],
            ) as mock_run,
        ):
            from src.startup_migrations import run_startup_migrations

            await run_startup_migrations("full")

        downgrade_call = mock_run.call_args_list[2]
        assert "base" in downgrade_call.args[0]
