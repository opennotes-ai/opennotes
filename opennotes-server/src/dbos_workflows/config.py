"""DBOS configuration and initialization.

Provides DBOS singleton management for workflow execution:
- get_dbos_config(): Build DBOSConfig from environment settings
- get_dbos() / reset_dbos() / destroy_dbos(): DBOS singleton lifecycle
- create_dbos_instance(): Factory for DBOS instances
- validate_dbos_connection(): Health check for DBOS system database
"""

import re
import threading
from urllib.parse import urlparse, urlunparse

from dbos import DBOS, DBOSConfig
from sqlalchemy.pool import NullPool

from src.config import settings
from src.dbos_workflows.serializer import SafeJsonSerializer

_dbos_instance: DBOS | None = None
_dbos_lock = threading.Lock()


def _derive_http_otlp_endpoint(grpc_endpoint: str | None) -> str | None:
    """Derive HTTP OTLP endpoint from gRPC endpoint.

    DBOS uses HTTP OTLP endpoints (port 4318 with /v1/* paths) while the main
    application uses gRPC OTLP (port 4317). This function transforms the
    gRPC endpoint to HTTP format using proper URL parsing.

    Common transformations:
    - http://tempo:4317 -> http://tempo:4318
    - https://otel-collector:443 -> https://otel-collector:443 (HTTPS typically uses same port)
    - http://localhost:4317 -> http://localhost:4318
    - http://host4317.example.com:4317 -> http://host4317.example.com:4318 (hostname preserved)

    Args:
        grpc_endpoint: The gRPC OTLP endpoint (e.g., http://tempo:4317)

    Returns:
        The HTTP OTLP base endpoint without path suffix, or None if input is empty
    """
    if not grpc_endpoint:
        return None

    endpoint = grpc_endpoint.rstrip("/")
    parsed = urlparse(endpoint)

    if not parsed.scheme or not parsed.netloc:
        return None

    if parsed.port != 4317:
        return urlunparse((parsed.scheme, parsed.netloc, "", "", "", ""))

    if parsed.hostname is None:
        return urlunparse((parsed.scheme, parsed.netloc, "", "", "", ""))

    if ":" in parsed.hostname:
        new_netloc = f"[{parsed.hostname}]:4318"
    else:
        new_netloc = f"{parsed.hostname}:4318"

    if parsed.username:
        auth = parsed.username
        if parsed.password:
            auth = f"{auth}:{parsed.password}"
        new_netloc = f"{auth}@{new_netloc}"

    return urlunparse((parsed.scheme, new_netloc, "", "", "", ""))


def get_dbos_config() -> DBOSConfig:
    """Build DBOS configuration from environment.

    DBOS automatically uses a dedicated 'dbos' schema for its system tables,
    isolating them from application tables in the 'public' schema.

    Note: DBOS uses synchronous psycopg internally, so we convert
    the async DATABASE_URL (postgresql+asyncpg://) to sync format.
    """
    database_url = settings.DATABASE_DIRECT_URL or settings.DATABASE_URL
    if not database_url:
        raise ValueError("DATABASE_URL environment variable required for DBOS")

    sync_url = database_url.replace("postgresql+asyncpg://", "postgresql://")

    config: DBOSConfig = {
        "name": settings.DBOS_APP_NAME,
        "system_database_url": sync_url,
        "serializer": SafeJsonSerializer(),
    }

    config["db_engine_kwargs"] = {
        "poolclass": NullPool,
        "connect_args": {"prepare_threshold": None},
    }

    config["admin_port"] = settings.DBOS_ADMIN_PORT
    config["run_admin_server"] = settings.DBOS_RUN_ADMIN_SERVER

    config["otlp_attributes"] = {
        "service.version": settings.VERSION,
        "deployment.environment": settings.ENVIRONMENT,
    }

    if settings.OTLP_ENDPOINT:
        http_base = _derive_http_otlp_endpoint(settings.OTLP_ENDPOINT)
        if http_base:
            config["enable_otlp"] = True
            config["otlp_traces_endpoints"] = [f"{http_base}/v1/traces"]
            config["otlp_logs_endpoints"] = [f"{http_base}/v1/logs"]

    return config


def create_dbos_instance() -> DBOS:
    """Create and return DBOS instance (do not launch yet)."""
    config = get_dbos_config()
    if settings.DBOS_CONDUCTOR_KEY:
        config["conductor_key"] = settings.DBOS_CONDUCTOR_KEY
    return DBOS(config=config)


def get_dbos() -> DBOS:
    """Get the DBOS instance, creating if needed.

    Uses double-checked locking to ensure thread-safe singleton creation
    without unnecessary lock contention.
    """
    global _dbos_instance
    instance = _dbos_instance
    if instance is None:
        with _dbos_lock:
            instance = _dbos_instance
            if instance is None:
                instance = create_dbos_instance()
                _dbos_instance = instance
    return instance


def reset_dbos() -> None:
    """Reset the DBOS instance. Used for testing."""
    global _dbos_instance
    with _dbos_lock:
        if _dbos_instance is not None:
            try:
                _dbos_instance.destroy(destroy_registry=False)
            except Exception:
                pass
        _dbos_instance = None


def destroy_dbos(workflow_completion_timeout_sec: int = 5) -> None:
    """Gracefully destroy the DBOS singleton.

    Calls DBOS.destroy() to properly shut down the executor and wait
    for any in-flight workflows to complete. This should be called
    during application shutdown.

    Args:
        workflow_completion_timeout_sec: Seconds to wait for workflows to
            complete before forcefully shutting down. Defaults to 5.
    """
    global _dbos_instance
    with _dbos_lock:
        if _dbos_instance is not None:
            DBOS.destroy(
                workflow_completion_timeout_sec=workflow_completion_timeout_sec,
                destroy_registry=False,
            )
            _dbos_instance = None


def validate_dbos_connection() -> bool:
    import psycopg

    config = get_dbos_config()
    db_url = config.get("system_database_url")
    if not db_url:
        raise RuntimeError("system_database_url not configured in DBOS config")

    try:
        with psycopg.connect(db_url, prepare_threshold=None) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = 'dbos' AND table_name = 'workflow_status')"
            )
            row = cur.fetchone()
            if row is None or not row[0]:
                raise RuntimeError("DBOS system tables not found in 'dbos' schema")
        return True
    except psycopg.Error as e:
        sanitized = re.sub(
            r"://[^@]*@",
            "://***:***@",
            str(e),
        )
        raise RuntimeError(
            f"DBOS database connection failed: {type(e).__name__}: {sanitized}"
        ) from None
