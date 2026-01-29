"""DBOS configuration and initialization."""

from dbos import DBOS, DBOSConfig

from src.config import settings

_dbos_instance: DBOS | None = None


def get_dbos_config() -> DBOSConfig:
    """Build DBOS configuration from environment.

    Uses dedicated 'dbos' schema to isolate DBOS tables from
    application tables in the 'public' schema.

    Note: DBOS uses synchronous psycopg internally, so we convert
    the async DATABASE_URL (postgresql+asyncpg://) to sync format.
    """
    database_url = settings.DATABASE_URL
    if not database_url:
        raise ValueError("DATABASE_URL environment variable required for DBOS")

    sync_url = database_url.replace("postgresql+asyncpg://", "postgresql://")

    config: DBOSConfig = {
        "name": "opennotes-server",
        "system_database_url": sync_url,
        "dbos_system_schema": "dbos",
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
