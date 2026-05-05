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
from uuid import UUID

import asyncpg
import pytest
from testcontainers.postgres import PostgresContainer

from src.jobs.recent_query import (
    _has_secret_query_param,
    _is_blocked_url,
    _passes_partial_threshold,
    list_recent,
)
from tests.conftest import VIBECHECK_JOBS_DDL

_REAL_GETADDRINFO = socket.getaddrinfo


_MINIMAL_DDL = (
    """
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
"""
    + VIBECHECK_JOBS_DDL
    + """
ALTER TABLE vibecheck_jobs
    ADD COLUMN IF NOT EXISTS source_type TEXT NOT NULL DEFAULT 'url';
CREATE INDEX IF NOT EXISTS vibecheck_jobs_source_type_idx
    ON vibecheck_jobs (source_type);
ALTER TABLE vibecheck_jobs
    DROP CONSTRAINT IF EXISTS vibecheck_jobs_source_type_check;
ALTER TABLE vibecheck_jobs
    ADD CONSTRAINT vibecheck_jobs_source_type_check
    CHECK (source_type IN ('url', 'pdf', 'browser_html'));
CREATE TABLE vibecheck_scrapes (
    scrape_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    normalized_url TEXT NOT NULL,
    tier TEXT NOT NULL DEFAULT 'scrape'
        CHECK (tier IN ('scrape', 'interact', 'browser_html')),
    url TEXT NOT NULL,
    host TEXT NOT NULL,
    page_kind TEXT NOT NULL DEFAULT 'other',
    page_title TEXT,
    markdown TEXT,
    html TEXT,
    screenshot_storage_key TEXT,
    scraped_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL DEFAULT (now() + INTERVAL '72 hours'),
    UNIQUE (normalized_url, tier)
);
"""
)


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


class TestBlockedUrlFilter:
    """Privacy filter exercised via the full SSRF guard composition.

    These tests run with the autouse `_stub_dns` from tests/conftest.py
    that returns 8.8.8.8 for any hostname, so non-blocked hosts like
    `example.com` resolve as "public" and pass the SSRF guard.
    """

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

    # ---- TASK-1485.06 P1.2 — bypasses Codex empirically verified
    # against the original ipaddress-only `_is_blocked_host`. ----

    def test_trailing_dot_localhost_blocked(self) -> None:
        # IDNA normalization in validate_public_http_url strips the dot.
        assert _is_blocked_url("http://localhost./") is True

    def test_internal_suffix_blocked(self) -> None:
        # `.internal` blocklist via SSRF guard (e.g. AWS / GCE metadata).
        assert _is_blocked_url("https://service.internal/path") is True

    def test_local_suffix_blocked(self) -> None:
        # `.local` blocklist (mDNS / Bonjour).
        assert _is_blocked_url("https://printer.local/jobs") is True

    def test_metadata_host_blocked(self) -> None:
        # GCE metadata host explicitly in SSRF blocklist.
        assert _is_blocked_url("http://metadata.google.internal/") is True

    def test_ipv4_mapped_ipv6_loopback_blocked(self) -> None:
        # `::ffff:127.0.0.1` is loopback per ipaddress.is_loopback.
        assert _is_blocked_url("http://[::ffff:127.0.0.1]/") is True

    def test_link_local_ipv6_blocked(self) -> None:
        # fe80::/10 is link-local — rejected by SSRF guard.
        assert _is_blocked_url("http://[fe80::1]/") is True

    def test_unspecified_address_blocked(self) -> None:
        assert _is_blocked_url("http://0.0.0.0/") is True

    def test_multicast_ipv4_blocked(self) -> None:
        assert _is_blocked_url("http://224.0.0.1/") is True

    def test_reserved_ipv4_blocked(self) -> None:
        assert _is_blocked_url("http://240.0.0.1/") is True

    def test_malformed_port_does_not_raise(self) -> None:
        # Without the `.port` try/except (TASK-1485.06 P1.2), a DB row
        # with a malformed port would 500 the gallery. We block instead.
        assert _is_blocked_url("https://example.com:abc/x") is True

    def test_non_http_scheme_blocked(self) -> None:
        assert _is_blocked_url("ftp://example.com/file") is True
        assert _is_blocked_url("file:///etc/passwd") is True
        assert _is_blocked_url("javascript:alert(1)") is True

    @pytest.mark.parametrize(
        "param",
        ["password", "auth", "sig", "signature", "API_KEY"],
    )
    def test_additional_secret_query_params_blocked(self, param: str) -> None:
        assert _is_blocked_url(f"https://example.com/x?{param}=v") is True


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


@pytest.fixture
def _restore_real_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    """DB-backed tests need real DNS for testcontainers Postgres.

    Pure-function privacy tests deliberately keep the suite-wide stub
    (`tests/conftest.py::_stub_dns` returns 8.8.8.8 for any host) so
    `example.com` etc. resolve as "public" and pass the SSRF guard
    without requiring CI internet access.
    """
    monkeypatch.setattr(socket, "getaddrinfo", _REAL_GETADDRINFO)


@pytest.fixture(scope="module")
def _postgres_container() -> Any:
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg


@pytest.fixture
async def db_pool(
    _postgres_container: PostgresContainer,
    _restore_real_dns: None,
) -> AsyncIterator[Any]:
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
    source_type: str = "url",
    sections: dict[str, dict[str, str]] | None = None,
    preview: str | None = "preview blurb",
    finished_at: datetime | None = None,
    expired_at: datetime | None = None,
) -> UUID:
    sections = sections if sections is not None else _full_sections()
    if finished_at is None and status in ("done", "partial", "failed"):
        finished_at = datetime.now(UTC)
    async with pool.acquire() as conn:
        return await conn.fetchval(
            """
            INSERT INTO vibecheck_jobs
                (url, normalized_url, host, status, sections, finished_at,
                 preview_description, source_type, expired_at)
            VALUES ($1, $1, 'example.com', $2, $3::jsonb, $4, $5, $6, $7)
            RETURNING job_id
            """,
            url,
            status,
            json.dumps(sections),
            finished_at,
            preview,
            source_type,
            expired_at,
        )


async def _seed_scrape(
    pool: Any,
    *,
    url: str,
    tier: str = "scrape",
    page_title: str | None = "Example Title",
    storage_key: str | None = "abc/screenshot.png",
    expires_in: timedelta = timedelta(hours=72),
) -> None:
    expires_at = datetime.now(UTC) + expires_in
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO vibecheck_scrapes
                (normalized_url, tier, url, host, page_title,
                 screenshot_storage_key, expires_at)
            VALUES ($1, $2, $1, 'example.com', $3, $4, $5)
            """,
            url,
            tier,
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

    async def test_excludes_pdf_source_type_rows(self, db_pool: Any) -> None:
        await _seed_job(
            db_pool,
            url="https://example.com/from-pdf",
            source_type="pdf",
        )
        await _seed_scrape(db_pool, url="https://example.com/from-pdf")
        result = await list_recent(db_pool, limit=5, signer=_StubSigner())
        assert result == []

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

    async def test_excludes_browser_html_source_type(self, db_pool: Any) -> None:
        url = "https://example.com/private-browser-html"
        await _seed_job(db_pool, url=url, source_type="browser_html")
        await _seed_scrape(db_pool, url=url, tier="browser_html")
        result = await list_recent(db_pool, limit=5, signer=_StubSigner())
        assert result == []

    async def test_excludes_expired_jobs(self, db_pool: Any) -> None:
        """TASK-1541.04: expired (soft-deleted) jobs must not appear in
        the gallery. The purge sets `expired_at` but does not null
        `preview_description`, so without the `expired_at IS NULL`
        guard the row would leak into list_recent and render a broken
        analysis card with empty sidebar_payload.
        """
        url = "https://example.com/expired-job"
        await _seed_job(db_pool, url=url, expired_at=datetime.now(UTC))
        await _seed_scrape(db_pool, url=url)
        result = await list_recent(db_pool, limit=5, signer=_StubSigner())
        assert result == []


# TASK-1488.16 — gallery join must prefer tier='interact' when both tier
# rows exist for the same URL. Without the preference, the JOIN is
# non-deterministic and a Tier 1 INTERSTITIAL row (e.g. CF challenge)
# can shadow a Tier 2 success.


class TestListRecentTierPreference:
    async def test_picks_interact_tier_when_both_tiers_exist(
        self, db_pool: Any
    ) -> None:
        """Both tier='scrape' and tier='interact' rows exist for the same
        URL — the gallery returns the interact-tier asset (page_title +
        screenshot_storage_key), not the cached interstitial.
        """
        url = "https://example.com/cf-then-interact-success"
        await _seed_job(db_pool, url=url)
        await _seed_scrape(
            db_pool,
            url=url,
            tier="scrape",
            page_title="Just a moment...",
            storage_key="cf-interstitial.png",
        )
        await _seed_scrape(
            db_pool,
            url=url,
            tier="interact",
            page_title="Real Article Title",
            storage_key="real-content.png",
        )
        result = await list_recent(db_pool, limit=5, signer=_StubSigner())
        assert len(result) == 1
        assert result[0].page_title == "Real Article Title"
        assert "real-content.png" in result[0].screenshot_url

    async def test_falls_back_to_scrape_tier_when_interact_missing(
        self, db_pool: Any
    ) -> None:
        """Regression: a URL with only a tier='scrape' row (no interact
        row) is still surfaced — the tier preference must not require
        the interact row.
        """
        url = "https://example.com/scrape-only"
        await _seed_job(db_pool, url=url)
        await _seed_scrape(
            db_pool,
            url=url,
            tier="scrape",
            page_title="Plain Article",
            storage_key="plain.png",
        )
        result = await list_recent(db_pool, limit=5, signer=_StubSigner())
        assert len(result) == 1
        assert result[0].page_title == "Plain Article"

    async def test_falls_back_to_scrape_when_interact_expired(
        self, db_pool: Any
    ) -> None:
        """Boundary: a fresh tier='scrape' row beats an expired
        tier='interact' row — the TTL filter applies before the tier
        preference.
        """
        url = "https://example.com/interact-expired"
        await _seed_job(db_pool, url=url)
        await _seed_scrape(
            db_pool,
            url=url,
            tier="scrape",
            page_title="Fresh Scrape",
            storage_key="fresh.png",
        )
        await _seed_scrape(
            db_pool,
            url=url,
            tier="interact",
            page_title="Stale Interact",
            storage_key="stale.png",
            expires_in=timedelta(hours=-1),
        )
        result = await list_recent(db_pool, limit=5, signer=_StubSigner())
        assert len(result) == 1
        assert result[0].page_title == "Fresh Scrape"


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

    async def test_many_blocked_rows_do_not_displace_eligible(
        self, db_pool: Any
    ) -> None:
        """TASK-1485.06 P2.1: large privacy-rejection batches must not
        prevent the gallery from filling when eligible rows exist.

        Uses example.com paths only so both real and stubbed DNS resolve
        the host as public — privacy filtering must come exclusively
        from the per-row predicate (secret query string here).
        """
        # 6 newer rows blocked by ?token=, 3 older eligible rows.
        for i in range(6):
            bad = f"https://example.com/blocked-{i}?token=x"
            await _seed_job(
                db_pool,
                url=bad,
                finished_at=datetime.now(UTC) - timedelta(seconds=i),
            )
            await _seed_scrape(db_pool, url=bad)
        for i in range(3):
            good = f"https://example.com/good-{i}"
            await _seed_job(
                db_pool,
                url=good,
                finished_at=datetime.now(UTC) - timedelta(seconds=10 + i),
            )
            await _seed_scrape(db_pool, url=good)

        result = await list_recent(db_pool, limit=5, signer=_StubSigner())
        assert len(result) == 3
        for card in result:
            assert "/good-" in card.source_url
            assert "?token=" not in card.source_url


class TestListRecentDedupAfterFilter:
    """TASK-1485.06 P1.1: a newer privacy-rejected duplicate must NOT
    hide an older qualifying duplicate of the same normalized_url."""

    async def test_newer_secret_query_does_not_hide_older_clean(
        self, db_pool: Any
    ) -> None:
        # Both jobs share the same normalized_url
        # ("https://example.com/dedup-secret") because the scrape cache's
        # normalize_url drops `?utm_*` but keeps `?token=`. Two distinct
        # URLs that normalize to the same key still go to the same scrape
        # row. We seed only one scrape row matching the shared key.
        url = "https://example.com/dedup-secret"
        # Older: clean URL, qualifying.
        old = await _seed_job(
            db_pool,
            url=url,
            finished_at=datetime.now(UTC) - timedelta(hours=1),
        )
        await _seed_scrape(db_pool, url=url)
        # Newer: same normalized URL but source_url carries a secret param.
        # Manually upsert with same normalized_url + dirty source_url.
        async with db_pool.acquire() as conn:
            new = await conn.fetchval(
                """
                INSERT INTO vibecheck_jobs
                    (url, normalized_url, host, status, sections,
                     finished_at, preview_description)
                VALUES ($1, $2, 'example.com', 'done', $3::jsonb, $4, $5)
                RETURNING job_id
                """,
                f"{url}?token=secret",
                url,
                json.dumps(_full_sections()),
                datetime.now(UTC),
                "newer secret-bearing job",
            )

        result = await list_recent(db_pool, limit=5, signer=_StubSigner())
        # The newer job is privacy-rejected (its source_url has ?token=).
        # Without dedup-after-filter, the gallery would drop this URL
        # entirely (newer hides older). With the fix, the older clean
        # job represents this URL.
        assert len(result) == 1
        assert result[0].job_id == old
        assert result[0].job_id != new
        assert "?token=" not in result[0].source_url

    async def test_newer_sub_threshold_partial_does_not_hide_older_done(
        self, db_pool: Any
    ) -> None:
        # SQL filters out the newer sub-threshold partial entirely (the
        # 90% rule lives in the WHERE clause), so dedup never sees it.
        # The older done job survives and represents this URL.
        url = "https://example.com/dedup-partial"
        old = await _seed_job(
            db_pool,
            url=url,
            status="done",
            finished_at=datetime.now(UTC) - timedelta(hours=1),
        )
        await _seed_scrape(db_pool, url=url)
        # Newer partial that fails the 90% rule.
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO vibecheck_jobs
                    (url, normalized_url, host, status, sections,
                     finished_at, preview_description)
                VALUES ($1, $1, 'example.com', 'partial', $2::jsonb, $3, $4)
                """,
                url,
                json.dumps(_partial_sections(done=5, total=10)),
                datetime.now(UTC),
                "low-completion partial",
            )

        result = await list_recent(db_pool, limit=5, signer=_StubSigner())
        assert len(result) == 1
        assert result[0].job_id == old
