import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest

MODULE = "src.startup_migrations"
TEST_SYNC_URL = "postgresql://test:test@testhost:5432/testdb"


def _make_subprocess_result(returncode=0, stdout="", stderr=""):
    result = MagicMock()
    result.returncode = returncode
    result.stdout = stdout
    result.stderr = stderr
    return result


def _make_mock_engine(lock_acquired=True):
    mock_conn = MagicMock()
    mock_engine = MagicMock()
    mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
    mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)

    lock_result = MagicMock()
    lock_result.scalar.return_value = lock_acquired

    original_execute = mock_conn.execute

    def execute_side_effect(stmt):
        stmt_str = str(stmt) if not isinstance(stmt, str) else stmt
        if "pg_try_advisory_lock" in str(stmt_str):
            return lock_result
        return original_execute(stmt)

    mock_conn.execute = MagicMock(side_effect=execute_side_effect)
    return mock_engine, mock_conn


def _make_mock_settings():
    mock_settings = MagicMock()
    mock_settings.SKIP_MIGRATIONS = False
    return mock_settings


def _execute_call_strings(mock_conn):
    return [str(c.args[0]) for c in mock_conn.execute.call_args_list]


@pytest.mark.asyncio
class TestRunStartupMigrationsServerSuccess:
    async def test_server_success_acquires_lock_runs_upgrade_releases_lock(self):
        mock_engine, mock_conn = _make_mock_engine()
        current_result = _make_subprocess_result(stdout="abc123 (head)\n")
        upgrade_result = _make_subprocess_result(stdout="Running upgrade abc123 -> def456")

        mock_settings = _make_mock_settings()

        with (
            patch(f"{MODULE}._get_direct_sync_url", return_value=TEST_SYNC_URL),
            patch(f"{MODULE}.create_engine", return_value=mock_engine),
            patch(f"{MODULE}.get_settings", return_value=mock_settings),
            patch(f"{MODULE}.subprocess.run", side_effect=[current_result, upgrade_result]),
        ):
            from src.startup_migrations import run_startup_migrations

            await run_startup_migrations("full")

        sql_calls = _execute_call_strings(mock_conn)
        assert any("pg_try_advisory_lock" in s for s in sql_calls)
        assert any("pg_advisory_unlock" in s for s in sql_calls)

        lock_idx = next(i for i, s in enumerate(sql_calls) if "pg_try_advisory_lock" in s)
        unlock_idx = next(i for i, s in enumerate(sql_calls) if "pg_advisory_unlock" in s)
        assert lock_idx < unlock_idx

    async def test_server_success_captures_current_revision(self):
        mock_engine, _mock_conn = _make_mock_engine()
        current_result = _make_subprocess_result(stdout="abc123 (head)\n")
        upgrade_result = _make_subprocess_result(stdout="Applied migrations")

        mock_settings = _make_mock_settings()

        with (
            patch(f"{MODULE}._get_direct_sync_url", return_value=TEST_SYNC_URL),
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

        mock_settings = _make_mock_settings()

        with (
            patch(f"{MODULE}._get_direct_sync_url", return_value=TEST_SYNC_URL),
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

        mock_settings = _make_mock_settings()

        with (
            patch(f"{MODULE}._get_direct_sync_url", return_value=TEST_SYNC_URL),
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

        mock_settings = _make_mock_settings()

        with (
            patch(f"{MODULE}._get_direct_sync_url", return_value=TEST_SYNC_URL),
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

        mock_settings = _make_mock_settings()

        with (
            patch(f"{MODULE}._get_direct_sync_url", return_value=TEST_SYNC_URL),
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

        mock_settings = _make_mock_settings()

        with (
            patch(f"{MODULE}._get_direct_sync_url", return_value=TEST_SYNC_URL),
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

        mock_settings = _make_mock_settings()

        with (
            patch(f"{MODULE}._get_direct_sync_url", return_value=TEST_SYNC_URL),
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

        mock_settings = _make_mock_settings()

        with (
            patch(f"{MODULE}._get_direct_sync_url", return_value=TEST_SYNC_URL),
            patch(f"{MODULE}.create_engine", return_value=mock_engine),
            patch(f"{MODULE}.get_settings", return_value=mock_settings),
            patch(f"{MODULE}.subprocess.run") as mock_run,
        ):
            from src.startup_migrations import run_startup_migrations

            await run_startup_migrations("dbos_worker")

        mock_run.assert_not_called()

        sql_calls = _execute_call_strings(mock_conn)
        assert any("pg_try_advisory_lock" in s for s in sql_calls)
        assert any("pg_advisory_unlock" in s for s in sql_calls)

    async def test_worker_does_not_run_alembic_commands(self):
        mock_engine, _mock_conn = _make_mock_engine()

        mock_settings = _make_mock_settings()

        with (
            patch(f"{MODULE}._get_direct_sync_url", return_value=TEST_SYNC_URL),
            patch(f"{MODULE}.create_engine", return_value=mock_engine),
            patch(f"{MODULE}.get_settings", return_value=mock_settings),
            patch(f"{MODULE}.subprocess.run") as mock_run,
        ):
            from src.startup_migrations import run_startup_migrations

            await run_startup_migrations("dbos_worker")

        mock_run.assert_not_called()


@pytest.mark.asyncio
class TestRunStartupMigrationsExceptionHandling:
    async def test_unexpected_exception_logs_critical_and_reraises(self):
        mock_engine = MagicMock()
        mock_engine.connect.return_value.__enter__ = MagicMock(
            side_effect=RuntimeError("connection failed")
        )
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)

        mock_settings = _make_mock_settings()

        from src.startup_migrations import run_startup_migrations

        with (
            patch(f"{MODULE}._get_direct_sync_url", return_value=TEST_SYNC_URL),
            patch(f"{MODULE}.create_engine", return_value=mock_engine),
            patch(f"{MODULE}.get_settings", return_value=mock_settings),
            patch(f"{MODULE}.logger") as mock_logger,
            pytest.raises(RuntimeError, match="connection failed"),
        ):
            await run_startup_migrations("full")

        mock_logger.critical.assert_called()
        critical_extra = mock_logger.critical.call_args_list[0].kwargs.get("extra", {})
        assert critical_extra.get("alert_type") == "migration_failure"

    async def test_unexpected_exception_logs_critical_with_alert_type(self):
        mock_engine, mock_conn = _make_mock_engine()
        mock_conn.execute.side_effect = RuntimeError("db error")

        mock_settings = _make_mock_settings()

        from src.startup_migrations import run_startup_migrations

        with (
            patch(f"{MODULE}._get_direct_sync_url", return_value=TEST_SYNC_URL),
            patch(f"{MODULE}.create_engine", return_value=mock_engine),
            patch(f"{MODULE}.get_settings", return_value=mock_settings),
            patch(f"{MODULE}.logger") as mock_logger,
            pytest.raises(RuntimeError, match="db error"),
        ):
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

        mock_settings = _make_mock_settings()

        with (
            patch(f"{MODULE}.create_engine", return_value=mock_engine) as mock_ce,
            patch(
                f"{MODULE}._get_direct_sync_url",
                return_value="postgresql://user:pass@host:5432/mydb",
            ),
            patch(f"{MODULE}.get_settings", return_value=mock_settings),
            patch(f"{MODULE}.subprocess.run", side_effect=[current_result, upgrade_result]),
        ):
            from src.startup_migrations import run_startup_migrations

            await run_startup_migrations("full")

        db_url_arg = mock_ce.call_args.args[0]
        assert db_url_arg == "postgresql://user:pass@host:5432/mydb"
        assert "asyncpg" not in db_url_arg

    async def test_uses_direct_url_when_set(self):
        mock_engine, _mock_conn = _make_mock_engine()
        current_result = _make_subprocess_result(stdout="abc123 (head)\n")
        upgrade_result = _make_subprocess_result(stdout="")

        with (
            patch(f"{MODULE}.create_engine", return_value=mock_engine) as mock_ce,
            patch(
                f"{MODULE}._get_direct_sync_url",
                return_value="postgresql://user:pass@direct:5432/mydb",
            ),
            patch(f"{MODULE}.get_settings", return_value=_make_mock_settings()),
            patch(f"{MODULE}.subprocess.run", side_effect=[current_result, upgrade_result]),
        ):
            from src.startup_migrations import run_startup_migrations

            await run_startup_migrations("full")

        db_url_arg = mock_ce.call_args.args[0]
        assert db_url_arg == "postgresql://user:pass@direct:5432/mydb"

    async def test_direct_url_asyncpg_prefix_stripped(self):
        mock_engine, _mock_conn = _make_mock_engine()
        current_result = _make_subprocess_result(stdout="abc123 (head)\n")
        upgrade_result = _make_subprocess_result(stdout="")

        with (
            patch(f"{MODULE}.create_engine", return_value=mock_engine) as mock_ce,
            patch(
                f"{MODULE}._get_direct_sync_url",
                return_value="postgresql://user:pass@direct:5432/mydb",
            ),
            patch(f"{MODULE}.get_settings", return_value=_make_mock_settings()),
            patch(f"{MODULE}.subprocess.run", side_effect=[current_result, upgrade_result]),
        ):
            from src.startup_migrations import run_startup_migrations

            await run_startup_migrations("full")

        db_url_arg = mock_ce.call_args.args[0]
        assert db_url_arg == "postgresql://user:pass@direct:5432/mydb"
        assert "asyncpg" not in db_url_arg

    async def test_subprocess_env_has_asyncpg_database_url(self):
        mock_engine, _mock_conn = _make_mock_engine()
        current_result = _make_subprocess_result(stdout="abc123 (head)\n")
        upgrade_result = _make_subprocess_result(stdout="")

        with (
            patch(f"{MODULE}.create_engine", return_value=mock_engine),
            patch(
                f"{MODULE}._get_direct_sync_url",
                return_value="postgresql://user:pass@direct:5432/mydb",
            ),
            patch(f"{MODULE}.get_settings", return_value=_make_mock_settings()),
            patch(
                f"{MODULE}.subprocess.run", side_effect=[current_result, upgrade_result]
            ) as mock_run,
        ):
            from src.startup_migrations import run_startup_migrations

            await run_startup_migrations("full")

        for c in mock_run.call_args_list:
            env = c.kwargs.get("env", {})
            assert env.get("DATABASE_URL") == "postgresql+asyncpg://user:pass@direct:5432/mydb"


@pytest.mark.asyncio
class TestMigrationLockId:
    async def test_uses_expected_lock_id(self):
        mock_engine, mock_conn = _make_mock_engine()

        mock_settings = _make_mock_settings()

        with (
            patch(f"{MODULE}._get_direct_sync_url", return_value=TEST_SYNC_URL),
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

        mock_settings = _make_mock_settings()

        with (
            patch(f"{MODULE}._get_direct_sync_url", return_value=TEST_SYNC_URL),
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

        mock_settings = _make_mock_settings()

        with (
            patch(f"{MODULE}._get_direct_sync_url", return_value=TEST_SYNC_URL),
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


@pytest.mark.asyncio
class TestSubprocessTimeout:
    async def test_subprocess_run_calls_have_timeout(self):
        mock_engine, _mock_conn = _make_mock_engine()
        current_result = _make_subprocess_result(stdout="abc123 (head)\n")
        upgrade_result = _make_subprocess_result(stdout="")

        mock_settings = _make_mock_settings()

        with (
            patch(f"{MODULE}._get_direct_sync_url", return_value=TEST_SYNC_URL),
            patch(f"{MODULE}.create_engine", return_value=mock_engine),
            patch(f"{MODULE}.get_settings", return_value=mock_settings),
            patch(
                f"{MODULE}.subprocess.run", side_effect=[current_result, upgrade_result]
            ) as mock_run,
        ):
            from src.startup_migrations import run_startup_migrations

            await run_startup_migrations("full")

        for c in mock_run.call_args_list:
            assert c.kwargs.get("timeout") == 300

    async def test_alembic_current_timeout_logs_critical_and_releases_lock(self):
        mock_engine, mock_conn = _make_mock_engine()

        mock_settings = _make_mock_settings()

        with (
            patch(f"{MODULE}._get_direct_sync_url", return_value=TEST_SYNC_URL),
            patch(f"{MODULE}.create_engine", return_value=mock_engine),
            patch(f"{MODULE}.get_settings", return_value=mock_settings),
            patch(
                f"{MODULE}.subprocess.run",
                side_effect=subprocess.TimeoutExpired(cmd="alembic current", timeout=300),
            ),
            patch(f"{MODULE}.logger") as mock_logger,
        ):
            from src.startup_migrations import run_startup_migrations

            await run_startup_migrations("full")

        mock_logger.critical.assert_called_once()
        assert "timed out" in str(mock_logger.critical.call_args)

        sql_calls = _execute_call_strings(mock_conn)
        assert any("pg_advisory_unlock" in s for s in sql_calls)

    async def test_alembic_downgrade_timeout_logs_critical_and_releases_lock(self):
        mock_engine, mock_conn = _make_mock_engine()
        current_result = _make_subprocess_result(stdout="abc123 (head)\n")
        upgrade_result = _make_subprocess_result(returncode=1, stderr="upgrade failed")

        mock_settings = _make_mock_settings()

        with (
            patch(f"{MODULE}._get_direct_sync_url", return_value=TEST_SYNC_URL),
            patch(f"{MODULE}.create_engine", return_value=mock_engine),
            patch(f"{MODULE}.get_settings", return_value=mock_settings),
            patch(
                f"{MODULE}.subprocess.run",
                side_effect=[
                    current_result,
                    upgrade_result,
                    subprocess.TimeoutExpired(cmd="alembic downgrade", timeout=300),
                ],
            ),
            patch(f"{MODULE}.logger") as mock_logger,
        ):
            from src.startup_migrations import run_startup_migrations

            await run_startup_migrations("full")

        critical_calls = mock_logger.critical.call_args_list
        assert any("downgrade timed out" in str(c) for c in critical_calls)
        timeout_call = next(c for c in critical_calls if "downgrade timed out" in str(c))
        extra = timeout_call.kwargs.get("extra", {})
        assert extra.get("alert_type") == "migration_rollback_timeout"

        sql_calls = _execute_call_strings(mock_conn)
        assert any("pg_advisory_unlock" in s for s in sql_calls)

    async def test_alembic_upgrade_timeout_logs_critical_and_releases_lock(self):
        mock_engine, mock_conn = _make_mock_engine()
        current_result = _make_subprocess_result(stdout="abc123 (head)\n")

        mock_settings = _make_mock_settings()

        with (
            patch(f"{MODULE}._get_direct_sync_url", return_value=TEST_SYNC_URL),
            patch(f"{MODULE}.create_engine", return_value=mock_engine),
            patch(f"{MODULE}.get_settings", return_value=mock_settings),
            patch(
                f"{MODULE}.subprocess.run",
                side_effect=[
                    current_result,
                    subprocess.TimeoutExpired(cmd="alembic upgrade", timeout=300),
                ],
            ),
            patch(f"{MODULE}.logger") as mock_logger,
        ):
            from src.startup_migrations import run_startup_migrations

            await run_startup_migrations("full")

        mock_logger.critical.assert_called_once()
        assert "timed out" in str(mock_logger.critical.call_args)

        sql_calls = _execute_call_strings(mock_conn)
        assert any("pg_advisory_unlock" in s for s in sql_calls)


@pytest.mark.asyncio
class TestAlembicCurrentReturncode:
    async def test_nonzero_returncode_aborts_migration(self):
        mock_engine, mock_conn = _make_mock_engine()
        current_result = _make_subprocess_result(returncode=1, stderr="alembic error")

        mock_settings = _make_mock_settings()

        with (
            patch(f"{MODULE}._get_direct_sync_url", return_value=TEST_SYNC_URL),
            patch(f"{MODULE}.create_engine", return_value=mock_engine),
            patch(f"{MODULE}.get_settings", return_value=mock_settings),
            patch(f"{MODULE}.subprocess.run", return_value=current_result) as mock_run,
            patch(f"{MODULE}.logger") as mock_logger,
        ):
            from src.startup_migrations import run_startup_migrations

            await run_startup_migrations("full")

        assert mock_run.call_count == 1
        mock_logger.critical.assert_called_once()
        assert "alembic current failed" in str(mock_logger.critical.call_args)

        sql_calls = _execute_call_strings(mock_conn)
        assert any("pg_advisory_unlock" in s for s in sql_calls)


@pytest.mark.asyncio
class TestMultiHeadParsing:
    async def test_multi_head_output_parsed_correctly(self):
        mock_engine, _mock_conn = _make_mock_engine()
        current_result = _make_subprocess_result(stdout="abc123 (head)\ndef456 (head)\n")
        upgrade_result = _make_subprocess_result(returncode=1, stderr="fail")
        downgrade_result = _make_subprocess_result(stdout="ok")

        mock_settings = _make_mock_settings()

        with (
            patch(f"{MODULE}._get_direct_sync_url", return_value=TEST_SYNC_URL),
            patch(f"{MODULE}.create_engine", return_value=mock_engine),
            patch(f"{MODULE}.get_settings", return_value=mock_settings),
            patch(
                f"{MODULE}.subprocess.run",
                side_effect=[current_result, upgrade_result, downgrade_result],
            ) as mock_run,
            patch(f"{MODULE}.logger") as mock_logger,
        ):
            from src.startup_migrations import run_startup_migrations

            await run_startup_migrations("full")

        downgrade_call = mock_run.call_args_list[2]
        assert "abc123" in downgrade_call.args[0]

        info_calls = [str(c) for c in mock_logger.info.call_args_list]
        assert any("abc123" in s and "def456" in s for s in info_calls)

    async def test_single_head_output_parsed_correctly(self):
        from src.startup_migrations import _parse_current_revision

        result = _parse_current_revision("abc123 (head)\n")
        assert result == ["abc123"]

    async def test_multi_head_output_returns_all_revisions(self):
        from src.startup_migrations import _parse_current_revision

        result = _parse_current_revision("abc123 (head)\ndef456 (head)\n")
        assert result == ["abc123", "def456"]

    async def test_empty_output_returns_empty_list(self):
        from src.startup_migrations import _parse_current_revision

        result = _parse_current_revision("")
        assert result == []

    async def test_whitespace_only_returns_empty_list(self):
        from src.startup_migrations import _parse_current_revision

        result = _parse_current_revision("   \n  \n")
        assert result == []


def _make_monotonic_mock(values):
    """Create a monotonic mock that returns values in sequence, then repeats the last value."""
    it = iter(values)
    last = [values[-1]]

    def monotonic():
        try:
            return next(it)
        except StopIteration:
            return last[0]

    return monotonic


@pytest.mark.asyncio
class TestTryLockRetry:
    async def test_retries_until_lock_acquired(self):
        mock_conn = MagicMock()
        mock_engine = MagicMock()
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)

        lock_false = MagicMock()
        lock_false.scalar.return_value = False
        lock_true = MagicMock()
        lock_true.scalar.return_value = True

        call_count = 0

        def execute_side_effect(stmt):
            nonlocal call_count
            stmt_str = str(stmt)
            if "pg_try_advisory_lock" in stmt_str:
                call_count += 1
                return lock_true if call_count >= 3 else lock_false
            return MagicMock()

        mock_conn.execute = MagicMock(side_effect=execute_side_effect)

        mock_settings = _make_mock_settings()
        current_result = _make_subprocess_result(stdout="abc123 (head)\n")
        upgrade_result = _make_subprocess_result(stdout="")

        with (
            patch(f"{MODULE}._get_direct_sync_url", return_value=TEST_SYNC_URL),
            patch(f"{MODULE}.create_engine", return_value=mock_engine),
            patch(f"{MODULE}.get_settings", return_value=mock_settings),
            patch(f"{MODULE}.subprocess.run", side_effect=[current_result, upgrade_result]),
            patch(f"{MODULE}.time.sleep") as mock_sleep,
            patch(
                f"{MODULE}.time.monotonic",
                side_effect=_make_monotonic_mock([0, 2, 2, 4, 4]),
            ),
            patch(f"{MODULE}.logger"),
        ):
            from src.startup_migrations import run_startup_migrations

            await run_startup_migrations("full")

        assert call_count == 3
        assert mock_sleep.call_count == 2

    async def test_logs_warning_periodically(self):
        mock_conn = MagicMock()
        mock_engine = MagicMock()
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)

        lock_false = MagicMock()
        lock_false.scalar.return_value = False
        lock_true = MagicMock()
        lock_true.scalar.return_value = True

        attempt = 0

        def execute_side_effect(stmt):
            nonlocal attempt
            stmt_str = str(stmt)
            if "pg_try_advisory_lock" in stmt_str:
                attempt += 1
                return lock_true if attempt >= 4 else lock_false
            return MagicMock()

        mock_conn.execute = MagicMock(side_effect=execute_side_effect)

        mock_settings = _make_mock_settings()
        current_result = _make_subprocess_result(stdout="abc123 (head)\n")
        upgrade_result = _make_subprocess_result(stdout="")

        with (
            patch(f"{MODULE}.create_engine", return_value=mock_engine),
            patch(f"{MODULE}.get_settings", return_value=mock_settings),
            patch(f"{MODULE}.subprocess.run", side_effect=[current_result, upgrade_result]),
            patch(f"{MODULE}.time.sleep"),
            patch(
                f"{MODULE}.time.monotonic",
                side_effect=_make_monotonic_mock([0, 10, 10, 31, 31, 62, 62]),
            ),
            patch(f"{MODULE}.logger") as mock_logger,
        ):
            from src.startup_migrations import run_startup_migrations

            await run_startup_migrations("full")

        warning_calls = [str(c) for c in mock_logger.warning.call_args_list]
        elapsed_warnings = [w for w in warning_calls if "elapsed" in w.lower()]
        assert len(elapsed_warnings) >= 2

    async def test_raises_after_30_minute_timeout(self):
        mock_conn = MagicMock()
        mock_engine = MagicMock()
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)

        lock_false = MagicMock()
        lock_false.scalar.return_value = False
        mock_conn.execute = MagicMock(return_value=lock_false)

        mock_settings = _make_mock_settings()
        check_result = _make_subprocess_result(returncode=1, stderr="not at head")

        from src.startup_migrations import run_startup_migrations

        with (
            patch(f"{MODULE}.create_engine", return_value=mock_engine),
            patch(f"{MODULE}.get_settings", return_value=mock_settings),
            patch(f"{MODULE}.subprocess.run", return_value=check_result),
            patch(f"{MODULE}.time.sleep"),
            patch(
                f"{MODULE}.time.monotonic",
                side_effect=_make_monotonic_mock([0, 1801]),
            ),
            patch(f"{MODULE}.logger"),
            pytest.raises(RuntimeError, match="Migration lock timeout"),
        ):
            await run_startup_migrations("full")

    async def test_fail_open_when_lock_unavailable_but_at_head(self):
        mock_conn = MagicMock()
        mock_engine = MagicMock()
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)

        lock_false = MagicMock()
        lock_false.scalar.return_value = False
        mock_conn.execute = MagicMock(return_value=lock_false)

        mock_settings = _make_mock_settings()
        check_result = _make_subprocess_result(returncode=0)

        with (
            patch(f"{MODULE}._get_direct_sync_url", return_value=TEST_SYNC_URL),
            patch(f"{MODULE}.create_engine", return_value=mock_engine),
            patch(f"{MODULE}.get_settings", return_value=mock_settings),
            patch(f"{MODULE}.subprocess.run", return_value=check_result),
            patch(f"{MODULE}.time.sleep"),
            patch(
                f"{MODULE}.time.monotonic",
                side_effect=_make_monotonic_mock([0, 1801]),
            ),
            patch(f"{MODULE}.logger") as mock_logger,
        ):
            from src.startup_migrations import run_startup_migrations

            await run_startup_migrations("full")

        warning_msgs = [str(c) for c in mock_logger.warning.call_args_list]
        assert any("at head" in m.lower() for m in warning_msgs)

    async def test_raises_when_lock_unavailable_and_not_at_head(self):
        mock_conn = MagicMock()
        mock_engine = MagicMock()
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)

        lock_false = MagicMock()
        lock_false.scalar.return_value = False
        mock_conn.execute = MagicMock(return_value=lock_false)

        mock_settings = _make_mock_settings()
        check_result = _make_subprocess_result(returncode=1, stderr="not at head")

        from src.startup_migrations import run_startup_migrations

        with (
            patch(f"{MODULE}._get_direct_sync_url", return_value=TEST_SYNC_URL),
            patch(f"{MODULE}.create_engine", return_value=mock_engine),
            patch(f"{MODULE}.get_settings", return_value=mock_settings),
            patch(f"{MODULE}.subprocess.run", return_value=check_result),
            patch(f"{MODULE}.time.sleep"),
            patch(
                f"{MODULE}.time.monotonic",
                side_effect=_make_monotonic_mock([0, 1801]),
            ),
            patch(f"{MODULE}.logger"),
            pytest.raises(RuntimeError, match="Migration lock timeout"),
        ):
            await run_startup_migrations("full")


@pytest.mark.asyncio
class TestSyncEngineConnectArgs:
    async def test_create_engine_called_with_connect_args(self):
        mock_engine, _mock_conn = _make_mock_engine()
        current_result = _make_subprocess_result(stdout="abc123 (head)\n")
        upgrade_result = _make_subprocess_result(stdout="")

        mock_settings = _make_mock_settings()

        with (
            patch(f"{MODULE}.create_engine", return_value=mock_engine) as mock_ce,
            patch(f"{MODULE}.get_settings", return_value=mock_settings),
            patch(f"{MODULE}.subprocess.run", side_effect=[current_result, upgrade_result]),
        ):
            from src.startup_migrations import run_startup_migrations

            await run_startup_migrations("full")

        connect_args = mock_ce.call_args.kwargs.get("connect_args")
        assert connect_args is not None
        assert connect_args == {
            "options": "-c statement_timeout=0",
            "connect_timeout": 10,
        }


@pytest.mark.asyncio
class TestSkipMigrations:
    async def test_skip_migrations_returns_early(self):
        mock_settings = MagicMock()
        mock_settings.SKIP_MIGRATIONS = True

        with (
            patch(f"{MODULE}._get_direct_sync_url", return_value=TEST_SYNC_URL),
            patch(f"{MODULE}.get_settings", return_value=mock_settings),
            patch(f"{MODULE}.logger") as mock_logger,
        ):
            from src.startup_migrations import run_startup_migrations

            await run_startup_migrations("full")

        info_messages = [str(c) for c in mock_logger.info.call_args_list]
        assert any("skip" in m.lower() for m in info_messages)
