import asyncio
import json
import threading
from collections.abc import AsyncGenerator
from types import MappingProxyType
from typing import Any

from cryptography.fernet import Fernet
from sqlalchemy import TypeDecorator, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from src.config import get_settings


class EncryptedJSONB(TypeDecorator[dict[str, Any] | None]):
    """
    Encrypted JSONB column type using Fernet symmetric encryption.

    Transparently encrypts JSON data before storing in the database and
    decrypts when reading. Provides column-level encryption for sensitive
    data like credentials and password hashes.

    Security considerations:
    - Uses Fernet (AES-128 in CBC mode with HMAC authentication)
    - Encryption key must be stored securely (environment variable)
    - Key rotation requires re-encrypting all existing data
    - Does not protect against database administrator access
    - Adds defense-in-depth layer for database dumps and backups

    Usage:
        credentials: Mapped[dict[str, Any] | None] = mapped_column(
            EncryptedJSONB, nullable=True
        )
    """

    impl = JSONB
    cache_ok = True

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._fernet = Fernet(get_settings().CREDENTIALS_ENCRYPTION_KEY.encode())

    def process_bind_param(
        self, value: dict[str, Any] | None, dialect: Any
    ) -> dict[str, Any] | None:
        """Encrypt value before storing in database."""
        if value is None:
            return None

        json_str = json.dumps(value, sort_keys=True)
        encrypted_bytes = self._fernet.encrypt(json_str.encode())
        return {"encrypted": encrypted_bytes.decode("utf-8")}

    def process_result_value(
        self, value: dict[str, Any] | None, dialect: Any
    ) -> dict[str, Any] | None:
        """Decrypt value after reading from database."""
        if value is None:
            return None

        if not isinstance(value, dict) or "encrypted" not in value:  # pyright: ignore[reportUnnecessaryIsInstance]
            return value

        encrypted_str = value["encrypted"]
        decrypted_bytes = self._fernet.decrypt(encrypted_str.encode())
        result: Any = json.loads(decrypted_bytes.decode())
        if isinstance(result, dict):
            return result
        return None


class Base(DeclarativeBase):
    pass


# Module-level variables for lazy initialization
_engine: AsyncEngine | None = None
_async_session_maker: async_sessionmaker[AsyncSession] | None = None
_engine_loop: asyncio.AbstractEventLoop | None = None
_db_lock = threading.RLock()


SUPAVISOR_CONNECT_ARGS: MappingProxyType[str, object] = MappingProxyType(
    {
        "statement_cache_size": 0,
        "prepared_statement_cache_size": 0,
        "prepared_statement_name_func": lambda: "",
    }
)


def _create_engine() -> AsyncEngine:
    """Create the async engine with two-tier pooling (app QueuePool -> Supavisor -> PG).

    App-side QueuePool reuses connections to Supavisor, avoiding DNS/TLS overhead
    per request. Supavisor multiplexes onto bounded PG backends.

    statement_cache_size=0 disables asyncpg native prepared statement cache.
    prepared_statement_cache_size=0 disables SQLAlchemy asyncpg dialect cache (default 100).
    prepared_statement_name_func=lambda:'' forces anonymous prepared statements so
    asyncpg never sends a named statement that collides across pooled backends.
    All three are required for Supavisor transaction-mode pooling.
    """
    cfg = get_settings()
    return create_async_engine(
        cfg.DATABASE_URL,
        echo=cfg.DEBUG,
        future=True,
        pool_size=cfg.DB_POOL_SIZE,
        max_overflow=cfg.DB_POOL_MAX_OVERFLOW,
        pool_timeout=cfg.DB_POOL_TIMEOUT,
        pool_recycle=cfg.DB_POOL_RECYCLE,
        pool_pre_ping=True,
        connect_args=SUPAVISOR_CONNECT_ARGS,
    )


def get_engine() -> AsyncEngine:
    """Get or create the async engine.

    Only recreates the engine when the tracked event loop is closed (e.g., between
    pytest test functions with asyncio_default_fixture_loop_scope=function).
    A different-but-alive loop (as seen from DBOS worker threads) does NOT trigger
    recreation, preventing MissingGreenlet errors from synchronous pool disposal.
    """
    global _engine  # noqa: PLW0603 - Module-level lazy-loaded singleton for async engine, necessary for event loop awareness in test suite
    global _engine_loop  # noqa: PLW0603 - Tracks current event loop to detect loop changes between tests

    with _db_lock:
        if _engine is None or (_engine_loop is not None and _engine_loop.is_closed()):
            _engine = _create_engine()
            try:
                _engine_loop = asyncio.get_running_loop()
            except RuntimeError:
                _engine_loop = None

        return _engine


def get_session_maker() -> async_sessionmaker[AsyncSession]:
    """Get or create the async session maker."""
    global _async_session_maker  # noqa: PLW0603 - Module-level lazy-loaded singleton, recreated when event loop changes

    with _db_lock:
        if _async_session_maker is None or (_engine_loop is not None and _engine_loop.is_closed()):
            _async_session_maker = async_sessionmaker(
                get_engine(),
                class_=AsyncSession,
                expire_on_commit=False,
                autocommit=False,
                autoflush=False,
            )
        return _async_session_maker


# Make engine and async_session_maker available as module attributes for backwards compatibility
def __getattr__(name: str) -> AsyncEngine | async_sessionmaker[AsyncSession]:
    if name == "engine":
        return get_engine()
    if name == "async_session_maker":
        return get_session_maker()
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    session_maker = get_session_maker()
    async with session_maker() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """
    Initialize database connection.

    This function only verifies database connectivity. It does NOT create schema.
    Schema management is handled by Alembic migrations.

    Run migrations before starting the server:
        alembic upgrade head

    Raises:
        Exception: If database connection fails
    """
    eng = get_engine()
    async with eng.begin() as conn:
        await conn.execute(text("SELECT 1"))


async def close_db() -> None:
    global _engine, _async_session_maker, _engine_loop  # noqa: PLW0603 - Cleanup module-level singletons on shutdown
    with _db_lock:
        if _engine is not None:
            await _engine.dispose()
            _engine = None
        _async_session_maker = None
        _engine_loop = None


def _reset_database_for_test_loop() -> None:  # pyright: ignore[reportUnusedFunction]
    """
    Reset database engine and session maker for a new test event loop.

    When using asyncio_default_fixture_loop_scope=function in pytest.ini,
    each test gets a fresh event loop. This resets the module-level
    singletons so the next call to get_engine() or get_session_maker()
    creates new ones bound to the current event loop. The old engine is
    left for GC (no synchronous dispose to avoid MissingGreenlet).
    """
    global _engine, _async_session_maker, _engine_loop  # noqa: PLW0603 - Reset singletons for fresh event loop in tests
    with _db_lock:
        _engine = None
        _async_session_maker = None
        _engine_loop = None
