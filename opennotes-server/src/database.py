import asyncio
import gc
import json
from collections.abc import AsyncGenerator
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

        if not isinstance(value, dict) or "encrypted" not in value:
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
_engine_loop: object | None = None


def _create_engine() -> AsyncEngine:
    """Create the async engine with appropriate settings for PostgreSQL."""
    cfg = get_settings()
    return create_async_engine(
        cfg.DATABASE_URL,
        echo=cfg.DEBUG,
        future=True,
        pool_pre_ping=True,
        pool_size=cfg.DB_POOL_SIZE,
        max_overflow=cfg.DB_POOL_MAX_OVERFLOW,
        pool_timeout=cfg.DB_POOL_TIMEOUT,
        pool_recycle=cfg.DB_POOL_RECYCLE,
    )


def get_engine() -> AsyncEngine:
    """Get or create the async engine.

    Automatically detects if the event loop has changed (as happens in tests with
    asyncio_default_fixture_loop_scope=function) and creates a new engine for the
    new loop to avoid "Task got Future attached to a different loop" errors.
    """
    global _engine  # noqa: PLW0603 - Module-level lazy-loaded singleton for async engine, necessary for event loop awareness in test suite
    global _engine_loop  # noqa: PLW0603 - Tracks current event loop to detect loop changes between tests

    if _engine is None:
        _engine = _create_engine()
        try:
            _engine_loop = asyncio.get_running_loop()
        except RuntimeError:
            _engine_loop = None
    else:
        try:
            current_loop = asyncio.get_running_loop()
            if _engine_loop is not current_loop:
                old_engine = _engine
                _engine = _create_engine()
                _engine_loop = current_loop

                del old_engine
                gc.collect()
        except RuntimeError:
            pass

    return _engine


def get_session_maker() -> async_sessionmaker[AsyncSession]:
    """Get or create the async session maker."""
    global _async_session_maker  # noqa: PLW0603 - Module-level lazy-loaded singleton, recreated when event loop changes

    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    if _async_session_maker is None or (current_loop and current_loop != _engine_loop):
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
    global _engine, _async_session_maker  # noqa: PLW0603 - Cleanup module-level singletons on shutdown
    if _engine is not None:
        await _engine.dispose()
        _engine = None
    _async_session_maker = None


def _reset_database_for_test_loop() -> None:
    """
    Reset database engine and session maker for a new test event loop.

    When using asyncio_default_fixture_loop_scope=function in pytest.ini,
    each test gets a fresh event loop. The async engine and session maker
    are bound to the event loop they were created in. Reusing them across
    tests causes "Task got Future attached to a different loop" errors.

    This function disposes the engine's connection pool (synchronously via
    sync_engine) and resets the module-level variables so the next call to
    get_engine() or get_session_maker() creates new ones bound to the
    current event loop.
    """
    global _engine, _async_session_maker, _engine_loop  # noqa: PLW0603 - Reset singletons for fresh event loop in tests
    if _engine is not None:
        _engine.sync_engine.dispose()
    _engine = None
    _async_session_maker = None
    _engine_loop = None
