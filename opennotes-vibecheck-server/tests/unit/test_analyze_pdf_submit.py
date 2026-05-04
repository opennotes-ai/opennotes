"""Route-level DB-backed tests for POST /api/analyze-pdf (TASK-1498.05)."""
from __future__ import annotations

import socket
from collections.abc import AsyncIterator, Iterator
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import asyncpg
import httpx
import pytest

from src.config import get_settings
from src.main import app
from src.routes import analyze as analyze_route
from src.routes import analyze_pdf
from tests.conftest import VIBECHECK_JOBS_DDL

_REAL_GETADDRINFO = socket.getaddrinfo


_MINIMAL_DDL = """
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE TABLE vibecheck_analyses (
    url TEXT PRIMARY KEY,
    sidebar_payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL
);
""" + VIBECHECK_JOBS_DDL


@pytest.fixture(autouse=True)
def _restore_real_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    # conftest.py stubs every DNS lookup for SSRF tests; restore live
    # DNS so testcontainers can reach the Postgres it starts.
    monkeypatch.setattr(socket, "getaddrinfo", _REAL_GETADDRINFO)


@pytest.fixture(scope="module")
def _postgres_container() -> Iterator[Any]:
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg


@pytest.fixture
async def db_pool(_postgres_container: Any) -> AsyncIterator[Any]:
    raw = _postgres_container.get_connection_url()
    dsn = raw.replace("postgresql+psycopg2://", "postgresql://")
    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=8)
    assert pool is not None
    async with pool.acquire() as conn:
        await conn.execute(
            "DROP TABLE IF EXISTS vibecheck_jobs CASCADE;"
            "DROP TABLE IF EXISTS vibecheck_analyses CASCADE;"
        )
        await conn.execute(_MINIMAL_DDL)
    try:
        yield pool
    finally:
        await pool.close()


@pytest.fixture
def enqueue_mock(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    mock = AsyncMock(return_value=None)
    monkeypatch.setattr(analyze_pdf, "enqueue_job", mock)
    return mock


@pytest.fixture
async def client(
    db_pool: Any, enqueue_mock: AsyncMock
) -> AsyncIterator[httpx.AsyncClient]:
    get_settings.cache_clear()
    app.state.limiter = analyze_route.limiter
    app.state.db_pool = db_pool
    analyze_route.limiter.reset()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as async_client:
        yield async_client
    app.state.db_pool = None
    analyze_route.limiter.reset()
    get_settings.cache_clear()


def _fake_pdf_store_factory(
    metadata_by_key: dict[str, dict[str, object] | None]
) -> type[object]:
    class _FakePdfUploadStore:
        def __init__(self, bucket_name: str) -> None:
            assert bucket_name == "test-pdf-bucket"

        def get_metadata(self, key: str) -> dict[str, object] | None:
            return metadata_by_key.get(key)

    return _FakePdfUploadStore


async def _count_jobs(db_pool, normalized_url: str | None = None) -> int:
    async with db_pool.acquire() as conn:
        if normalized_url is None:
            return await conn.fetchval("SELECT COUNT(*) FROM vibecheck_jobs")
        return await conn.fetchval(
            "SELECT COUNT(*) FROM vibecheck_jobs WHERE normalized_url = $1",
            normalized_url,
        )


async def _insert_inflight_pdf_job(db_pool, gcs_key: str) -> UUID:
    async with db_pool.acquire() as conn:
        job_id = await conn.fetchval(
            """
            INSERT INTO vibecheck_jobs (url, normalized_url, host, source_type, status)
            VALUES ($1, $1, '', 'pdf', 'pending')
            RETURNING job_id
            """,
            gcs_key,
        )
    assert isinstance(job_id, UUID)
    return job_id


async def test_analyze_pdf_submits_valid_gcs_key(
    client: httpx.AsyncClient,
    db_pool,
    enqueue_mock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VIBECHECK_PDF_UPLOAD_BUCKET", "test-pdf-bucket")
    get_settings.cache_clear()
    key = str(uuid4())
    monkeypatch.setattr(
        analyze_pdf,
        "get_pdf_upload_store",
        _fake_pdf_store_factory({key: {"size": 512, "content_type": "application/pdf"}}),
    )

    resp = await client.post("/api/analyze-pdf", json={"gcs_key": key})

    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "pending"
    assert body["cached"] is False
    job_id = UUID(body["job_id"])

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT url, normalized_url, host, source_type, status, cached"
            " FROM vibecheck_jobs WHERE job_id = $1",
            job_id,
        )
    assert row is not None
    assert row["url"] == key
    assert row["normalized_url"] == key
    assert row["host"] == "gcs-pdf"
    assert row["source_type"] == "pdf"
    assert row["status"] == "pending"
    assert row["cached"] is False
    assert enqueue_mock.await_count == 1


async def test_analyze_pdf_duplicate_inflight_dedupes_without_second_enqueue(
    client: httpx.AsyncClient,
    db_pool,
    enqueue_mock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VIBECHECK_PDF_UPLOAD_BUCKET", "test-pdf-bucket")
    get_settings.cache_clear()
    key = str(uuid4())
    existing_job_id = await _insert_inflight_pdf_job(db_pool, key)
    monkeypatch.setattr(
        analyze_pdf,
        "get_pdf_upload_store",
        _fake_pdf_store_factory({key: {"size": 1024, "content_type": "application/pdf"}}),
    )

    first = await client.post("/api/analyze-pdf", json={"gcs_key": key})
    second = await client.post("/api/analyze-pdf", json={"gcs_key": key})

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["job_id"] == str(existing_job_id)
    assert second.json()["job_id"] == str(existing_job_id)
    assert await _count_jobs(db_pool, normalized_url=key) == 1
    assert enqueue_mock.await_count == 0


async def test_analyze_pdf_rejects_malformed_gcs_key(
    client: httpx.AsyncClient,
    db_pool,
    enqueue_mock,
) -> None:
    before = await _count_jobs(db_pool)
    resp = await client.post("/api/analyze-pdf", json={"gcs_key": "not-a-uuid"})

    assert resp.status_code == 400
    assert resp.json()["error_code"] == "upload_key_invalid"
    assert await _count_jobs(db_pool) == before
    assert enqueue_mock.await_count == 0


async def test_analyze_pdf_accepts_non_v4_uuid_when_present_in_gcs(
    client: httpx.AsyncClient,
    db_pool,
    enqueue_mock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TASK-1498.30: parser-only validation — GCS existence is the security gate."""
    monkeypatch.setenv("VIBECHECK_PDF_UPLOAD_BUCKET", "test-pdf-bucket")
    get_settings.cache_clear()
    key = "11111111-1111-1111-1111-111111111111"
    monkeypatch.setattr(
        analyze_pdf,
        "get_pdf_upload_store",
        _fake_pdf_store_factory({key: {"size": 1024, "content_type": "application/pdf"}}),
    )

    resp = await client.post("/api/analyze-pdf", json={"gcs_key": key})

    assert resp.status_code == 202
    assert enqueue_mock.await_count == 1
    assert await _count_jobs(db_pool, normalized_url=key) == 1


async def test_analyze_pdf_transient_storage_error_returns_503(
    client: httpx.AsyncClient,
    db_pool,
    enqueue_mock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TASK-1498.24: transient GCS errors map to 503 upstream_error, not 400 not-found."""
    monkeypatch.setenv("VIBECHECK_PDF_UPLOAD_BUCKET", "test-pdf-bucket")
    get_settings.cache_clear()
    key = str(uuid4())

    class _FlakyPdfUploadStore:
        def __init__(self, bucket_name: str) -> None:
            assert bucket_name == "test-pdf-bucket"

        def get_metadata(self, key: str) -> dict[str, object] | None:
            raise RuntimeError("gcs transient outage")

    monkeypatch.setattr(analyze_pdf, "get_pdf_upload_store", lambda _: _FlakyPdfUploadStore("test-pdf-bucket"))
    before = await _count_jobs(db_pool)

    resp = await client.post("/api/analyze-pdf", json={"gcs_key": key})

    assert resp.status_code == 503
    body = resp.json()
    assert body["error_code"] == "upstream_error"
    assert await _count_jobs(db_pool) == before
    assert enqueue_mock.await_count == 0


async def test_analyze_pdf_missing_metadata_rejects_with_upload_not_found(
    client: httpx.AsyncClient,
    db_pool,
    enqueue_mock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VIBECHECK_PDF_UPLOAD_BUCKET", "test-pdf-bucket")
    get_settings.cache_clear()
    key = str(uuid4())
    monkeypatch.setattr(
        analyze_pdf,
        "get_pdf_upload_store",
        _fake_pdf_store_factory({key: None}),
    )
    before = await _count_jobs(db_pool)

    resp = await client.post("/api/analyze-pdf", json={"gcs_key": key})

    assert resp.status_code == 400
    body = resp.json()
    assert body["error_code"] == "upload_not_found"
    assert "PDF not found; upload may have failed" in body["message"]
    assert await _count_jobs(db_pool) == before
    assert await _count_jobs(db_pool, normalized_url=key) == 0
    assert enqueue_mock.await_count == 0


async def test_analyze_pdf_oversize_pdf_rejects(
    client: httpx.AsyncClient,
    db_pool,
    enqueue_mock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VIBECHECK_PDF_UPLOAD_BUCKET", "test-pdf-bucket")
    get_settings.cache_clear()
    key = str(uuid4())
    monkeypatch.setattr(
        analyze_pdf,
        "get_pdf_upload_store",
        _fake_pdf_store_factory(
            {key: {"size": 50 * 1024 * 1024 + 1, "content_type": "application/pdf"}}
        ),
    )
    before = await _count_jobs(db_pool)

    resp = await client.post("/api/analyze-pdf", json={"gcs_key": key})

    assert resp.status_code == 400
    assert resp.json()["error_code"] == "pdf_too_large"
    assert await _count_jobs(db_pool) == before
    assert await _count_jobs(db_pool, normalized_url=key) == 0
    assert enqueue_mock.await_count == 0


async def test_analyze_pdf_bad_content_type_rejects(
    client: httpx.AsyncClient,
    db_pool,
    enqueue_mock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VIBECHECK_PDF_UPLOAD_BUCKET", "test-pdf-bucket")
    get_settings.cache_clear()
    key = str(uuid4())
    monkeypatch.setattr(
        analyze_pdf,
        "get_pdf_upload_store",
        _fake_pdf_store_factory({key: {"size": 1024, "content_type": "text/plain"}}),
    )
    before = await _count_jobs(db_pool)

    resp = await client.post("/api/analyze-pdf", json={"gcs_key": key})

    assert resp.status_code == 400
    assert resp.json()["error_code"] == "invalid_pdf_type"
    assert await _count_jobs(db_pool) == before
    assert await _count_jobs(db_pool, normalized_url=key) == 0
    assert enqueue_mock.await_count == 0


async def test_rate_limit_for_analyze_pdf_shares_analyze_bucket(
    client: httpx.AsyncClient,
    db_pool,
    enqueue_mock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RATE_LIMIT_PER_IP_PER_HOUR", "1")
    get_settings.cache_clear()
    analyze_route.limiter.reset()

    key = str(uuid4())
    monkeypatch.setenv("VIBECHECK_PDF_UPLOAD_BUCKET", "test-pdf-bucket")
    monkeypatch.setattr(
        analyze_pdf,
        "get_pdf_upload_store",
        _fake_pdf_store_factory({key: {"size": 1024, "content_type": "application/pdf"}}),
    )

    first_resp = await client.post("/api/analyze-pdf", json={"gcs_key": key})
    second_resp = await client.post("/api/analyze-pdf", json={"gcs_key": key})

    assert first_resp.status_code == 202
    assert second_resp.status_code == 429
    assert enqueue_mock.await_count == 1
    assert await _count_jobs(db_pool, normalized_url=key) == 1


async def test_analyze_and_analyze_pdf_share_submit_rate_limit_bucket(
    client: httpx.AsyncClient,
    db_pool,
    enqueue_mock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RATE_LIMIT_PER_IP_PER_HOUR", "1")
    monkeypatch.setenv("VIBECHECK_PDF_UPLOAD_BUCKET", "test-pdf-bucket")
    get_settings.cache_clear()
    analyze_route.limiter.reset()
    monkeypatch.setattr(analyze_route, "check_urls", AsyncMock(return_value={}))
    monkeypatch.setattr(analyze_route, "enqueue_job", enqueue_mock)

    key = str(uuid4())
    monkeypatch.setattr(
        analyze_pdf,
        "get_pdf_upload_store",
        _fake_pdf_store_factory({key: {"size": 1024, "content_type": "application/pdf"}}),
    )

    url_resp = await client.post("/api/analyze", json={"url": "https://example.com/url-first"})
    pdf_resp = await client.post("/api/analyze-pdf", json={"gcs_key": key})

    assert url_resp.status_code == 202, url_resp.text
    assert pdf_resp.status_code == 429
    assert await _count_jobs(db_pool, normalized_url="https://example.com/url-first") == 1
    assert await _count_jobs(db_pool, normalized_url=key) == 0
    assert enqueue_mock.await_count == 1
