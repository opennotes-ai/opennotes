"""DBOS configuration and initialization.

Provides two modes of operation:
- Server mode (full): Uses DBOSClient for lightweight enqueueing only (no polling)
- Worker mode (dbos_worker): Uses DBOS.launch() for queue polling and execution

This separation ensures that only workers compete for queued workflows,
while the server can enqueue work without starting its own executor.
"""

import re
import threading
from typing import Any
from urllib.parse import urlparse, urlunparse

import psycopg
import sqlalchemy as sa
from dbos import DBOS, DBOSClient, DBOSConfig
from sqlalchemy.pool import NullPool

from src.common.connection_retry import sync_connect_with_retry
from src.config import settings
from src.dbos_workflows.serializer import SafeJsonSerializer

_NULLPOOL_INCOMPATIBLE_KEYS = frozenset(
    {"pool_timeout", "max_overflow", "pool_size", "pool_pre_ping"}
)


def _strip_nullpool_incompatible_kwargs(engine_kwargs: dict[str, Any]) -> None:
    if engine_kwargs.get("poolclass") is NullPool:
        for key in _NULLPOOL_INCOMPATIBLE_KEYS:
            engine_kwargs.pop(key, None)


def _install_nullpool_patch() -> None:
    import dbos._dbos_config as _dbos_config_mod

    _original = _dbos_config_mod.configure_db_engine_parameters

    def _patched(data: Any, **kwargs: Any) -> None:
        _original(data, **kwargs)
        for key in ("db_engine_kwargs", "sys_db_engine_kwargs"):
            engine_kwargs = data.get(key)
            if engine_kwargs:
                _strip_nullpool_incompatible_kwargs(engine_kwargs)

    _dbos_config_mod.configure_db_engine_parameters = _patched


_install_nullpool_patch()

_dbos_instance: DBOS | None = None
_dbos_client: DBOSClient | None = None
_dbos_lock = threading.Lock()
_dbos_client_lock = threading.Lock()


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
    database_url = settings.DATABASE_URL
    if not database_url:
        raise ValueError("DATABASE_URL environment variable required for DBOS")

    sync_url = database_url.replace("postgresql+asyncpg://", "postgresql://")

    config: DBOSConfig = {
        "name": settings.DBOS_APP_NAME,
        "system_database_url": sync_url,
        "serializer": SafeJsonSerializer(),
    }

    def _raw_dbos_connect():
        return psycopg.connect(sync_url, prepare_threshold=None)

    config["db_engine_kwargs"] = {
        "poolclass": NullPool,
        "connect_args": {"prepare_threshold": None},
        "creator": sync_connect_with_retry(
            _raw_dbos_connect,
            max_retries=settings.DB_CONNECT_MAX_RETRIES,
            backoff_base=settings.DB_CONNECT_BACKOFF_BASE_SECONDS,
        ),
    }

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


def _get_sync_database_url() -> str:
    """Get the sync PostgreSQL URL for DBOS.

    DBOS uses synchronous psycopg internally, so we convert
    the async DATABASE_URL (postgresql+asyncpg://) to sync format.
    """
    database_url = settings.DATABASE_URL
    if not database_url:
        raise ValueError("DATABASE_URL environment variable required for DBOS")
    return database_url.replace("postgresql+asyncpg://", "postgresql://")


def get_dbos_client() -> DBOSClient:
    """Get DBOSClient for enqueueing workflows (server mode).

    Use this in the API server to enqueue workflows without starting
    queue polling. The client connects directly to the DBOS system
    database to manage queue operations.

    Uses double-checked locking to ensure thread-safe singleton creation
    without unnecessary lock contention.

    Returns:
        DBOSClient instance for enqueueing workflows
    """
    global _dbos_client
    client = _dbos_client
    if client is None:
        with _dbos_client_lock:
            client = _dbos_client
            if client is None:
                sync_url = _get_sync_database_url()

                def _raw_connect():
                    return psycopg.connect(sync_url, prepare_threshold=None)

                engine = sa.create_engine(
                    sync_url,
                    poolclass=NullPool,
                    creator=sync_connect_with_retry(
                        _raw_connect,
                        max_retries=settings.DB_CONNECT_MAX_RETRIES,
                        backoff_base=settings.DB_CONNECT_BACKOFF_BASE_SECONDS,
                    ),
                )
                client = DBOSClient(
                    system_database_engine=engine,
                    serializer=SafeJsonSerializer(),
                )
                _dbos_client = client
    return client


def destroy_dbos_client() -> None:
    """Gracefully destroy the DBOSClient singleton.

    Calls destroy() on the client and clears the cache. The cache is
    cleared even if destroy() raises an exception, ensuring a fresh
    client can be created on the next get_dbos_client() call.
    """
    global _dbos_client
    with _dbos_client_lock:
        if _dbos_client is not None:
            client = _dbos_client
            _dbos_client = None
            client.destroy()


def reset_dbos_client() -> None:
    global _dbos_client
    with _dbos_client_lock:
        if _dbos_client is not None:
            _dbos_client.destroy()
        _dbos_client = None


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
