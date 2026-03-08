import asyncio
import subprocess
import sys
from pathlib import Path

import psycopg2
from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.pool import NullPool

from src.common.connection_retry import sync_connect_with_retry
from src.config import get_settings
from src.monitoring import get_logger

logger = get_logger(__name__)
MIGRATION_LOCK_ID = 1847334512
SUBPROCESS_TIMEOUT = 300


def _get_sync_db_url() -> str:
    settings = get_settings()
    return settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")


def _parse_current_revision(stdout: str) -> list[str]:
    revisions = []
    for line in stdout.strip().splitlines():
        rev = line.strip().split(" ")[0]
        if rev:
            revisions.append(rev)
    return revisions


def _run_migrations_sync(is_worker: bool) -> None:
    db_url = _get_sync_db_url()
    cfg = get_settings()
    server_dir = Path(__file__).parent.parent
    url = make_url(db_url)

    def _raw_connect():
        return psycopg2.connect(url.render_as_string(hide_password=False))

    creator = sync_connect_with_retry(
        _raw_connect,
        max_retries=cfg.DB_CONNECT_MAX_RETRIES,
        backoff_base=cfg.DB_CONNECT_BACKOFF_BASE_SECONDS,
    )

    engine = create_engine(
        db_url,
        isolation_level="AUTOCOMMIT",
        poolclass=NullPool,
        creator=creator,
    )
    try:
        with engine.connect() as conn:
            conn.execute(text(f"SELECT pg_advisory_lock({MIGRATION_LOCK_ID})"))
            logger.info("Migration lock acquired")

            if is_worker:
                logger.info("Worker mode — migration lock acquired (waited for server), releasing")
                conn.execute(text(f"SELECT pg_advisory_unlock({MIGRATION_LOCK_ID})"))
                return

            try:
                current_rev = subprocess.run(
                    [sys.executable, "-m", "alembic", "current"],
                    capture_output=True,
                    text=True,
                    check=False,
                    cwd=server_dir,
                    timeout=SUBPROCESS_TIMEOUT,
                )
            except subprocess.TimeoutExpired:
                logger.critical(
                    "alembic current timed out — aborting migration attempt",
                    extra={
                        "alert_type": "migration_failure",
                        "timeout_seconds": SUBPROCESS_TIMEOUT,
                    },
                )
                conn.execute(text(f"SELECT pg_advisory_unlock({MIGRATION_LOCK_ID})"))
                logger.info("Migration lock released")
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
                conn.execute(text(f"SELECT pg_advisory_unlock({MIGRATION_LOCK_ID})"))
                logger.info("Migration lock released")
                return

            revisions = _parse_current_revision(current_rev.stdout)
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
                )
            except subprocess.TimeoutExpired:
                logger.critical(
                    "alembic upgrade head timed out — aborting migration attempt",
                    extra={
                        "alert_type": "migration_failure",
                        "timeout_seconds": SUBPROCESS_TIMEOUT,
                    },
                )
                conn.execute(text(f"SELECT pg_advisory_unlock({MIGRATION_LOCK_ID})"))
                logger.info("Migration lock released")
                return

            if result.returncode != 0:
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
                    conn.execute(text(f"SELECT pg_advisory_unlock({MIGRATION_LOCK_ID})"))
                    logger.info("Migration lock released")
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
            elif result.stdout.strip():
                logger.info(f"Migrations applied successfully: {result.stdout.strip()}")
            else:
                logger.info("No pending migrations")

            conn.execute(text(f"SELECT pg_advisory_unlock({MIGRATION_LOCK_ID})"))
            logger.info("Migration lock released")
    except Exception as e:
        logger.critical(
            f"Migration process error: {e}",
            extra={"alert_type": "migration_failure"},
            exc_info=True,
        )
    finally:
        engine.dispose()


async def run_startup_migrations(server_mode: str) -> None:
    is_worker = server_mode == "dbos_worker"
    await asyncio.to_thread(_run_migrations_sync, is_worker)
