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
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlparse
from uuid import UUID, uuid4

import asyncpg
import httpx
import pytest
from testcontainers.postgres import PostgresContainer

from src.cache.scrape_cache import CachedScrape
from src.cache.supabase_cache import normalize_url
from src.firecrawl_client import ScrapeMetadata, ScrapeResult
from src.main import app
from src.routes import analyze as analyze_route

ScrapeOutcome = ScrapeResult | BaseException | Callable[[], ScrapeResult]
# Per-URL outcome a recording client can serve: a fixed result, a raised
# exception, or a no-arg factory for state-dependent tests.

_REAL_GETADDRINFO = socket.getaddrinfo


# ---------------------------------------------------------------------------
# Postgres testcontainers fixture + minimal DDL.
# ---------------------------------------------------------------------------

# We mirror src/cache/schema.sql for the tables the orchestrator + slot
# writers + analyze route + sweeper touch. pg_cron, RLS, and the TASK-1490
# exec_sql/advisory-lock bootstrap are out of scope for an integration test:
# fixtures apply DDL directly and TASK-1490.03 audits production drift against
# the canonical schema.sql. The sweeper function is exercised by direct SQL
# invocation, not by a scheduled cron job.
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
    source_type TEXT NOT NULL DEFAULT 'url',
    attempt_id UUID NOT NULL DEFAULT uuid_generate_v4(),
    error_code TEXT,
    error_message TEXT,
    error_host TEXT,
    sections JSONB NOT NULL DEFAULT '{}'::jsonb,
    sidebar_payload JSONB,
    cached BOOLEAN NOT NULL DEFAULT false,
    source_type TEXT NOT NULL DEFAULT 'url',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    heartbeat_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    test_fail_slug TEXT,
    safety_recommendation JSONB,
    headline_summary JSONB,
    last_stage TEXT,
    preview_description TEXT,
    extract_transient_attempts INT NOT NULL DEFAULT 0,
    CONSTRAINT vibecheck_jobs_status_check
        CHECK (status IN ('pending', 'extracting', 'analyzing', 'done', 'partial', 'failed')),
    CONSTRAINT vibecheck_jobs_source_type_check
        CHECK (source_type IN ('url', 'pdf')),
    CONSTRAINT vibecheck_jobs_error_code_check
        CHECK (
            error_code IS NULL
            OR error_code IN (
                'invalid_url', 'unsafe_url', 'unsupported_site', 'upstream_error',
                'extraction_failed', 'section_failure', 'timeout',
                'pdf_too_large', 'pdf_extraction_failed',
                'rate_limited', 'internal'
            )
        ),
    CONSTRAINT vibecheck_jobs_source_type_check
        CHECK (source_type IN ('url', 'pdf', 'browser_html')),
    CONSTRAINT vibecheck_jobs_terminal_finished_at
        CHECK (
            (status NOT IN ('done', 'partial', 'failed') AND finished_at IS NULL)
            OR (status IN ('done', 'partial', 'failed') AND finished_at IS NOT NULL)
        )
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
    normalized_url TEXT NOT NULL,
    tier TEXT NOT NULL DEFAULT 'scrape'
        CHECK (tier IN ('scrape', 'interact', 'browser_html')),
    url TEXT NOT NULL,
    final_url TEXT,
    host TEXT NOT NULL,
    page_kind TEXT NOT NULL DEFAULT 'other',
    page_title TEXT,
    markdown TEXT,
    html TEXT,
    screenshot_storage_key TEXT,
    scraped_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL DEFAULT (now() + INTERVAL '72 hours'),
    evicted_at TIMESTAMPTZ,
    CONSTRAINT vibecheck_scrapes_page_kind_check
        CHECK (page_kind IN (
            'blog_post', 'forum_thread', 'hierarchical_thread',
            'blog_index', 'article', 'other'
        ))
);
CREATE UNIQUE INDEX IF NOT EXISTS
    vibecheck_scrapes_normalized_url_tier_idx
    ON vibecheck_scrapes (normalized_url, tier);

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
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT vibecheck_job_utterances_kind_check
        CHECK (kind IN ('post', 'comment', 'reply'))
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
    normalized_url; `evict` writes tombstones by normalized_url for fence
    protection. We do not exercise
    the Storage bucket — `signed_screenshot_url` returns None.

    `signed_screenshot_url` is async to mirror the production surface so
    callers (the extractor's tool surface) await it without changes.
    """

    def __init__(
        self,
        pool: Any,
        *,
        ttl_hours: int = 72,
        before_fence_read: Callable[[], Awaitable[None]] | None = None,
        after_fence_read: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self._pool = pool
        self._ttl_hours = ttl_hours
        self._before_fence_read = before_fence_read
        self._after_fence_read = after_fence_read

    async def get(
        self, url: str, *, tier: str = "scrape"
    ) -> CachedScrape | None:
        norm = normalize_url(url)
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT url, final_url, host, page_title, markdown, html,
                       screenshot_storage_key
                FROM vibecheck_scrapes
                WHERE normalized_url = $1
                  AND tier = $2
                  AND expires_at > now()
                """,
                norm,
                tier,
            )
        if row is None:
            return None
        source_url = row["final_url"] or row["url"]
        metadata = ScrapeMetadata(
            title=row["page_title"],
            source_url=source_url,
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
        *,
        tier: str = "scrape",
        screenshot_bytes: bytes | None = None,
    ) -> CachedScrape:
        norm = normalize_url(url)
        host = urlparse(norm).netloc
        put_started_at = datetime.now(UTC)
        metadata = scrape.metadata or ScrapeMetadata()
        final_url = metadata.source_url or url
        if self._before_fence_read is not None:
            await self._before_fence_read()
        async with self._pool.acquire() as conn:
            tombstone = await conn.fetchrow(
                """
                SELECT evicted_at
                FROM vibecheck_scrapes
                WHERE normalized_url = $1
                  AND tier = $2
                """,
                norm,
                tier,
            )
            if (
                tombstone is not None
                and tombstone["evicted_at"] is not None
                and tombstone["evicted_at"] >= put_started_at - timedelta(seconds=1)
            ):
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
        if self._after_fence_read is not None:
            await self._after_fence_read()
        now = datetime.now(UTC)
        expires = now + timedelta(hours=self._ttl_hours)
        async with self._pool.acquire() as conn:
            wrote_row = await conn.fetchval(
                """
                INSERT INTO vibecheck_scrapes (
                    normalized_url, tier, url, final_url, host, page_kind,
                    page_title,
                    markdown, html, screenshot_storage_key,
                    scraped_at, expires_at, evicted_at
                )
                VALUES (
                    $1, $2, $3, $4, $5, 'other', $6,
                    $7, $8, NULL, $9, $10, NULL
                )
                ON CONFLICT (normalized_url, tier) DO UPDATE
                SET url = EXCLUDED.url,
                    final_url = EXCLUDED.final_url,
                    host = EXCLUDED.host,
                    page_kind = EXCLUDED.page_kind,
                    page_title = EXCLUDED.page_title,
                    markdown = EXCLUDED.markdown,
                    html = EXCLUDED.html,
                    screenshot_storage_key = EXCLUDED.screenshot_storage_key,
                    scraped_at = EXCLUDED.scraped_at,
                    expires_at = EXCLUDED.expires_at,
                    evicted_at = EXCLUDED.evicted_at
                WHERE vibecheck_scrapes.evicted_at IS NULL
                   OR vibecheck_scrapes.evicted_at < $11
                RETURNING TRUE
                """,
                norm,
                tier,
                url,
                final_url,
                host,
                metadata.title,
                scrape.markdown,
                scrape.html,
                now,
                expires,
                put_started_at - timedelta(seconds=1),
            )
        if not wrote_row:
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

    async def evict(self, url: str, *, tier: str | None = None) -> None:
        now = datetime.now(UTC)
        norm = normalize_url(url)
        host = urlparse(norm).netloc
        expired = now - timedelta(hours=1)
        async with self._pool.acquire() as conn:
            tombstones = ("scrape", "interact") if tier is None else (tier,)
            if tier is None:
                await conn.execute(
                    "DELETE FROM vibecheck_scrapes WHERE normalized_url = $1", norm
                )
            else:
                await conn.execute(
                    "DELETE FROM vibecheck_scrapes "
                    "WHERE normalized_url = $1 AND tier = $2",
                    norm,
                    tier,
                )
            for tombstone_tier in tombstones:
                await conn.execute(
                    """
                    INSERT INTO vibecheck_scrapes (
                        normalized_url, tier, url, final_url, host, page_kind,
                        page_title, markdown, html, screenshot_storage_key,
                        scraped_at, expires_at, evicted_at
                    )
                    VALUES (
                        $1, $2, $3, NULL, $4, 'other',
                        NULL, NULL, NULL, NULL,
                        $5, $6, $7
                    )
                    ON CONFLICT (normalized_url, tier) DO UPDATE
                    SET final_url = EXCLUDED.final_url,
                        host = EXCLUDED.host,
                        page_kind = EXCLUDED.page_kind,
                        page_title = EXCLUDED.page_title,
                        markdown = EXCLUDED.markdown,
                        html = EXCLUDED.html,
                        screenshot_storage_key = EXCLUDED.screenshot_storage_key,
                        scraped_at = EXCLUDED.scraped_at,
                        expires_at = EXCLUDED.expires_at,
                        evicted_at = EXCLUDED.evicted_at
                    """,
                    norm,
                    tombstone_tier,
                    norm,
                    host,
                    now,
                    expired,
                    now,
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

    Each `scrape(url, ...)` and `interact(url, ...)` call appends to `calls`
    (preserved for back-compat with `len(calls) == N` style assertions in
    existing tests) and to `scrape_calls` / `interact_calls` as
    `(url, kwargs)` tuples for new contract-pinning assertions.

    Per-URL outcome is `ScrapeOutcome`: a fixed `ScrapeResult`, a raised
    `BaseException` (e.g. `FirecrawlBlocked` for refusal scenarios), or a
    no-arg callable factory for state-dependent tests.

    `metadata.source_url` defaults to the requested URL so the post-scrape
    SSRF revalidator passes; SSRF tests override this to a private IP.
    """

    def __init__(
        self,
        *,
        results_by_url: dict[str, ScrapeOutcome] | None = None,
        interact_results_by_url: dict[str, ScrapeOutcome] | None = None,
        default_markdown: str = "Sample post content with substantive prose.",
    ) -> None:
        self.calls: list[str] = []
        self.scrape_calls: list[tuple[str, dict[str, Any]]] = []
        self.interact_calls: list[tuple[str, dict[str, Any]]] = []
        self._results_by_url: dict[str, ScrapeOutcome] = dict(
            results_by_url or {}
        )
        self._interact_results_by_url: dict[str, ScrapeOutcome] = dict(
            interact_results_by_url or {}
        )
        self._default_markdown = default_markdown

    def _resolve(
        self, url: str, results: dict[str, ScrapeOutcome]
    ) -> ScrapeResult:
        if url not in results:
            return ScrapeResult(
                markdown=self._default_markdown,
                html=f"<article>{self._default_markdown}</article>",
                metadata=ScrapeMetadata(title="Test Page", source_url=url),
            )
        outcome = results[url]
        if isinstance(outcome, BaseException):
            raise outcome
        if callable(outcome):
            return outcome()
        return outcome

    async def scrape(
        self,
        url: str,
        formats: list[str],
        *,
        only_main_content: bool = False,
    ) -> ScrapeResult:
        self.calls.append(url)
        self.scrape_calls.append(
            (url, {"formats": formats, "only_main_content": only_main_content})
        )
        return self._resolve(url, self._results_by_url)

    async def interact(
        self,
        url: str,
        actions: list[dict[str, Any]],
        *,
        formats: list[str] | None = None,
        only_main_content: bool = False,
    ) -> ScrapeResult:
        self.calls.append(url)
        self.interact_calls.append(
            (
                url,
                {
                    "actions": actions,
                    "formats": formats,
                    "only_main_content": only_main_content,
                },
            )
        )
        return self._resolve(url, self._interact_results_by_url)


# ---------------------------------------------------------------------------
# ASGI client wiring.
#
# `install_oidc_mock` and `oidc_headers` are consumed from the root
# `tests/conftest.py` (TASK-1474.23.03.14 consolidation). Pytest discovers
# fixtures up the conftest tree automatically, so no re-export is needed.
# ---------------------------------------------------------------------------


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
    try:
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as c:
            yield c
    finally:
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
