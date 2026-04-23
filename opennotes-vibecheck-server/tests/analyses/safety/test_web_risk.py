"""Tests for src/analyses/safety/web_risk.py (TASK-1474.07).

Uses httpx.MockTransport for HTTP and testcontainers Postgres for the
vibecheck_web_risk_lookups cache table.
"""
from __future__ import annotations

import asyncio
import json
import socket
from collections.abc import AsyncIterator, Iterator
from typing import Any
from unittest.mock import patch

import asyncpg
import httpx
import pytest
from testcontainers.postgres import PostgresContainer

from src.analyses.safety._schemas import WebRiskFinding
from src.analyses.safety.web_risk import WebRiskTransientError, check_urls

# Capture real resolver before the suite-wide autouse _stub_dns patches it.
_REAL_GETADDRINFO = socket.getaddrinfo

_MINIMAL_DDL = """
CREATE TABLE IF NOT EXISTS vibecheck_web_risk_lookups (
    url TEXT PRIMARY KEY,
    finding_payload JSONB NOT NULL,
    checked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS vibecheck_web_risk_lookups_expires_at_idx
    ON vibecheck_web_risk_lookups (expires_at);
"""


@pytest.fixture(autouse=True)
def _restore_real_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _REAL_GETADDRINFO)


@pytest.fixture(scope="module")
def _postgres_container() -> Iterator[PostgresContainer]:
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg


@pytest.fixture
async def db_pool(_postgres_container: PostgresContainer) -> AsyncIterator[asyncpg.Pool]:
    raw = _postgres_container.get_connection_url()
    dsn = raw.replace("postgresql+psycopg2://", "postgresql://")
    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=8)
    assert pool is not None
    async with pool.acquire() as conn:
        await conn.execute("DROP TABLE IF EXISTS vibecheck_web_risk_lookups CASCADE;")
        await conn.execute(_MINIMAL_DDL)
    try:
        yield pool
    finally:
        await pool.close()


def _make_mock_transport(
    responses: dict[str, httpx.Response] | None = None,
    default_response: httpx.Response | None = None,
) -> httpx.MockTransport:
    """Build an httpx.MockTransport that dispatches by URL."""
    responses = responses or {}
    _default = default_response or httpx.Response(200, json={})

    def handler(request: httpx.Request) -> httpx.Response:
        uri = request.url.params.get("uri", "")
        return responses.get(uri, _default)

    return httpx.MockTransport(handler)


async def _seed_cache(
    pool: asyncpg.Pool,
    url: str,
    threat_types: list[str],
    expires_in_seconds: int = 3600,
) -> None:
    finding = WebRiskFinding(url=url, threat_types=threat_types)  # type: ignore[arg-type]
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO vibecheck_web_risk_lookups (url, finding_payload, expires_at)
            VALUES ($1, $2::jsonb, now() + ($3 * interval '1 second'))
            ON CONFLICT (url) DO UPDATE SET
                finding_payload = EXCLUDED.finding_payload,
                expires_at = EXCLUDED.expires_at
            """,
            url,
            json.dumps(finding.model_dump()),
            expires_in_seconds,
        )


class TestCacheHitSkipsApi:
    async def test_cache_hit_skips_api(self, db_pool: asyncpg.Pool) -> None:
        url = "https://example.com/cached"
        await _seed_cache(db_pool, url, [])

        request_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal request_count
            request_count += 1
            return httpx.Response(200, json={})

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            with patch("src.analyses.safety.web_risk.get_access_token", return_value="tok"):
                result = await check_urls([url], pool=db_pool, httpx_client=client)

        assert request_count == 0
        assert url in result
        assert result[url].threat_types == []


class TestCacheMissCallsApiAndUpsertsNegativeCache:
    async def test_cache_miss_calls_api_and_upserts_negative_cache(
        self, db_pool: asyncpg.Pool
    ) -> None:
        url = "https://example.com/clean"
        transport = _make_mock_transport(
            responses={url: httpx.Response(200, json={})},
        )
        async with httpx.AsyncClient(transport=transport) as client:
            with patch("src.analyses.safety.web_risk.get_access_token", return_value="tok"):
                result = await check_urls([url], pool=db_pool, httpx_client=client)

        assert url in result
        assert result[url].threat_types == []

        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT finding_payload FROM vibecheck_web_risk_lookups WHERE url = $1",
                url,
            )
        assert row is not None
        payload = row["finding_payload"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        assert payload["threat_types"] == []


class TestCacheMissParsesSingleThreatType:
    async def test_cache_miss_parses_single_threat_type(
        self, db_pool: asyncpg.Pool
    ) -> None:
        url = "https://malware.example.com/"
        api_resp = {"threat": {"threatTypes": ["MALWARE"], "expireTime": "2099-01-01T00:00:00Z"}}
        transport = _make_mock_transport(
            responses={url: httpx.Response(200, json=api_resp)},
        )
        async with httpx.AsyncClient(transport=transport) as client:
            with patch("src.analyses.safety.web_risk.get_access_token", return_value="tok"):
                result = await check_urls([url], pool=db_pool, httpx_client=client)

        assert result[url].threat_types == ["MALWARE"]


class TestCacheMissParsesMultipleThreatTypes:
    async def test_cache_miss_parses_multiple_threat_types(
        self, db_pool: asyncpg.Pool
    ) -> None:
        url = "https://phishing.example.com/"
        api_resp = {
            "threat": {
                "threatTypes": ["MALWARE", "SOCIAL_ENGINEERING"],
                "expireTime": "2099-01-01T00:00:00Z",
            }
        }
        transport = _make_mock_transport(
            responses={url: httpx.Response(200, json=api_resp)},
        )
        async with httpx.AsyncClient(transport=transport) as client:
            with patch("src.analyses.safety.web_risk.get_access_token", return_value="tok"):
                result = await check_urls([url], pool=db_pool, httpx_client=client)

        assert set(result[url].threat_types) == {"MALWARE", "SOCIAL_ENGINEERING"}


class TestTransientErrors:
    async def test_429_raises_transient_error(self, db_pool: asyncpg.Pool) -> None:
        url = "https://rate-limited.example.com/"
        transport = _make_mock_transport(
            default_response=httpx.Response(429, json={"error": "rate limited"}),
        )
        async with httpx.AsyncClient(transport=transport) as client:
            with patch("src.analyses.safety.web_risk.get_access_token", return_value="tok"):
                with pytest.raises(WebRiskTransientError):
                    await check_urls([url], pool=db_pool, httpx_client=client)

    async def test_500_raises_transient_error(self, db_pool: asyncpg.Pool) -> None:
        url = "https://server-error.example.com/"
        transport = _make_mock_transport(
            default_response=httpx.Response(500, json={"error": "internal"}),
        )
        async with httpx.AsyncClient(transport=transport) as client:
            with patch("src.analyses.safety.web_risk.get_access_token", return_value="tok"):
                with pytest.raises(WebRiskTransientError):
                    await check_urls([url], pool=db_pool, httpx_client=client)

    async def test_missing_adc_token_raises_transient_error(
        self, db_pool: asyncpg.Pool
    ) -> None:
        url = "https://no-token.example.com/"
        transport = _make_mock_transport()
        async with httpx.AsyncClient(transport=transport) as client:
            with patch("src.analyses.safety.web_risk.get_access_token", return_value=None):
                with pytest.raises(WebRiskTransientError, match="ADC token unavailable"):
                    await check_urls([url], pool=db_pool, httpx_client=client)


class TestConcurrencyBoundedBySemaphore:
    async def test_concurrency_bounded_by_semaphore(
        self, db_pool: asyncpg.Pool
    ) -> None:
        urls = [f"https://concurrent-{i}.example.com/" for i in range(20)]
        max_concurrent = 0
        active = 0
        lock = asyncio.Lock()

        async def slow_handler(request: httpx.Request) -> httpx.Response:
            nonlocal max_concurrent, active
            async with lock:
                active += 1
                if active > max_concurrent:
                    max_concurrent = active
            await asyncio.sleep(0.02)
            async with lock:
                active -= 1
            return httpx.Response(200, json={})

        transport = httpx.MockTransport(slow_handler)
        async with httpx.AsyncClient(transport=transport) as client:
            with patch("src.analyses.safety.web_risk.get_access_token", return_value="tok"):
                await check_urls(urls, pool=db_pool, httpx_client=client)

        assert max_concurrent <= 8


class TestEmptyInput:
    async def test_empty_input_returns_empty_dict_no_api_calls(
        self, db_pool: asyncpg.Pool
    ) -> None:
        request_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal request_count
            request_count += 1
            return httpx.Response(200, json={})

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            with patch("src.analyses.safety.web_risk.get_access_token", return_value="tok"):
                result = await check_urls([], pool=db_pool, httpx_client=client)

        assert result == {}
        assert request_count == 0
