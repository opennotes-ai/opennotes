"""Tests for startup validation checks."""

import subprocess
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.startup_validation import (
    CheckResult,
    CheckSeverity,
    StartupValidationError,
    check_database_schema,
    check_fact_check_dataset,
    check_llm_provider_configuration,
    check_nats_connectivity,
    check_postgresql_connectivity,
    check_redis_connectivity,
    check_required_environment_variables,
    run_startup_checks,
)


@pytest.mark.asyncio
class TestStartupValidationChecks:
    """Test individual validation checks."""

    async def test_check_database_schema_success(self):
        """Test successful database schema validation."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "No new upgrade operations detected."
        mock_result.stderr = ""

        with (
            patch("src.startup_validation.settings") as mock_settings,
            patch("subprocess.run", return_value=mock_result),
        ):
            mock_settings.ENVIRONMENT = "production"
            result = await check_database_schema()

        assert result.passed is True
        assert result.severity == CheckSeverity.CRITICAL
        assert "schema matches" in result.message.lower()

    async def test_check_database_schema_drift_detected(self):
        """Test database schema drift detection."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = "Pending migrations detected"
        mock_result.stderr = ""

        with (
            patch("src.startup_validation.settings") as mock_settings,
            patch("subprocess.run", return_value=mock_result),
        ):
            mock_settings.ENVIRONMENT = "production"
            result = await check_database_schema()

        assert result.passed is False
        assert result.severity == CheckSeverity.CRITICAL
        assert "drift" in result.message.lower()

    async def test_check_database_schema_timeout(self):
        """Test database schema check timeout handling."""
        with (
            patch("src.startup_validation.settings") as mock_settings,
            patch(
                "subprocess.run",
                side_effect=subprocess.TimeoutExpired("alembic", 30),
            ),
        ):
            mock_settings.ENVIRONMENT = "production"
            result = await check_database_schema()

        assert result.passed is False
        assert result.severity == CheckSeverity.CRITICAL
        assert "timed out" in result.message.lower()

    async def test_check_required_environment_variables_success(self):
        """Test successful environment variable validation."""
        with patch("src.startup_validation.settings") as mock_settings:
            mock_settings.DATABASE_URL = "postgresql+asyncpg://test"
            mock_settings.REDIS_URL = "redis://test"
            mock_settings.NATS_URL = "nats://test"
            mock_settings.SECRET_KEY = "test_secret_key_long_enough"
            mock_settings.ENCRYPTION_KEY = "test_encryption_key"

            result = await check_required_environment_variables()

        assert result.passed is True
        assert result.severity == CheckSeverity.CRITICAL

    async def test_check_required_environment_variables_missing(self):
        """Test missing environment variables detection."""
        with patch("src.startup_validation.settings") as mock_settings:
            mock_settings.DATABASE_URL = ""
            mock_settings.REDIS_URL = "redis://test"
            mock_settings.NATS_URL = ""
            mock_settings.SECRET_KEY = "test"
            mock_settings.ENCRYPTION_KEY = ""

            result = await check_required_environment_variables()

        assert result.passed is False
        assert result.severity == CheckSeverity.CRITICAL
        assert "missing" in result.message.lower()
        assert result.details is not None
        assert len(result.details["missing_vars"]) > 0

    async def test_check_postgresql_connectivity_success(self):
        """Test successful PostgreSQL connectivity."""
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 1
        mock_session.execute.return_value = mock_result

        with patch("src.startup_validation.get_session_maker") as mock_maker:
            mock_maker.return_value.return_value.__aenter__.return_value = mock_session
            result = await check_postgresql_connectivity()

        assert result.passed is True
        assert result.severity == CheckSeverity.CRITICAL

    async def test_check_postgresql_connectivity_failure(self):
        """Test PostgreSQL connectivity failure."""
        with patch("src.startup_validation.get_session_maker") as mock_maker:
            mock_maker.side_effect = Exception("Connection refused")
            result = await check_postgresql_connectivity()

        assert result.passed is False
        assert result.severity == CheckSeverity.CRITICAL
        assert "failed to connect" in result.message.lower()

    async def test_check_redis_connectivity_success(self):
        """Test successful Redis connectivity."""
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock()
        mock_client.aclose = AsyncMock()

        with patch("redis.asyncio.from_url", return_value=mock_client):
            result = await check_redis_connectivity()

        assert result.passed is True
        assert result.severity == CheckSeverity.CRITICAL
        mock_client.ping.assert_called_once()
        mock_client.aclose.assert_called_once()

    async def test_check_redis_connectivity_failure(self):
        """Test Redis connectivity failure."""
        with patch("redis.asyncio.from_url", side_effect=Exception("Connection refused")):
            result = await check_redis_connectivity()

        assert result.passed is False
        assert result.severity == CheckSeverity.CRITICAL

    async def test_check_nats_connectivity_success(self):
        """Test successful NATS connectivity."""
        mock_nc = AsyncMock()
        mock_nc.close = AsyncMock()

        with patch("nats.connect", return_value=mock_nc):
            result = await check_nats_connectivity()

        assert result.passed is True
        assert result.severity == CheckSeverity.CRITICAL
        mock_nc.close.assert_called_once()

    async def test_check_nats_connectivity_failure(self):
        """Test NATS connectivity failure."""
        with patch("nats.connect", side_effect=Exception("Connection refused")):
            result = await check_nats_connectivity()

        assert result.passed is False
        assert result.severity == CheckSeverity.CRITICAL

    async def test_check_llm_provider_configuration_openai_valid(self):
        """Test valid LLM provider infrastructure with OpenAI fallback."""
        with patch("src.startup_validation.settings") as mock_settings:
            mock_settings.OPENAI_API_KEY = "sk-test-key"
            mock_settings.ANTHROPIC_API_KEY = None
            mock_settings.EMBEDDING_MODEL = "text-embedding-3-small"
            mock_settings.VISION_MODEL = "gpt-5.1"
            mock_settings.AI_NOTE_WRITER_MODEL = "gpt-5.1"

            result = await check_llm_provider_configuration()

        assert result.passed is True
        assert result.severity == CheckSeverity.WARNING
        assert "provider" in result.message.lower()

    async def test_check_llm_provider_configuration_openai_missing_key(self):
        """Test LLM configuration with no global fallback keys."""
        with patch("src.startup_validation.settings") as mock_settings:
            mock_settings.OPENAI_API_KEY = None
            mock_settings.ANTHROPIC_API_KEY = None
            mock_settings.EMBEDDING_MODEL = "text-embedding-3-small"
            mock_settings.VISION_MODEL = "gpt-5.1"
            mock_settings.AI_NOTE_WRITER_MODEL = "gpt-5.1"

            result = await check_llm_provider_configuration()

        assert result.passed is False
        assert result.severity == CheckSeverity.WARNING
        assert "fallback" in result.message.lower() or "communities" in result.message.lower()

    async def test_check_fact_check_dataset_with_data(self):
        """Test fact-check dataset validation with data."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 42  # Simulate having data
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.__aenter__.return_value = mock_session
        mock_session.__aexit__.return_value = None

        with patch("src.startup_validation.get_session_maker") as mock_maker:
            mock_maker.return_value.return_value = mock_session
            result = await check_fact_check_dataset()

        assert result.passed is True
        assert result.severity == CheckSeverity.WARNING
        assert result.details["item_count"] > 0

    async def test_check_fact_check_dataset_empty(self):
        """Test fact-check dataset validation with empty dataset."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 0
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.__aenter__.return_value = mock_session
        mock_session.__aexit__.return_value = None

        with patch("src.startup_validation.get_session_maker") as mock_maker:
            mock_maker.return_value.return_value = mock_session
            result = await check_fact_check_dataset()

        assert result.passed is False
        assert result.severity == CheckSeverity.WARNING
        assert "empty" in result.message.lower()


@pytest.mark.asyncio
class TestStartupValidationOrchestrator:
    """Test the run_startup_checks orchestrator."""

    async def test_run_startup_checks_all_pass(self):
        """Test that all checks passing succeeds."""
        passing_check = CheckResult(
            name="test",
            passed=True,
            severity=CheckSeverity.CRITICAL,
            message="Success",
        )

        with (
            patch("src.startup_validation.check_database_schema", return_value=passing_check),
            patch(
                "src.startup_validation.check_required_environment_variables",
                return_value=passing_check,
            ),
            patch(
                "src.startup_validation.check_postgresql_connectivity", return_value=passing_check
            ),
            patch("src.startup_validation.check_redis_connectivity", return_value=passing_check),
            patch("src.startup_validation.check_nats_connectivity", return_value=passing_check),
            patch(
                "src.startup_validation.check_llm_provider_configuration",
                return_value=passing_check,
            ),
            patch("src.startup_validation.check_fact_check_dataset", return_value=passing_check),
        ):
            results = await run_startup_checks()

        assert len(results) == 7
        assert all(r.passed for r in results)

    async def test_run_startup_checks_critical_failure_raises(self):
        """Test that critical failures raise StartupValidationError."""
        passing_check = CheckResult(
            name="test",
            passed=True,
            severity=CheckSeverity.CRITICAL,
            message="Success",
        )
        failing_check = CheckResult(
            name="database_schema",
            passed=False,
            severity=CheckSeverity.CRITICAL,
            message="Schema drift detected",
        )

        with (
            patch("src.startup_validation.check_database_schema", return_value=failing_check),
            patch(
                "src.startup_validation.check_required_environment_variables",
                return_value=passing_check,
            ),
            patch(
                "src.startup_validation.check_postgresql_connectivity", return_value=passing_check
            ),
            patch("src.startup_validation.check_redis_connectivity", return_value=passing_check),
            patch("src.startup_validation.check_nats_connectivity", return_value=passing_check),
            patch(
                "src.startup_validation.check_llm_provider_configuration",
                return_value=passing_check,
            ),
            patch("src.startup_validation.check_fact_check_dataset", return_value=passing_check),
            pytest.raises(StartupValidationError) as exc_info,
        ):
            await run_startup_checks()

        assert len(exc_info.value.failed_checks) == 1
        assert exc_info.value.failed_checks[0].name == "database_schema"

    async def test_run_startup_checks_warning_does_not_raise(self):
        """Test that warnings do not prevent startup."""
        passing_check = CheckResult(
            name="test",
            passed=True,
            severity=CheckSeverity.CRITICAL,
            message="Success",
        )
        warning_check = CheckResult(
            name="llm_configuration",
            passed=False,
            severity=CheckSeverity.WARNING,
            message="LLM config issue",
        )

        with (
            patch("src.startup_validation.check_database_schema", return_value=passing_check),
            patch(
                "src.startup_validation.check_required_environment_variables",
                return_value=passing_check,
            ),
            patch(
                "src.startup_validation.check_postgresql_connectivity", return_value=passing_check
            ),
            patch("src.startup_validation.check_redis_connectivity", return_value=passing_check),
            patch("src.startup_validation.check_nats_connectivity", return_value=passing_check),
            patch(
                "src.startup_validation.check_llm_provider_configuration",
                return_value=warning_check,
            ),
            patch("src.startup_validation.check_fact_check_dataset", return_value=passing_check),
        ):
            results = await run_startup_checks()

        assert len(results) == 7
        warnings = [r for r in results if not r.passed and r.severity == CheckSeverity.WARNING]
        assert len(warnings) == 1

    async def test_run_startup_checks_with_skip_checks(self):
        """Test that skip_checks parameter works."""
        passing_check = CheckResult(
            name="test",
            passed=True,
            severity=CheckSeverity.CRITICAL,
            message="Success",
        )

        with (
            patch(
                "src.startup_validation.check_database_schema", return_value=passing_check
            ) as mock_schema,
            patch(
                "src.startup_validation.check_required_environment_variables",
                return_value=passing_check,
            ),
            patch(
                "src.startup_validation.check_postgresql_connectivity", return_value=passing_check
            ) as mock_pg,
            patch("src.startup_validation.check_redis_connectivity", return_value=passing_check),
            patch("src.startup_validation.check_nats_connectivity", return_value=passing_check),
            patch(
                "src.startup_validation.check_llm_provider_configuration",
                return_value=passing_check,
            ),
            patch("src.startup_validation.check_fact_check_dataset", return_value=passing_check),
        ):
            results = await run_startup_checks(skip_checks=["database_schema", "postgresql"])

        # Only 5 checks should run (7 total - 2 skipped)
        assert len(results) == 5
        mock_schema.assert_not_called()
        mock_pg.assert_not_called()


@pytest.mark.asyncio
class TestNatsConnectivityAuth:
    """Test NATS connectivity check authentication handling."""

    async def test_check_nats_connectivity_uses_auth_when_configured(self):
        """Test that NATS connectivity check uses credentials when available."""
        mock_nc = AsyncMock()
        mock_nc.close = AsyncMock()

        with (
            patch("src.startup_validation.settings") as mock_settings,
            patch("nats.connect", return_value=mock_nc) as mock_connect,
        ):
            mock_settings.NATS_URL = "nats://localhost:4222"
            mock_settings.NATS_USERNAME = "testuser"
            mock_settings.NATS_PASSWORD = "testpass"

            result = await check_nats_connectivity()

        assert result.passed is True
        mock_connect.assert_called_once()
        call_kwargs = mock_connect.call_args.kwargs
        assert call_kwargs["servers"] == "nats://localhost:4222"
        assert call_kwargs["user"] == "testuser"
        assert call_kwargs["password"] == "testpass"
        assert call_kwargs["connect_timeout"] == 5

    async def test_check_nats_connectivity_no_auth_when_not_configured(self):
        """Test that NATS connectivity check omits auth when not configured."""
        mock_nc = AsyncMock()
        mock_nc.close = AsyncMock()

        with (
            patch("src.startup_validation.settings") as mock_settings,
            patch("nats.connect", return_value=mock_nc) as mock_connect,
        ):
            mock_settings.NATS_URL = "nats://localhost:4222"
            mock_settings.NATS_USERNAME = None
            mock_settings.NATS_PASSWORD = None

            result = await check_nats_connectivity()

        assert result.passed is True
        mock_connect.assert_called_once()
        call_kwargs = mock_connect.call_args.kwargs
        assert call_kwargs["servers"] == "nats://localhost:4222"
        assert "user" not in call_kwargs
        assert "password" not in call_kwargs

    async def test_check_nats_connectivity_no_auth_when_partial_credentials(self):
        """Test that NATS auth is omitted when only username or password is set."""
        mock_nc = AsyncMock()
        mock_nc.close = AsyncMock()

        with (
            patch("src.startup_validation.settings") as mock_settings,
            patch("nats.connect", return_value=mock_nc) as mock_connect,
        ):
            mock_settings.NATS_URL = "nats://localhost:4222"
            mock_settings.NATS_USERNAME = "testuser"
            mock_settings.NATS_PASSWORD = None  # Only username set

            result = await check_nats_connectivity()

        assert result.passed is True
        call_kwargs = mock_connect.call_args.kwargs
        assert "user" not in call_kwargs
        assert "password" not in call_kwargs
