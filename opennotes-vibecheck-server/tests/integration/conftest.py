"""Shared integration-test fixtures (TASK-1473.22).

Each test in `tests/integration/` exercises a multi-component flow that
needs:

  * a real Postgres backing the orchestrator + slot writer (testcontainers
    is the only mock-free way to validate the JSONB merge + advisory-lock
    + sweeper SQL paths).
  * a fake scrape cache backed by the same Postgres so the cache-rescue
    test can assert that a second submit reuses the row written by the
    first job rather than re-invoking Firecrawl.
  * the `vibecheck_sweep_orphan_jobs` SQL function from the production
    schema, ported into the minimal DDL so the sweeper test can assert
    against the real function body.
  * the OIDC verifier mock + Authorization header pair so the
    `/_internal/jobs/.../run` endpoint accepts test traffic.

Why we don't use the Supabase Python client directly: the production
schema requires Supabase-specific extensions (`pg_cron`) and RLS policies
that are not available in vanilla Postgres. Spinning up a Supabase-shaped
DB inside a unit test is heavier than the contract under test requires —
the orchestrator and route handlers talk to asyncpg via `app.state.db_pool`
for everything except the scrape cache, and the scrape cache surface is
small enough to back with a Postgres-shaped fake.

`AsyncpgScrapeCache` below mirrors `SupabaseScrapeCache`'s public methods
(`get`, `put`, `evict`, `signed_screenshot_url`) but persists into
`vibecheck_scrapes` via the same asyncpg pool the orchestrator uses. The
behavior contract is the same: get-after-put returns a CachedScrape; put
honors the 72h TTL; evict removes the row.
"""
from __future__ import annotations

import json
import socket
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import asyncpg
import httpx
import pytest
from testcontainers.postgres import PostgresContainer

from src.cache.scrape_cache import CachedScrape
from src.firecrawl_client import ScrapeMetadata, ScrapeResult
from src.main import app
from src.routes import analyze as analyze_route

_REAL_GETADDRINFO = socket.getaddrinfo


# ---------------------------------------------------------------------------
# Postgres testcontainers fixture + minimal DDL.
# ---------------------------------------------------------------------------

# We mirror src/cache/schema.sql for the tables the orchestrator + slot
# writers + analyze route + sweeper touch. pg_cron and RLS are out of scope
# for an integration test — the sweeper function is exercised by direct
# SQL invocation, not by a scheduled cron job.
INTEGRATION_DDL = """
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS vibecheck_analyses (
    url TEXT PRIMARY KEY,
    sidebar_payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS vibecheck_analyses_expires_at_idx
    ON vibecheck_analyses(expires_at);

CREATE TABLE IF NOT EXISTS vibecheck_jobs (
    job_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    url TEXT NOT NULL,
    normalized_url TEXT NOT NULL,
    host TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    attempt_id UUID NOT NULL DEFAULT uuid_generate_v4(),
    error_code TEXT,
    error_message TEXT,
    error_host TEXT,
    sections JSONB NOT NULL DEFAULT '{}'::jsonb,
    sidebar_payload JSONB,
    cached BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    heartbeat_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    test_fail_slug TEXT,
    safety_recommendation JSONB,
    last_stage TEXT,
    preview_description TEXT,
    extract_transient_attempts INT NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS vibecheck_jobs_normalized_url_idx
    ON vibecheck_jobs(normalized_url);
CREATE INDEX IF NOT EXISTS vibecheck_jobs_status_created_at_idx
    ON vibecheck_jobs(status, created_at)
    WHERE status NOT IN ('done', 'partial', 'failed');
CREATE INDEX IF NOT EXISTS vibecheck_jobs_heartbeat_idx
    ON vibecheck_jobs(heartbeat_at)
    WHERE status IN ('extracting', 'analyzing');
CREATE UNIQUE INDEX IF NOT EXISTS
    vibecheck_jobs_unique_done_cached_normalized_url
    ON vibecheck_jobs(normalized_url)
    WHERE status = 'done' AND cached = true;

CREATE TABLE IF NOT EXISTS vibecheck_scrapes (
    scrape_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    normalized_url TEXT NOT NULL UNIQUE,
    url TEXT NOT NULL,
    host TEXT NOT NULL,
    page_kind TEXT NOT NULL DEFAULT 'other',
    page_title TEXT,
    markdown TEXT,
    html TEXT,
    screenshot_storage_key TEXT,
    scraped_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL DEFAULT (now() + INTERVAL '72 hours')
);

CREATE TABLE IF NOT EXISTS vibecheck_web_risk_lookups (
    url TEXT PRIMARY KEY,
    finding_payload JSONB NOT NULL,
    checked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS vibecheck_web_risk_lookups_expires_at_idx
    ON vibecheck_web_risk_lookups (expires_at);

CREATE TABLE IF NOT EXISTS vibecheck_job_utterances (
    utterance_pk UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    job_id UUID NOT NULL REFERENCES vibecheck_jobs(job_id) ON DELETE CASCADE,
    utterance_id TEXT,
    kind TEXT NOT NULL,
    text TEXT NOT NULL,
    author TEXT,
    timestamp_at TIMESTAMPTZ,
    parent_id TEXT,
    position INT NOT NULL DEFAULT 0,
    page_title TEXT,
    page_kind TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Sweeper function — verbatim copy of src/cache/schema.sql so the
-- sweeper test exercises the real function body. SECURITY DEFINER is
-- elided since the testcontainer Postgres has no RLS configured.
CREATE OR REPLACE FUNCTION vibecheck_sweep_orphan_jobs()
RETURNS INT
LANGUAGE plpgsql
AS $$
DECLARE
    swept INT;
BEGIN
    UPDATE public.vibecheck_jobs
    SET
        status        = 'failed',
        error_code    = 'timeout',
        error_message = COALESCE(
            error_message,
            CASE
                WHEN status = 'pending' THEN 'job pending > 240s without dispatch'
                ELSE 'worker heartbeat stale > 30s'
            END
        ),
        updated_at    = now(),
        finished_at   = now()
    WHERE
        status NOT IN ('done', 'partial', 'failed')
        AND (
            (status = 'pending' AND (now() - created_at) > INTERVAL '240 seconds')
            OR (
                status IN ('extracting', 'analyzing')
                AND (now() - COALESCE(heartbeat_at, updated_at, created_at))
                    > INTERVAL '30 seconds'
            )
        );
    GET DIAGNOSTICS swept = ROW_COUNT;
    RETURN swept;
END;
$$;
"""


@pytest.fixture(autouse=True)
def _restore_real_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    """Undo the suite-wide `_stub_dns` so testcontainers can reach localhost."""
    monkeypatch.setattr(socket, "getaddrinfo", _REAL_GETADDRINFO)


@pytest.fixture(scope="module")
def _postgres_container() -> Iterator[PostgresContainer]:
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg


@pytest.fixture
async def db_pool(
    _postgres_container: PostgresContainer,
) -> AsyncIterator[Any]:
    """Fresh schema per test so ordering effects can't carry between cases."""
    raw = _postgres_container.get_connection_url()
    dsn = raw.replace("postgresql+psycopg2://", "postgresql://")
    pool = await asyncpg.create_pool(dsn, min_size=2, max_size=8)
    assert pool is not None
    async with pool.acquire() as conn:
        await conn.execute(
            "DROP TABLE IF EXISTS vibecheck_job_utterances CASCADE; "
            "DROP TABLE IF EXISTS vibecheck_scrapes CASCADE; "
            "DROP TABLE IF EXISTS vibecheck_analyses CASCADE; "
            "DROP TABLE IF EXISTS vibecheck_web_risk_lookups CASCADE; "
            "DROP TABLE IF EXISTS vibecheck_jobs CASCADE;"
        )
        await conn.execute(INTEGRATION_DDL)
    try:
        yield pool
    finally:
        await pool.close()


# ---------------------------------------------------------------------------
# Asyncpg-backed scrape cache (Supabase shape, Postgres backing).
# ---------------------------------------------------------------------------


class AsyncpgScrapeCache:
    """`SupabaseScrapeCache` shape over an asyncpg pool.

    Behavior contract is identical to `SupabaseScrapeCache.get/put/evict`:
    rows live in `vibecheck_scrapes` with a 72h TTL; `get` enforces a
    server-side `expires_at > now()` predicate; `put` UPSERTs on
    normalized_url; `evict` deletes by normalized_url. We do not exercise
    the Storage bucket — `signed_screenshot_url` returns None.

    `signed_screenshot_url` is async to mirror the production surface so
    callers (the extractor's tool surface) await it without changes.
    """

    def __init__(self, pool: Any, *, ttl_hours: int = 72) -> None:
        self._pool = pool
        self._ttl_hours = ttl_hours

    async def get(self, url: str) -> CachedScrape | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT url, host, page_title, markdown, html,
                       screenshot_storage_key
                FROM vibecheck_scrapes
                WHERE normalized_url = $1
                  AND expires_at > now()
                """,
                url,
            )
        if row is None:
            return None
        metadata = ScrapeMetadata(
            title=row["page_title"],
            source_url=row["url"],
        )
        return CachedScrape(
            markdown=row["markdown"],
            html=row["html"],
            screenshot=None,
            metadata=metadata,
            storage_key=row["screenshot_storage_key"],
        )

    async def put(
        self,
        url: str,
        scrape: ScrapeResult,
        screenshot_bytes: bytes | None = None,
    ) -> CachedScrape:
        host = (
            scrape.metadata.source_url.split("://", 1)[-1].split("/", 1)[0]
            if scrape.metadata and scrape.metadata.source_url
            else url.split("://", 1)[-1].split("/", 1)[0]
        )
        now = datetime.now(UTC)
        expires = now + timedelta(hours=self._ttl_hours)
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO vibecheck_scrapes (
                    normalized_url, url, host, page_kind, page_title,
                    markdown, html, screenshot_storage_key,
                    scraped_at, expires_at
                )
                VALUES ($1, $2, $3, 'other', $4, $5, $6, NULL, $7, $8)
                ON CONFLICT (normalized_url) DO UPDATE
                SET url = EXCLUDED.url,
                    host = EXCLUDED.host,
                    page_kind = EXCLUDED.page_kind,
                    page_title = EXCLUDED.page_title,
                    markdown = EXCLUDED.markdown,
                    html = EXCLUDED.html,
                    screenshot_storage_key = EXCLUDED.screenshot_storage_key,
                    scraped_at = EXCLUDED.scraped_at,
                    expires_at = EXCLUDED.expires_at
                """,
                url,
                url,
                host,
                scrape.metadata.title if scrape.metadata else None,
                scrape.markdown,
                scrape.html,
                now,
                expires,
            )
        return CachedScrape(
            markdown=scrape.markdown,
            html=scrape.html,
            raw_html=scrape.raw_html,
            screenshot=scrape.screenshot,
            links=scrape.links,
            metadata=scrape.metadata,
            warning=scrape.warning,
            storage_key=None,
        )

    async def evict(self, url: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM vibecheck_scrapes WHERE normalized_url = $1", url
            )

    async def signed_screenshot_url(self, scrape: ScrapeResult) -> str | None:
        return None


@pytest.fixture
def scrape_cache(db_pool: Any) -> AsyncpgScrapeCache:
    return AsyncpgScrapeCache(db_pool)


# ---------------------------------------------------------------------------
# Recording fake Firecrawl client used by integration tests.
# ---------------------------------------------------------------------------


class RecordingFirecrawlClient:
    """Programmable Firecrawl stand-in with a per-URL result map.

    Each `scrape(url, ...)` call appends to `calls`. Tests that want to
    prove the cache-rescue path NOT call Firecrawl on the second submit
    assert `len(calls) == 1` after both submits complete.

    `metadata.source_url` defaults to the requested URL so the post-scrape
    SSRF revalidator passes; the SSRF integration test overrides this to
    a private IP.
    """

    def __init__(
        self,
        *,
        results_by_url: dict[str, ScrapeResult] | None = None,
        default_markdown: str = "Sample post content with substantive prose.",
    ) -> None:
        self.calls: list[str] = []
        self._results_by_url = dict(results_by_url or {})
        self._default_markdown = default_markdown

    async def scrape(
        self,
        url: str,
        formats: list[str],
        *,
        only_main_content: bool = False,
    ) -> ScrapeResult:
        self.calls.append(url)
        if url in self._results_by_url:
            return self._results_by_url[url]
        return ScrapeResult(
            markdown=self._default_markdown,
            html=f"<article>{self._default_markdown}</article>",
            metadata=ScrapeMetadata(
                title="Test Page", source_url=url
            ),
        )


# ---------------------------------------------------------------------------
# OIDC + ASGI client wiring.
# ---------------------------------------------------------------------------


_DEFAULT_OIDC_AUDIENCE = "https://vibecheck.test"
_DEFAULT_OIDC_EMAIL = (
    "vibecheck-tasks@open-notes-core.iam.gserviceaccount.com"
)


@pytest.fixture
def oidc_headers() -> dict[str, str]:
    return {"Authorization": "Bearer integration.test.token"}


@pytest.fixture
def install_oidc_mock(monkeypatch: pytest.MonkeyPatch):
    """Install a happy-path OIDC verifier and matching settings."""
    from unittest.mock import MagicMock

    from src.auth import cloud_tasks_oidc
    from src.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("VIBECHECK_SERVER_URL", _DEFAULT_OIDC_AUDIENCE)
    monkeypatch.setenv("VIBECHECK_TASKS_ENQUEUER_SA", _DEFAULT_OIDC_EMAIL)
    get_settings.cache_clear()

    mock = MagicMock(
        return_value={
            "iss": "https://accounts.google.com",
            "aud": _DEFAULT_OIDC_AUDIENCE,
            "email": _DEFAULT_OIDC_EMAIL,
            "email_verified": True,
        }
    )
    monkeypatch.setattr(cloud_tasks_oidc, "_verify_oauth2_token", mock)
    yield mock
    get_settings.cache_clear()


@pytest.fixture
async def http_client(
    db_pool: Any, install_oidc_mock: Any
) -> AsyncIterator[httpx.AsyncClient]:
    """ASGI client with the test pool installed on app.state."""
    from unittest.mock import AsyncMock

    app.state.cache = None
    app.state.db_pool = db_pool
    app.state.limiter = analyze_route.limiter
    analyze_route.limiter.reset()

    # Ensure the route's enqueue surface is harmless by default — the
    # integration tests that exercise the worker call it directly via
    # /_internal/...
    enqueue_mock = AsyncMock(return_value=None)
    original = analyze_route.enqueue_job
    analyze_route.enqueue_job = enqueue_mock  # type: ignore[assignment]

    # Page-URL Web Risk gate would otherwise hit the real Google API — stub
    # both the route's binding and the underlying function (used by the
    # orchestrator's `run_web_risk` worker) to "no findings" so submissions
    # of test URLs aren't rejected as `unsafe_url`. Tests that exercise the
    # unsafe-url branch override this.
    from src.analyses.safety import web_risk as web_risk_module
    from src.analyses.safety import web_risk_worker as web_risk_worker_module

    original_check_urls = analyze_route.check_urls
    original_check_urls_module = web_risk_module.check_urls
    original_check_urls_worker = web_risk_worker_module.check_urls
    no_findings = AsyncMock(return_value={})
    analyze_route.check_urls = no_findings  # type: ignore[assignment]
    web_risk_module.check_urls = no_findings  # type: ignore[assignment]
    web_risk_worker_module.check_urls = no_findings  # type: ignore[assignment]

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as c:
        yield c
    app.state.db_pool = None
    analyze_route.limiter.reset()
    analyze_route.enqueue_job = original  # type: ignore[assignment]
    analyze_route.check_urls = original_check_urls  # type: ignore[assignment]
    web_risk_module.check_urls = original_check_urls_module  # type: ignore[assignment]
    web_risk_worker_module.check_urls = original_check_urls_worker  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Test data helpers.
# ---------------------------------------------------------------------------


async def insert_pending_job(
    pool: Any, *, url: str = "https://example.com/work", attempt_id: UUID | None = None
) -> tuple[UUID, UUID]:
    attempt = attempt_id or uuid4()
    async with pool.acquire() as conn:
        job_id = await conn.fetchval(
            """
            INSERT INTO vibecheck_jobs (url, normalized_url, host, status, attempt_id)
            VALUES ($1, $1, 'example.com', 'pending', $2)
            RETURNING job_id
            """,
            url,
            attempt,
        )
    assert isinstance(job_id, UUID)
    return job_id, attempt


async def read_job(pool: Any, job_id: UUID) -> dict[str, Any]:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM vibecheck_jobs WHERE job_id = $1", job_id
        )
    assert row is not None
    return dict(row)


async def read_sections(pool: Any, job_id: UUID) -> dict[str, Any]:
    async with pool.acquire() as conn:
        raw = await conn.fetchval(
            "SELECT sections FROM vibecheck_jobs WHERE job_id = $1", job_id
        )
    return json.loads(raw) if isinstance(raw, str) else dict(raw)
