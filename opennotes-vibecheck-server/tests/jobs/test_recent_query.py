"""Behavior contracts for the recent-analyses query (TASK-1485.03).

Privacy filters are pure-function tested directly; SQL behavior (DISTINCT
ON dedup, status filter, expired-scrape exclusion, 90% rule) goes through
the testcontainers Postgres `db_pool` fixture so partial-with-mostly-done
sections actually exercise the JSONB key counter.
"""
from __future__ import annotations

import json
import socket
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import asyncpg
import pytest
from testcontainers.postgres import PostgresContainer

from src.jobs.recent_query import (
    ScreenshotSigner,
    _has_secret_query_param,
    _is_blocked_host,
    _is_blocked_url,
    _passes_partial_threshold,
    list_recent,
)

_REAL_GETADDRINFO = socket.getaddrinfo


_MINIMAL_DDL = """
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE vibecheck_jobs (
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
    preview_description TEXT
);

CREATE TABLE vibecheck_scrapes (
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
"""


class _StubSigner:
    """Returns a deterministic signed URL for any non-empty key."""

    def sign_screenshot_key(self, storage_key: str | None) -> str | None:
        if not storage_key:
            return None
        return f"https://signed.example/{storage_key}?token=abc"


class _BrokenSigner:
    """Always returns None — exercises the drop-rows-with-no-signed-url path."""

    def sign_screenshot_key(self, storage_key: str | None) -> str | None:
        return None


# ---------------------------------------------------------------------------
# Pure-function privacy filter tests (no DB needed).
# ---------------------------------------------------------------------------


class TestSecretQueryParamFilter:
    @pytest.mark.parametrize(
        "param",
        [
            "token",
            "api_key",
            "apikey",
            "secret",
            "key",
            "access_token",
            "password",
            "auth",
            "sig",
            "signature",
        ],
    )
    def test_blocks_known_secret_keys(self, param: str) -> None:
        assert _has_secret_query_param(f"{param}=abc123") is True

    def test_case_insensitive(self) -> None:
        assert _has_secret_query_param("Token=abc") is True
        assert _has_secret_query_param("API_KEY=abc") is True

    def test_does_not_block_innocuous_query(self) -> None:
        assert _has_secret_query_param("page=2&sort=desc") is False

    def test_empty_query_passes(self) -> None:
        assert _has_secret_query_param("") is False


class TestBlockedHostFilter:
    @pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "::1", "10.0.0.1", "192.168.1.1", "172.16.5.5"])
    def test_blocks_loopback_and_private_ranges(self, host: str) -> None:
        assert _is_blocked_host(host) is True

    @pytest.mark.parametrize("host", ["example.com", "blog.example.com", "8.8.8.8", "1.1.1.1"])
    def test_allows_public_hosts(self, host: str) -> None:
        assert _is_blocked_host(host) is False


class TestBlockedUrlFilter:
    def test_localhost_blocked(self) -> None:
        assert _is_blocked_url("https://localhost/page") is True

    def test_127_blocked(self) -> None:
        assert _is_blocked_url("http://127.0.0.1/page") is True

    def test_private_ip_blocked(self) -> None:
        assert _is_blocked_url("http://192.168.1.1/page") is True

    def test_explicit_non_safe_port_blocked(self) -> None:
        assert _is_blocked_url("https://example.com:8080/page") is True

    def test_port_443_allowed(self) -> None:
        assert _is_blocked_url("https://example.com:443/page") is False

    def test_port_80_allowed(self) -> None:
        assert _is_blocked_url("http://example.com:80/page") is False

    def test_secret_query_blocked(self) -> None:
        assert _is_blocked_url("https://example.com/page?token=abc") is True

    def test_innocuous_url_allowed(self) -> None:
        assert _is_blocked_url("https://example.com/page?utm_source=foo") is False

    def test_userinfo_blocked(self) -> None:
        assert _is_blocked_url("https://user:pass@example.com/page") is True

    def test_invalid_url_blocked(self) -> None:
        assert _is_blocked_url("not a url") is True


class TestPartialThreshold:
    def test_done_status_passes_unconditionally(self) -> None:
        assert _passes_partial_threshold({}, "done") is True

    def test_failed_status_excluded(self) -> None:
        assert _passes_partial_threshold({}, "failed") is False

    def test_partial_with_no_sections_excluded(self) -> None:
        assert _passes_partial_threshold({}, "partial") is False

    def test_partial_below_90_excluded(self) -> None:
        sections = {f"slug{i}": {"state": "done"} for i in range(8)}
        sections["slug9"] = {"state": "failed"}
        sections["slug10"] = {"state": "failed"}
        # 8/10 = 80% — excluded.
        assert _passes_partial_threshold(sections, "partial") is False

    def test_partial_at_90_included(self) -> None:
        sections = {f"slug{i}": {"state": "done"} for i in range(9)}
        sections["slug9"] = {"state": "failed"}
        # 9/10 = 90% — included.
        assert _passes_partial_threshold(sections, "partial") is True

    def test_partial_seven_of_seven_included(self) -> None:
        sections = {f"slug{i}": {"state": "done"} for i in range(7)}
        # 100% — included.
        assert _passes_partial_threshold(sections, "partial") is True

    def test_partial_six_of_seven_excluded(self) -> None:
        sections = {f"slug{i}": {"state": "done"} for i in range(6)}
        sections["slug6"] = {"state": "failed"}
        # 6/7 ≈ 85.7% — excluded.
        assert _passes_partial_threshold(sections, "partial") is False

    def test_accepts_jsonb_string_input(self) -> None:
        sections = {f"slug{i}": {"state": "done"} for i in range(9)}
        sections["slug9"] = {"state": "failed"}
        assert _passes_partial_threshold(json.dumps(sections), "partial") is True


# ---------------------------------------------------------------------------
# DB-backed integration tests via testcontainers.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _restore_real_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _REAL_GETADDRINFO)


@pytest.fixture(scope="module")
def _postgres_container() -> Any:
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg


@pytest.fixture
async def db_pool(_postgres_container: PostgresContainer) -> AsyncIterator[Any]:
    raw = _postgres_container.get_connection_url()
    dsn = raw.replace("postgresql+psycopg2://", "postgresql://")
    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=8)
    assert pool is not None
    async with pool.acquire() as conn:
        await conn.execute(
            "DROP TABLE IF EXISTS vibecheck_scrapes CASCADE; "
            "DROP TABLE IF EXISTS vibecheck_jobs CASCADE;"
        )
        await conn.execute(_MINIMAL_DDL)
    try:
        yield pool
    finally:
        await pool.close()


def _full_sections() -> dict[str, dict[str, str]]:
    return {f"slug{i}": {"state": "done"} for i in range(7)}


def _partial_sections(done: int, total: int) -> dict[str, dict[str, str]]:
    sections: dict[str, dict[str, str]] = {}
    for i in range(done):
        sections[f"slug{i}"] = {"state": "done"}
    for i in range(done, total):
        sections[f"slug{i}"] = {"state": "failed"}
    return sections


async def _seed_job(
    pool: Any,
    *,
    url: str,
    status: str = "done",
    sections: dict[str, dict[str, str]] | None = None,
    preview: str | None = "preview blurb",
    finished_at: datetime | None = None,
) -> UUID:
    sections = sections if sections is not None else _full_sections()
    finished_at = finished_at or datetime.now(UTC)
    async with pool.acquire() as conn:
        return await conn.fetchval(
            """
            INSERT INTO vibecheck_jobs
                (url, normalized_url, host, status, sections, finished_at,
                 preview_description)
            VALUES ($1, $1, 'example.com', $2, $3::jsonb, $4, $5)
            RETURNING job_id
            """,
            url,
            status,
            json.dumps(sections),
            finished_at,
            preview,
        )


async def _seed_scrape(
    pool: Any,
    *,
    url: str,
    page_title: str | None = "Example Title",
    storage_key: str | None = "abc/screenshot.png",
    expires_in: timedelta = timedelta(hours=72),
) -> None:
    expires_at = datetime.now(UTC) + expires_in
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO vibecheck_scrapes
                (normalized_url, url, host, page_title, screenshot_storage_key,
                 expires_at)
            VALUES ($1, $1, 'example.com', $2, $3, $4)
            """,
            url,
            page_title,
            storage_key,
            expires_at,
        )


class TestListRecentEmpty:
    async def test_empty_db_returns_empty_list(self, db_pool: Any) -> None:
        result = await list_recent(db_pool, limit=5, signer=_StubSigner())
        assert result == []

    async def test_zero_limit_short_circuits(self, db_pool: Any) -> None:
        url = "https://example.com/has-data"
        await _seed_job(db_pool, url=url)
        await _seed_scrape(db_pool, url=url)
        result = await list_recent(db_pool, limit=0, signer=_StubSigner())
        assert result == []


class TestListRecentDoneJobs:
    async def test_done_job_with_scrape_appears(self, db_pool: Any) -> None:
        url = "https://example.com/done"
        job_id = await _seed_job(db_pool, url=url)
        await _seed_scrape(db_pool, url=url)
        result = await list_recent(db_pool, limit=5, signer=_StubSigner())
        assert len(result) == 1
        assert result[0].job_id == job_id
        assert result[0].source_url == url
        assert result[0].screenshot_url.startswith("https://signed.example/")

    async def test_truncates_to_limit(self, db_pool: Any) -> None:
        for i in range(7):
            url = f"https://example.com/page-{i}"
            await _seed_job(db_pool, url=url)
            await _seed_scrape(db_pool, url=url)
        result = await list_recent(db_pool, limit=5, signer=_StubSigner())
        assert len(result) == 5

    async def test_orders_by_finished_at_desc(self, db_pool: Any) -> None:
        old = await _seed_job(
            db_pool,
            url="https://example.com/old",
            finished_at=datetime.now(UTC) - timedelta(hours=2),
        )
        await _seed_scrape(db_pool, url="https://example.com/old")
        new = await _seed_job(
            db_pool,
            url="https://example.com/new",
            finished_at=datetime.now(UTC),
        )
        await _seed_scrape(db_pool, url="https://example.com/new")
        result = await list_recent(db_pool, limit=5, signer=_StubSigner())
        assert [r.job_id for r in result] == [new, old]


class TestListRecentDedup:
    async def test_dedups_by_normalized_url_keeping_newest(self, db_pool: Any) -> None:
        url = "https://example.com/dup"
        old = await _seed_job(
            db_pool,
            url=url,
            finished_at=datetime.now(UTC) - timedelta(hours=1),
        )
        await _seed_scrape(db_pool, url=url)
        new = await _seed_job(
            db_pool,
            url=url,
            finished_at=datetime.now(UTC),
        )
        result = await list_recent(db_pool, limit=5, signer=_StubSigner())
        assert len(result) == 1
        assert result[0].job_id == new
        assert result[0].job_id != old


class TestListRecentExclusionRules:
    async def test_excludes_failed_status(self, db_pool: Any) -> None:
        url = "https://example.com/failed"
        await _seed_job(db_pool, url=url, status="failed", preview=None)
        await _seed_scrape(db_pool, url=url)
        result = await list_recent(db_pool, limit=5, signer=_StubSigner())
        assert result == []

    async def test_excludes_pending_status(self, db_pool: Any) -> None:
        url = "https://example.com/pending"
        await _seed_job(db_pool, url=url, status="pending", preview=None)
        await _seed_scrape(db_pool, url=url)
        result = await list_recent(db_pool, limit=5, signer=_StubSigner())
        assert result == []

    async def test_partial_below_90_excluded(self, db_pool: Any) -> None:
        url = "https://example.com/partial-low"
        await _seed_job(
            db_pool,
            url=url,
            status="partial",
            sections=_partial_sections(done=6, total=10),
        )
        await _seed_scrape(db_pool, url=url)
        result = await list_recent(db_pool, limit=5, signer=_StubSigner())
        assert result == []

    async def test_partial_at_90_included(self, db_pool: Any) -> None:
        url = "https://example.com/partial-at-90"
        await _seed_job(
            db_pool,
            url=url,
            status="partial",
            sections=_partial_sections(done=9, total=10),
        )
        await _seed_scrape(db_pool, url=url)
        result = await list_recent(db_pool, limit=5, signer=_StubSigner())
        assert len(result) == 1

    async def test_excludes_when_scrape_missing(self, db_pool: Any) -> None:
        url = "https://example.com/no-scrape"
        await _seed_job(db_pool, url=url)
        # No scrape row inserted.
        result = await list_recent(db_pool, limit=5, signer=_StubSigner())
        assert result == []

    async def test_excludes_when_scrape_expired(self, db_pool: Any) -> None:
        url = "https://example.com/expired-scrape"
        await _seed_job(db_pool, url=url)
        await _seed_scrape(db_pool, url=url, expires_in=timedelta(hours=-1))
        result = await list_recent(db_pool, limit=5, signer=_StubSigner())
        assert result == []

    async def test_excludes_when_screenshot_storage_key_null(
        self, db_pool: Any
    ) -> None:
        url = "https://example.com/no-screenshot"
        await _seed_job(db_pool, url=url)
        await _seed_scrape(db_pool, url=url, storage_key=None)
        result = await list_recent(db_pool, limit=5, signer=_StubSigner())
        assert result == []

    async def test_excludes_when_signer_returns_none(self, db_pool: Any) -> None:
        url = "https://example.com/sign-fail"
        await _seed_job(db_pool, url=url)
        await _seed_scrape(db_pool, url=url)
        result = await list_recent(db_pool, limit=5, signer=_BrokenSigner())
        assert result == []

    async def test_excludes_when_preview_description_null(
        self, db_pool: Any
    ) -> None:
        url = "https://example.com/no-preview"
        await _seed_job(db_pool, url=url, preview=None)
        await _seed_scrape(db_pool, url=url)
        result = await list_recent(db_pool, limit=5, signer=_StubSigner())
        assert result == []


class TestListRecentPrivacyFilters:
    async def test_excludes_localhost(self, db_pool: Any) -> None:
        url = "http://localhost/page"
        await _seed_job(db_pool, url=url)
        await _seed_scrape(db_pool, url=url)
        result = await list_recent(db_pool, limit=5, signer=_StubSigner())
        assert result == []

    async def test_excludes_secret_query_string(self, db_pool: Any) -> None:
        url = "https://example.com/page?token=abc"
        await _seed_job(db_pool, url=url)
        await _seed_scrape(db_pool, url=url)
        result = await list_recent(db_pool, limit=5, signer=_StubSigner())
        assert result == []

    async def test_excludes_explicit_port(self, db_pool: Any) -> None:
        url = "https://example.com:9000/page"
        await _seed_job(db_pool, url=url)
        await _seed_scrape(db_pool, url=url)
        result = await list_recent(db_pool, limit=5, signer=_StubSigner())
        assert result == []

    async def test_blocked_url_does_not_displace_eligible(
        self, db_pool: Any
    ) -> None:
        """Privacy reject must be applied BEFORE the limit cutoff so eligible
        rows are not silently pushed out by a blocked one."""
        bad = "https://example.com/page?token=secret"
        await _seed_job(
            db_pool,
            url=bad,
            finished_at=datetime.now(UTC),
        )
        await _seed_scrape(db_pool, url=bad)
        good = "https://example.com/clean"
        await _seed_job(
            db_pool,
            url=good,
            finished_at=datetime.now(UTC) - timedelta(seconds=1),
        )
        await _seed_scrape(db_pool, url=good)

        result = await list_recent(db_pool, limit=1, signer=_StubSigner())
        assert len(result) == 1
        assert result[0].source_url == good
