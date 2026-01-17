"""
Startup validation checks to ensure server readiness.

This module performs critical validation checks before the server starts accepting requests,
including database schema validation, service connectivity, and configuration verification.
"""

import subprocess
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import nats
import redis.asyncio as redis
from sqlalchemy import func, select, text

from src.cache.redis_client import get_redis_connection_kwargs
from src.config import settings
from src.database import get_session_maker
from src.fact_checking.models import FactCheckItem
from src.llm_config.providers.factory import LLMProviderFactory
from src.monitoring import get_logger

logger = get_logger(__name__)


class CheckSeverity(Enum):
    """Severity level for validation checks."""

    CRITICAL = "critical"  # Server cannot start
    WARNING = "warning"  # Issue should be addressed but not blocking
    INFO = "info"  # Informational check result


@dataclass
class CheckResult:
    """Result of a validation check."""

    name: str
    passed: bool
    severity: CheckSeverity
    message: str
    details: dict[str, Any] | None = None

    def __str__(self) -> str:
        status = "✅ PASS" if self.passed else "❌ FAIL"
        return f"{status} [{self.severity.value.upper()}] {self.name}: {self.message}"


class StartupValidationError(Exception):
    """Raised when critical startup validation checks fail."""

    def __init__(self, failed_checks: list[CheckResult]):
        self.failed_checks = failed_checks
        messages = [str(check) for check in failed_checks]
        super().__init__("Startup validation failed:\n" + "\n".join(messages))


async def check_database_schema() -> CheckResult:
    """
    Validate database schema matches SQLAlchemy models using Alembic.

    In test environments, this check is skipped since test databases are
    initialized with fresh schemas and alembic checks can hang due to
    event loop conflicts during server initialization.

    Returns:
        CheckResult indicating if schema is in sync
    """
    if settings.ENVIRONMENT == "test":
        logger.info("Skipping alembic schema check in test environment")
        return CheckResult(
            name="Database Schema",
            passed=True,
            severity=CheckSeverity.CRITICAL,
            message="Database schema check skipped in test environment",
            details={
                "environment": "test",
                "reason": "test databases initialized with fresh schemas",
            },
        )

    try:
        # Get server directory (parent of src)
        server_dir = Path(__file__).parent.parent

        # Run alembic check command
        # Use python -m for compatibility with containerized environments
        # where dependencies are installed system-wide (no .venv)
        result = subprocess.run(
            ["python", "-m", "alembic", "check"],
            check=False,
            cwd=server_dir,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode == 0 and "No new upgrade operations detected" in result.stdout:
            return CheckResult(
                name="Database Schema",
                passed=True,
                severity=CheckSeverity.CRITICAL,
                message="Database schema matches SQLAlchemy models",
                details={"alembic_output": result.stdout.strip()},
            )
        return CheckResult(
            name="Database Schema",
            passed=False,
            severity=CheckSeverity.CRITICAL,
            message="Database schema drift detected - migrations needed",
            details={
                "alembic_stdout": result.stdout.strip(),
                "alembic_stderr": result.stderr.strip(),
                "return_code": result.returncode,
            },
        )
    except subprocess.TimeoutExpired:
        return CheckResult(
            name="Database Schema",
            passed=False,
            severity=CheckSeverity.CRITICAL,
            message="Alembic check timed out after 30 seconds",
        )
    except Exception as e:
        return CheckResult(
            name="Database Schema",
            passed=False,
            severity=CheckSeverity.CRITICAL,
            message=f"Failed to run alembic check: {e}",
        )


async def check_required_environment_variables() -> CheckResult:
    """
    Validate all required environment variables are set.

    Returns:
        CheckResult indicating if all required env vars are present
    """
    required_vars = [
        "DATABASE_URL",
        "REDIS_URL",
        "NATS_URL",
        "JWT_SECRET_KEY",
        "CREDENTIALS_ENCRYPTION_KEY",
        "ENCRYPTION_MASTER_KEY",
    ]

    missing_vars = []
    for var in required_vars:
        value = getattr(settings, var, None)
        if not value or (isinstance(value, str) and not value.strip()):
            missing_vars.append(var)

    if not missing_vars:
        return CheckResult(
            name="Environment Variables",
            passed=True,
            severity=CheckSeverity.CRITICAL,
            message=f"All {len(required_vars)} required environment variables are set",
            details={"checked_vars": required_vars},
        )
    return CheckResult(
        name="Environment Variables",
        passed=False,
        severity=CheckSeverity.CRITICAL,
        message=f"Missing required environment variables: {', '.join(missing_vars)}",
        details={"missing_vars": missing_vars},
    )


async def check_postgresql_connectivity() -> CheckResult:
    """
    Test PostgreSQL database connectivity.

    Returns:
        CheckResult indicating if PostgreSQL is reachable
    """
    try:
        async_session_maker = get_session_maker()
        async with async_session_maker() as session:
            result = await session.execute(text("SELECT 1"))
            result.scalar_one()

        return CheckResult(
            name="PostgreSQL Connectivity",
            passed=True,
            severity=CheckSeverity.CRITICAL,
            message="Successfully connected to PostgreSQL",
            details={"database_url": settings.DATABASE_URL.split("@")[-1]},  # Hide credentials
        )
    except Exception as e:
        return CheckResult(
            name="PostgreSQL Connectivity",
            passed=False,
            severity=CheckSeverity.CRITICAL,
            message=f"Failed to connect to PostgreSQL: {type(e).__name__}: {e}",
        )


async def check_redis_connectivity() -> CheckResult:
    """
    Test Redis connectivity.

    Returns:
        CheckResult indicating if Redis is reachable
    """
    try:
        connection_kwargs = get_redis_connection_kwargs(settings.REDIS_URL)
        client = redis.from_url(settings.REDIS_URL, **connection_kwargs)  # type: ignore[no-untyped-call]
        await client.ping()
        await client.aclose()

        return CheckResult(
            name="Redis Connectivity",
            passed=True,
            severity=CheckSeverity.CRITICAL,
            message="Successfully connected to Redis",
            details={"redis_url": settings.REDIS_URL.split("@")[-1]},  # Hide credentials
        )
    except Exception as e:
        return CheckResult(
            name="Redis Connectivity",
            passed=False,
            severity=CheckSeverity.CRITICAL,
            message=f"Failed to connect to Redis: {type(e).__name__}: {e}",
        )


async def check_nats_connectivity() -> CheckResult:
    """
    Test NATS connectivity.

    Returns:
        CheckResult indicating if NATS is reachable
    """
    try:
        nc = await nats.connect(settings.NATS_URL, connect_timeout=5)
        await nc.close()

        return CheckResult(
            name="NATS Connectivity",
            passed=True,
            severity=CheckSeverity.CRITICAL,
            message="Successfully connected to NATS",
            details={"nats_url": settings.NATS_URL},
        )
    except Exception as e:
        return CheckResult(
            name="NATS Connectivity",
            passed=False,
            severity=CheckSeverity.CRITICAL,
            message=f"Failed to connect to NATS: {type(e).__name__}: {e}",
        )


async def check_llm_provider_configuration() -> CheckResult:
    """
    Validate LLM provider infrastructure and global fallback configuration.

    The LLM system uses per-community provider configurations stored in the database,
    with optional global API keys as fallback. This check validates:
    - Provider infrastructure is available
    - At least one global fallback API key is configured (optional but recommended)
    - Model settings for OpenAI-specific features are configured

    Returns:
        CheckResult indicating if LLM configuration is valid
    """
    try:
        warnings = []
        details: dict[str, bool | str | list[str]] = {}

        # Verify provider infrastructure
        available_providers = LLMProviderFactory.list_providers()
        details["available_providers"] = available_providers

        if not available_providers:
            return CheckResult(
                name="LLM Configuration",
                passed=False,
                severity=CheckSeverity.WARNING,
                message="No LLM providers registered in factory",
                details=details,
            )

        # Check global fallback API keys (optional but recommended)
        has_openai = bool(settings.OPENAI_API_KEY)
        has_anthropic = bool(settings.ANTHROPIC_API_KEY)
        details["openai_fallback_key_set"] = has_openai
        details["anthropic_fallback_key_set"] = has_anthropic

        if not has_openai and not has_anthropic:
            warnings.append(
                "No global fallback API keys configured (OPENAI_API_KEY, ANTHROPIC_API_KEY) - "
                "AI features will only work for communities with their own LLM configuration"
            )

        # Validate OpenAI-specific model settings
        if not settings.EMBEDDING_MODEL:
            warnings.append("EMBEDDING_MODEL not configured")
        if not settings.VISION_MODEL:
            warnings.append("VISION_MODEL not configured")
        if not settings.AI_NOTE_WRITER_MODEL:
            warnings.append("AI_NOTE_WRITER_MODEL not configured")

        details["embedding_model"] = settings.EMBEDDING_MODEL
        details["vision_model"] = settings.VISION_MODEL
        details["ai_note_writer_model"] = settings.AI_NOTE_WRITER_MODEL

        if not warnings:
            return CheckResult(
                name="LLM Configuration",
                passed=True,
                severity=CheckSeverity.WARNING,
                message=f"LLM provider infrastructure ready ({len(available_providers)} providers available)",
                details=details,
            )
        return CheckResult(
            name="LLM Configuration",
            passed=False,
            severity=CheckSeverity.WARNING,
            message=f"LLM configuration warnings: {'; '.join(warnings)}",
            details={**details, "warnings": warnings},
        )
    except Exception as e:
        return CheckResult(
            name="LLM Configuration",
            passed=False,
            severity=CheckSeverity.WARNING,
            message=f"Failed to validate LLM configuration: {type(e).__name__}: {e}",
        )


async def check_fact_check_dataset() -> CheckResult:
    """
    Validate fact-check dataset is accessible and has data.

    Returns:
        CheckResult indicating if fact-check dataset is accessible
    """
    try:
        async_session_maker = get_session_maker()
        async with async_session_maker() as session:
            result = await session.execute(select(func.count(FactCheckItem.id)))
            count = result.scalar_one()

            if count > 0:
                return CheckResult(
                    name="Fact-Check Dataset",
                    passed=True,
                    severity=CheckSeverity.WARNING,
                    message=f"Fact-check dataset accessible with {count} items",
                    details={"item_count": count},
                )
            return CheckResult(
                name="Fact-Check Dataset",
                passed=False,
                severity=CheckSeverity.WARNING,
                message="Fact-check dataset is empty - AI note generation may not work",
                details={"item_count": 0},
            )
    except Exception as e:
        return CheckResult(
            name="Fact-Check Dataset",
            passed=False,
            severity=CheckSeverity.WARNING,
            message=f"Failed to check fact-check dataset: {type(e).__name__}: {e}",
        )


async def run_startup_checks(skip_checks: list[str] | None = None) -> list[CheckResult]:
    """
    Run all startup validation checks.

    Args:
        skip_checks: Optional list of check names to skip (for development)

    Returns:
        List of CheckResult objects

    Raises:
        StartupValidationError: If any critical checks fail
    """
    skip_checks = skip_checks or []

    # Define all checks
    checks: list[tuple[str, Callable[[], Coroutine[Any, Any, CheckResult]]]] = [
        ("database_schema", check_database_schema),
        ("environment_variables", check_required_environment_variables),
        ("postgresql", check_postgresql_connectivity),
        ("redis", check_redis_connectivity),
        ("nats", check_nats_connectivity),
        ("llm_configuration", check_llm_provider_configuration),
        ("fact_check_dataset", check_fact_check_dataset),
    ]

    logger.info("Starting server validation checks...")

    results = []
    for check_name, check_func in checks:
        if check_name in skip_checks:
            logger.info(f"Skipping check: {check_name} (disabled in configuration)")
            continue

        try:
            result = await check_func()
            results.append(result)

            # Log based on result
            if result.passed:
                logger.info(str(result))
            elif result.severity == CheckSeverity.CRITICAL:
                logger.error(str(result))
            else:
                logger.warning(str(result))

        except Exception as e:
            logger.exception(f"Unexpected error running check {check_name}")
            results.append(
                CheckResult(
                    name=check_name,
                    passed=False,
                    severity=CheckSeverity.CRITICAL,
                    message=f"Unexpected error: {type(e).__name__}: {e}",
                )
            )

    # Check for critical failures
    critical_failures = [
        r for r in results if not r.passed and r.severity == CheckSeverity.CRITICAL
    ]

    if critical_failures:
        logger.error(f"❌ {len(critical_failures)} critical validation check(s) failed")
        raise StartupValidationError(critical_failures)

    # Log warnings
    warnings = [r for r in results if not r.passed and r.severity == CheckSeverity.WARNING]
    if warnings:
        logger.warning(f"⚠️  {len(warnings)} validation warning(s) detected")

    passed_count = len([r for r in results if r.passed])
    logger.info(f"✅ Startup validation complete: {passed_count}/{len(results)} checks passed")

    return results
