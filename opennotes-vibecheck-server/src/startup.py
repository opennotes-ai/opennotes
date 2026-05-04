from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

import asyncpg
from fastapi import FastAPI
from supabase import Client, create_client

from src.cache.supabase_cache import SupabaseCache
from src.config import get_settings
from src.monitoring import configure_logfire, get_logger

logger = get_logger(__name__)

_SCHEMA_PATH = Path(__file__).parent / "cache" / "schema.sql"

# Supavisor (transaction-mode pooler) requires `statement_cache_size=0` because
# asyncpg prepared-statement reuse is invalid across connection swaps.
_DEFAULT_POOLER_PORT = 6543
_DEFAULT_POOLER_HOST = "aws-1-us-east-1.pooler.supabase.com"
_SUPABASE_PROJECT_URL_RE = re.compile(
    r"(?:https://)?[a-z0-9-]+\.supabase\.co",
    re.IGNORECASE,
)


def _build_supabase_client(url: str, key: str) -> Client:
    return create_client(url, key)


def _project_ref_from_url(supabase_url: str) -> str | None:
    host = urlparse(supabase_url).hostname
    if not host:
        return None
    return host.split(".", 1)[0] or None


async def _create_db_pool(
    *,
    supabase_url: str,
    db_password: str,
    host: str,
    port: int,
) -> asyncpg.Pool:
    project_ref = _project_ref_from_url(supabase_url)
    if not project_ref:
        raise RuntimeError(
            f"cannot derive Supabase project ref from VIBECHECK_SUPABASE_URL={supabase_url!r}"
        )
    pool = await asyncpg.create_pool(
        host=host,
        port=port,
        user=f"postgres.{project_ref}",
        password=db_password,
        database="postgres",
        ssl="require",
        statement_cache_size=0,
        min_size=2,
        max_size=10,
    )
    if pool is None:
        raise RuntimeError("asyncpg.create_pool returned None")
    return pool


def _apply_schema(client: Client) -> None:
    if not _SCHEMA_PATH.exists():
        logger.warning("vibecheck cache schema.sql not found at %s", _SCHEMA_PATH)
        return
    sql = _SCHEMA_PATH.read_text()
    try:
        client.postgrest.rpc("exec_sql", {"sql": sql}).execute()
    except Exception as exc:

        def _redact(match: re.Match[str]) -> str:
            prefix = "https://" if match.group(0).lower().startswith("https://") else ""
            return f"{prefix}<supabase-project>.supabase.co"

        redacted_message = _SUPABASE_PROJECT_URL_RE.sub(_redact, str(exc))
        logger.error(
            "vibecheck schema apply via exec_sql RPC failed: %s",
            redacted_message,
            exc_info=True,
        )
        raise RuntimeError(redacted_message) from exc


_EXTRACTOR_TO_THREAD_CALL_SITES = 3
_DEFAULT_THREAD_POOL_CAP = 64


def _resolve_thread_pool_workers(container_concurrency: int) -> int:
    """Size the asyncio default executor for Cloud Run worst-case fan-out.

    The utterance extractor wraps `_sanitize_html`, `attribute_media`, and the
    optional `get_html` agent tool in `asyncio.to_thread`. At
    `containerConcurrency=80` that is up to 240 simultaneous thread tasks, far
    above asyncio's default `min(32, cpu_count + 4)` (~5-6 threads on a 1-2
    vCPU Cloud Run instance). We size for the worst case but cap to keep
    thread-context overhead bounded on small instances.
    """
    requested = max(1, container_concurrency) * _EXTRACTOR_TO_THREAD_CALL_SITES
    return min(requested, _DEFAULT_THREAD_POOL_CAP)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    from src.services.pydantic_patches import apply_all_patches

    apply_all_patches()

    # Install Logfire span scrubbing before any route handler (and therefore
    # any pydantic-ai agent invocation) can emit spans. `configure_logfire`
    # is idempotent and swallows ImportError if the logfire package is
    # unavailable in a given environment (e.g. stripped-down unit runs).
    configure_logfire()
    settings = get_settings()

    # Replace asyncio's default ThreadPoolExecutor so `asyncio.to_thread` in
    # the extractor (TASK-1474.23.04) does not saturate at ~5-6 workers under
    # Cloud Run's containerConcurrency=80. See `_resolve_thread_pool_workers`
    # for the sizing rationale (TASK-1474.23.03.24).
    thread_pool_workers = _resolve_thread_pool_workers(
        settings.VIBECHECK_CONTAINER_CONCURRENCY
    )
    executor = ThreadPoolExecutor(
        max_workers=thread_pool_workers,
        thread_name_prefix="vibecheck-default",
    )
    asyncio.get_running_loop().set_default_executor(executor)
    app.state.default_executor = executor
    logger.info(
        "vibecheck default ThreadPoolExecutor sized for Cloud Run concurrency "
        "(workers=%s, container_concurrency=%s)",
        thread_pool_workers,
        settings.VIBECHECK_CONTAINER_CONCURRENCY,
    )

    try:
        cache_key = (
            settings.VIBECHECK_SUPABASE_SERVICE_ROLE_KEY
            or settings.VIBECHECK_SUPABASE_ANON_KEY
        )
        if settings.VIBECHECK_SUPABASE_URL and cache_key:
            # The analysis cache writes through vibecheck_analyses, which is RLS-
            # locked to service_role (src/cache/schema.sql). Prefer the
            # service-role key; fall back to anon so dev envs without the
            # lockdown applied keep working.
            client = _build_supabase_client(settings.VIBECHECK_SUPABASE_URL, cache_key)
            _apply_schema(client)
            app.state.cache = SupabaseCache(client, ttl_hours=settings.CACHE_TTL_HOURS)
            logger.info("vibecheck supabase cache initialized (ttl=%sh)", settings.CACHE_TTL_HOURS)
        else:
            app.state.cache = None
            logger.warning("vibecheck supabase cache disabled: missing VIBECHECK_SUPABASE_* env")

        # asyncpg pool for the analyze pipeline. Routes raise 503 with
        # error_code="internal" when this is missing, so a deploy without the
        # right Supabase credentials is loud rather than silently broken.
        if settings.VIBECHECK_SUPABASE_URL and settings.VIBECHECK_SUPABASE_DB_PASSWORD:
            db_host = settings.VIBECHECK_DATABASE_HOST or _DEFAULT_POOLER_HOST
            if not settings.VIBECHECK_DATABASE_HOST:
                logger.warning(
                    "VIBECHECK_DATABASE_HOST unset; falling back to default pooler host %s",
                    _DEFAULT_POOLER_HOST,
                )
            try:
                app.state.db_pool = await _create_db_pool(
                    supabase_url=settings.VIBECHECK_SUPABASE_URL,
                    db_password=settings.VIBECHECK_SUPABASE_DB_PASSWORD,
                    host=db_host,
                    port=settings.VIBECHECK_DATABASE_PORT or _DEFAULT_POOLER_PORT,
                )
                logger.info(
                    "vibecheck db pool initialized (host=%s port=%s)",
                    db_host,
                    settings.VIBECHECK_DATABASE_PORT or _DEFAULT_POOLER_PORT,
                )
            except Exception as exc:
                logger.error("vibecheck db pool initialization failed: %s", exc)
                raise
        else:
            app.state.db_pool = None
            logger.warning(
                "vibecheck db pool disabled: missing VIBECHECK_SUPABASE_URL / VIBECHECK_SUPABASE_DB_PASSWORD"
            )

        yield
    finally:
        pool = getattr(app.state, "db_pool", None)
        if pool is not None:
            await pool.close()
            app.state.db_pool = None
        app.state.cache = None
        executor = getattr(app.state, "default_executor", None)
        if executor is not None:
            executor.shutdown(wait=False, cancel_futures=True)
            app.state.default_executor = None
