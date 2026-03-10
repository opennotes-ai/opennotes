import asyncio
import os
import subprocess
import sys
import time
from pathlib import Path

from sqlalchemy import create_engine, text

from src.config import get_settings
from src.database import get_direct_sync_url as _get_direct_sync_url
from src.monitoring import get_logger

logger = get_logger(__name__)
MIGRATION_LOCK_ID = 1847334512
SUBPROCESS_TIMEOUT = 60
LOCK_RETRY_INTERVAL = 2
LOCK_MAX_RETRIES = 30


def _get_alembic_env(direct_url: str) -> dict[str, str]:
    env = os.environ.copy()
    if direct_url.startswith("postgresql://"):
        env["DATABASE_URL"] = direct_url.replace("postgresql://", "postgresql+asyncpg://")
    return env


def _parse_current_revision(stdout: str) -> list[str]:
    revisions = []
    for line in stdout.strip().splitlines():
        rev = line.strip().split(" ")[0]
        if rev:
            revisions.append(rev)
    return revisions


def _is_at_head(server_dir: Path, env: dict[str, str]) -> bool:
    try:
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "check"],
            capture_output=True,
            text=True,
            check=False,
            cwd=server_dir,
            timeout=SUBPROCESS_TIMEOUT,
            env=env,
        )
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        return False


def _acquire_lock(conn) -> bool:
    for attempt in range(LOCK_MAX_RETRIES):
        result = conn.execute(text(f"SELECT pg_try_advisory_lock({MIGRATION_LOCK_ID})"))
        locked = result.scalar()
        if locked:
            return True
        if attempt < LOCK_MAX_RETRIES - 1:
            logger.info(
                f"Migration lock held by another instance, retrying ({attempt + 1}/{LOCK_MAX_RETRIES})"
            )
            time.sleep(LOCK_RETRY_INTERVAL)
    return False


def _release_lock(conn) -> None:
    conn.execute(text(f"SELECT pg_advisory_unlock({MIGRATION_LOCK_ID})"))
    logger.info("Migration lock released")


def _run_alembic_upgrade(conn, server_dir: Path, alembic_env: dict[str, str]) -> None:
    try:
        current_rev = subprocess.run(
            [sys.executable, "-m", "alembic", "current"],
            capture_output=True,
            text=True,
            check=False,
            cwd=server_dir,
            timeout=SUBPROCESS_TIMEOUT,
            env=alembic_env,
        )
    except subprocess.TimeoutExpired:
        logger.critical(
            "alembic current timed out — aborting migration attempt",
            extra={
                "alert_type": "migration_failure",
                "timeout_seconds": SUBPROCESS_TIMEOUT,
            },
        )
        _release_lock(conn)
        return

    if current_rev.returncode != 0:
        logger.critical(
            "alembic current failed — aborting migration attempt",
            extra={
                "alert_type": "migration_failure",
                "alembic_stdout": current_rev.stdout,
                "alembic_stderr": current_rev.stderr,
            },
        )
        _release_lock(conn)
        return

    revisions = _parse_current_revision(current_rev.stdout)
    if len(revisions) > 1:
        logger.warning(
            "Multiple alembic heads detected — rollback will only target the first head; "
            "merge heads before deploying to avoid partial rollback",
            extra={
                "alert_type": "migration_multiple_heads",
                "heads": revisions,
            },
        )
    pre_deploy_revision = revisions[0] if revisions else "base"
    logger.info(f"Pre-deploy revision(s): {revisions or ['base']}")

    try:
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            capture_output=True,
            text=True,
            check=False,
            cwd=server_dir,
            timeout=SUBPROCESS_TIMEOUT,
            env=alembic_env,
        )
    except subprocess.TimeoutExpired:
        logger.critical(
            "alembic upgrade head timed out — aborting migration attempt",
            extra={
                "alert_type": "migration_failure",
                "timeout_seconds": SUBPROCESS_TIMEOUT,
            },
        )
        _release_lock(conn)
        return

    if result.returncode != 0:
        _handle_upgrade_failure(conn, server_dir, alembic_env, result, pre_deploy_revision)
    elif result.stdout.strip():
        logger.info(f"Migrations applied successfully: {result.stdout.strip()}")
    else:
        logger.info("No pending migrations")

    _release_lock(conn)


def _handle_upgrade_failure(conn, server_dir, alembic_env, result, pre_deploy_revision):
    logger.critical(
        "Migration failed — rolling back to pre-deploy revision",
        extra={
            "alert_type": "migration_failure",
            "alembic_stdout": result.stdout,
            "alembic_stderr": result.stderr,
            "pre_deploy_revision": pre_deploy_revision,
        },
    )
    try:
        rollback = subprocess.run(
            [sys.executable, "-m", "alembic", "downgrade", pre_deploy_revision],
            capture_output=True,
            text=True,
            check=False,
            cwd=server_dir,
            timeout=SUBPROCESS_TIMEOUT,
            env=alembic_env,
        )
    except subprocess.TimeoutExpired:
        logger.critical(
            "alembic downgrade timed out — rollback may be incomplete",
            extra={
                "alert_type": "migration_rollback_timeout",
                "timeout_seconds": SUBPROCESS_TIMEOUT,
                "pre_deploy_revision": pre_deploy_revision,
            },
        )
        _release_lock(conn)
        return
    if rollback.returncode != 0:
        logger.critical(
            "Migration rollback ALSO failed",
            extra={
                "alert_type": "migration_rollback_failure",
                "alembic_stdout": rollback.stdout,
                "alembic_stderr": rollback.stderr,
            },
        )


def _run_migrations_sync(is_worker: bool) -> None:
    direct_url = _get_direct_sync_url()
    server_dir = Path(__file__).parent.parent
    alembic_env = _get_alembic_env(direct_url)

    engine = create_engine(
        direct_url,
        isolation_level="AUTOCOMMIT",
    )
    try:
        with engine.connect() as conn:
            locked = _acquire_lock(conn)

            if not locked:
                at_head = _is_at_head(server_dir, alembic_env)
                if at_head:
                    logger.warning(
                        "Could not acquire migration lock after retries, but DB is at head — proceeding"
                    )
                    return
                logger.critical(
                    "Could not acquire migration lock and DB is NOT at head — aborting",
                    extra={"alert_type": "migration_failure"},
                )
                raise RuntimeError("Migration lock unavailable and database not at head")

            logger.info("Migration lock acquired")

            if is_worker:
                logger.info("Worker mode — migration lock acquired (waited for server), releasing")
                _release_lock(conn)
                return

            _run_alembic_upgrade(conn, server_dir, alembic_env)
    except Exception as e:
        logger.critical(
            f"Migration process error: {e}",
            extra={"alert_type": "migration_failure"},
            exc_info=True,
        )
        raise
    finally:
        engine.dispose()


async def run_startup_migrations(server_mode: str) -> None:
    settings = get_settings()
    if settings.SKIP_MIGRATIONS:
        logger.info("SKIP_MIGRATIONS is set — skipping startup migrations")
        return
    is_worker = server_mode == "dbos_worker"
    await asyncio.to_thread(_run_migrations_sync, is_worker)
