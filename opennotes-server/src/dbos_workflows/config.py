"""DBOS configuration and initialization.

Provides two modes of operation:
- Server mode (full): Uses DBOSClient for lightweight enqueueing only (no polling)
- Worker mode (dbos_worker): Uses DBOS.launch() for queue polling and execution

This separation ensures that only workers compete for queued workflows,
while the server can enqueue work without starting its own executor.
"""

from dbos import DBOS, DBOSClient, DBOSConfig

from src.config import settings

_dbos_instance: DBOS | None = None
_dbos_client: DBOSClient | None = None


def _derive_http_otlp_endpoint(grpc_endpoint: str | None) -> str | None:
    """Derive HTTP OTLP endpoint from gRPC endpoint.

    DBOS uses HTTP OTLP endpoints (port 4318 with /v1/* paths) while the main
    application uses gRPC OTLP (port 4317). This function transforms the
    gRPC endpoint to HTTP format.

    Common transformations:
    - http://tempo:4317 -> http://tempo:4318
    - https://otel-collector:443 -> https://otel-collector:443 (HTTPS typically uses same port)
    - http://localhost:4317 -> http://localhost:4318

    Args:
        grpc_endpoint: The gRPC OTLP endpoint (e.g., http://tempo:4317)

    Returns:
        The HTTP OTLP base endpoint without path suffix, or None if input is empty
    """
    if not grpc_endpoint:
        return None

    endpoint = grpc_endpoint.rstrip("/")

    if ":4317" in endpoint:
        return endpoint.replace(":4317", ":4318")

    return endpoint


def _get_otlp_config() -> dict:
    """Build OTLP configuration for DBOS based on environment settings.

    Uses the same OTLP_ENDPOINT setting as the main application but transforms
    it to HTTP format required by DBOS.

    Returns:
        Dictionary with DBOS OTLP configuration fields
    """
    if not settings.OTLP_ENDPOINT:
        return {"enable_otlp": False}

    http_base = _derive_http_otlp_endpoint(settings.OTLP_ENDPOINT)
    if not http_base:
        return {"enable_otlp": False}

    traces_endpoint = f"{http_base}/v1/traces"
    logs_endpoint = f"{http_base}/v1/logs"

    return {
        "enable_otlp": True,
        "otlp_traces_endpoints": [traces_endpoint],
        "otlp_logs_endpoints": [logs_endpoint],
    }


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
        "name": settings.OTEL_SERVICE_NAME or settings.PROJECT_NAME,
        "system_database_url": sync_url,
        **_get_otlp_config(),
    }
    return config


def create_dbos_instance() -> DBOS:
    """Create and return DBOS instance (do not launch yet)."""
    config = get_dbos_config()
    return DBOS(config=config)


def get_dbos() -> DBOS:
    """Get the DBOS instance, creating if needed."""
    global _dbos_instance
    if _dbos_instance is None:
        _dbos_instance = create_dbos_instance()
    return _dbos_instance


def reset_dbos() -> None:
    """Reset the DBOS instance. Used for testing."""
    global _dbos_instance
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

    Returns:
        DBOSClient instance for enqueueing workflows
    """
    global _dbos_client
    if _dbos_client is None:
        sync_url = _get_sync_database_url()
        _dbos_client = DBOSClient(system_database_url=sync_url)
    return _dbos_client


def reset_dbos_client() -> None:
    """Reset the DBOSClient instance. Used for testing."""
    global _dbos_client
    _dbos_client = None


def validate_dbos_connection(dbos_instance: DBOS) -> bool:
    """Validate DBOS can connect to its system database.

    Executes a simple query against the DBOS schema to verify:
    1. Database connectivity works
    2. DBOS system tables exist (created by launch())

    Args:
        dbos_instance: The launched DBOS instance

    Returns:
        True if validation succeeds

    Raises:
        RuntimeError: If connection or schema validation fails
    """
    import psycopg

    config = get_dbos_config()
    db_url = config["system_database_url"]

    try:
        with psycopg.connect(db_url) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = 'dbos' AND table_name = 'workflow_status')"
            )
            exists = cur.fetchone()[0]
            if not exists:
                raise RuntimeError("DBOS system tables not found in 'dbos' schema")
        return True
    except psycopg.Error as e:
        raise RuntimeError(f"DBOS database connection failed: {e}") from e
