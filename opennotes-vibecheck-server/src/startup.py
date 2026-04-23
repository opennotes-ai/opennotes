from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from supabase import Client, create_client

from src.cache.supabase_cache import SupabaseCache
from src.config import get_settings
from src.monitoring import configure_logfire, get_logger

logger = get_logger(__name__)

_SCHEMA_PATH = Path(__file__).parent / "cache" / "schema.sql"


def _build_supabase_client(url: str, key: str) -> Client:
    return create_client(url, key)


def _apply_schema(client: Client) -> None:
    if not _SCHEMA_PATH.exists():
        logger.warning("vibecheck cache schema.sql not found at %s", _SCHEMA_PATH)
        return
    sql = _SCHEMA_PATH.read_text()
    try:
        client.postgrest.rpc("exec_sql", {"sql": sql}).execute()
    except Exception as exc:
        logger.info(
            "skipping in-app schema apply (run via supabase migration): %s",
            exc,
        )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Install Logfire span scrubbing before any route handler (and therefore
    # any pydantic-ai agent invocation) can emit spans. `configure_logfire`
    # is idempotent and swallows ImportError if the logfire package is
    # unavailable in a given environment (e.g. stripped-down unit runs).
    configure_logfire()
    settings = get_settings()
    if settings.VIBECHECK_SUPABASE_URL and settings.VIBECHECK_SUPABASE_ANON_KEY:
        client = _build_supabase_client(
            settings.VIBECHECK_SUPABASE_URL, settings.VIBECHECK_SUPABASE_ANON_KEY
        )
        _apply_schema(client)
        app.state.cache = SupabaseCache(client, ttl_hours=settings.CACHE_TTL_HOURS)
        logger.info("vibecheck supabase cache initialized (ttl=%sh)", settings.CACHE_TTL_HOURS)
    else:
        app.state.cache = None
        logger.warning("vibecheck supabase cache disabled: missing VIBECHECK_SUPABASE_* env")
    try:
        yield
    finally:
        app.state.cache = None
