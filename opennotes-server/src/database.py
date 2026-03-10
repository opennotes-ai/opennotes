import asyncio
import json
import threading
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


def get_direct_sync_url() -> str:
    cfg = get_settings()
    url = cfg.DATABASE_DIRECT_URL or cfg.DATABASE_URL
    if not url:
        raise ValueError("DATABASE_URL environment variable required")
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql://", 1)
    if url.startswith("postgresql://"):
        return url
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql://", 1)
    return f"postgresql://{url}"


_engines: dict[int, tuple[AsyncEngine, asyncio.AbstractEventLoop | None]] = {}
_session_makers: dict[int, async_sessionmaker[AsyncSession]] = {}
_db_lock = threading.RLock()


def _create_engine() -> AsyncEngine:
    """Create the async engine with two-tier pooling (app QueuePool -> Supavisor -> PG).

    App-side QueuePool reuses connections to Supavisor, avoiding DNS/TLS overhead
    per request. Supavisor multiplexes onto bounded PG backends.

    statement_cache_size=0 disables asyncpg native prepared statement cache.
    prepared_statement_cache_size=0 disables SQLAlchemy asyncpg dialect cache (default 100).
    Both are required for Supavisor transaction-mode pooling (prepared statements
    created on one backend may not exist on another).
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
        connect_args={
            "statement_cache_size": 0,
            "prepared_statement_cache_size": 0,
        },
    )


def get_engine() -> AsyncEngine:
    """Get or create an async engine for the current event loop.

    Each event loop gets its own AsyncEngine, keyed by ``id(loop)``.  When no
    loop is running the key is ``0``.  Entries whose tracked loop has closed
    are lazily pruned on every access so the dict does not grow unboundedly.
    """
    with _db_lock:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        loop_key = id(loop) if loop is not None else 0

        if loop_key in _engines:
            engine, tracked_loop = _engines[loop_key]
            if tracked_loop is None or not tracked_loop.is_closed():
                return engine
            del _engines[loop_key]
            _session_makers.pop(loop_key, None)

        stale = [k for k, (_, lp) in _engines.items() if lp is not None and lp.is_closed()]
        for k in stale:
            del _engines[k]
            _session_makers.pop(k, None)

        engine = _create_engine()
        _engines[loop_key] = (engine, loop)
        return engine


def get_session_maker() -> async_sessionmaker[AsyncSession]:
    """Get or create an async session maker for the current event loop."""
    with _db_lock:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        loop_key = id(loop) if loop is not None else 0

        engine = get_engine()

        if loop_key in _session_makers:
            return _session_makers[loop_key]

        maker = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
        _session_makers[loop_key] = maker
        return maker


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
    with _db_lock:
        engines_to_dispose = list(_engines.values())
        _engines.clear()
        _session_makers.clear()

    for engine, _ in engines_to_dispose:
        await engine.dispose()


def _reset_database_for_test_loop() -> None:  # pyright: ignore[reportUnusedFunction]
    """
    Reset all per-loop engines and session makers for a new test event loop.

    When using asyncio_default_fixture_loop_scope=function in pytest.ini,
    each test gets a fresh event loop. This clears all entries so the next
    call to get_engine() or get_session_maker() creates fresh instances.
    Old engines are left for GC (no synchronous dispose to avoid
    MissingGreenlet).
    """
    with _db_lock:
        _engines.clear()
        _session_makers.clear()
