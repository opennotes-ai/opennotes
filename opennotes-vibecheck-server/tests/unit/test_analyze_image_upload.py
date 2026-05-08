"""Route-level tests for multi-image upload and conversion submit."""
from __future__ import annotations

import json
import socket
from collections.abc import AsyncIterator, Iterator
from typing import Any, ClassVar
from unittest.mock import AsyncMock
from uuid import UUID

import asyncpg
import httpx
import pytest

from src.config import get_settings
from src.main import app
from src.routes import analyze as analyze_route
from src.routes import analyze_pdf
from tests.conftest import VIBECHECK_IMAGE_UPLOAD_BATCHES_DDL, VIBECHECK_JOBS_DDL

_REAL_GETADDRINFO = socket.getaddrinfo

_MINIMAL_DDL = (
    "CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\";"
    + VIBECHECK_JOBS_DDL
    + VIBECHECK_IMAGE_UPLOAD_BATCHES_DDL
)


@pytest.fixture(autouse=True)
def _restore_real_dns(monkeypatch: pytest.MonkeyPatch) -> None:
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
            "DROP TABLE IF EXISTS vibecheck_image_upload_batches CASCADE;"
            "DROP TABLE IF EXISTS vibecheck_jobs CASCADE;"
        )
        await conn.execute(_MINIMAL_DDL)
    try:
        yield pool
    finally:
        await pool.close()


@pytest.fixture
def enqueue_conversion_mock(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    mock = AsyncMock(return_value=None)
    monkeypatch.setattr(analyze_pdf, "enqueue_image_conversion", mock)
    return mock


@pytest.fixture
async def client(
    db_pool: Any, enqueue_conversion_mock: AsyncMock
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


class _FakeUploadStore:
    metadata_by_key: ClassVar[dict[str, dict[str, object] | None]] = {}

    def __init__(self, bucket_name: str) -> None:
        assert bucket_name == "test-pdf-bucket"

    def signed_upload_url(
        self,
        key: str,
        *,
        ttl_seconds: int = 900,
        content_type: str = "application/pdf",
    ) -> str:
        assert ttl_seconds == 900
        return f"https://upload.example/{content_type}/{key}"

    def get_metadata(self, key: str) -> dict[str, object] | None:
        return self.metadata_by_key.get(key)


@pytest.fixture(autouse=True)
def _fake_store(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeUploadStore.metadata_by_key = {}
    monkeypatch.setenv("VIBECHECK_PDF_UPLOAD_BUCKET", "test-pdf-bucket")
    get_settings.cache_clear()
    monkeypatch.setattr(analyze_pdf, "get_pdf_upload_store", _FakeUploadStore)


async def test_upload_images_creates_pending_pdf_job_and_ordered_batch(
    client: httpx.AsyncClient,
    db_pool: Any,
) -> None:
    response = await client.post(
        "/api/upload-images",
        json={
            "images": [
                {"filename": "first.png", "content_type": "image/png", "size_bytes": 12},
                {"filename": "second.jpg", "content_type": "image/jpeg", "size_bytes": 34},
            ]
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    job_id = UUID(body["job_id"])
    assert [image["ordinal"] for image in body["images"]] == [0, 1]
    assert body["images"][0]["gcs_key"].startswith(f"image-uploads/{job_id}/source/000-")
    assert body["images"][1]["gcs_key"].startswith(f"image-uploads/{job_id}/source/001-")
    assert "image/png" in body["images"][0]["upload_url"]
    assert "image/jpeg" in body["images"][1]["upload_url"]

    async with db_pool.acquire() as conn:
        job = await conn.fetchrow(
            "SELECT source_type, status, last_stage FROM vibecheck_jobs WHERE job_id = $1",
            job_id,
        )
        batch = await conn.fetchrow(
            "SELECT images, conversion_status, generated_pdf_gcs_key "
            "FROM vibecheck_image_upload_batches WHERE job_id = $1",
            job_id,
        )

    assert job is not None
    assert job["source_type"] == "pdf"
    assert job["status"] == "pending"
    assert job["last_stage"] == "converting_images"
    assert batch is not None
    assert batch["conversion_status"] == "awaiting_upload"
    stored_images = json.loads(batch["images"]) if isinstance(batch["images"], str) else batch["images"]
    assert [image["filename"] for image in stored_images] == ["first.png", "second.jpg"]
    assert batch["generated_pdf_gcs_key"] == f"image-uploads/{job_id}/generated.pdf"


async def test_upload_images_rejects_aggregate_size_before_creating_job(
    client: httpx.AsyncClient,
    db_pool: Any,
) -> None:
    response = await client.post(
        "/api/upload-images",
        json={
            "images": [
                {
                    "filename": "too-big.png",
                    "content_type": "image/png",
                    "size_bytes": 45 * 1024 * 1024 + 1,
                }
            ]
        },
    )

    assert response.status_code == 400
    assert response.json()["error_code"] == "image_aggregate_too_large"
    async with db_pool.acquire() as conn:
        assert await conn.fetchval("SELECT COUNT(*) FROM vibecheck_jobs") == 0


async def test_upload_images_rejects_unsupported_content_type(
    client: httpx.AsyncClient,
    db_pool: Any,
) -> None:
    response = await client.post(
        "/api/upload-images",
        json={
            "images": [
                {"filename": "bad.webp", "content_type": "image/webp", "size_bytes": 12}
            ]
        },
    )

    assert response.status_code == 400
    assert response.json()["error_code"] == "invalid_image_type"
    async with db_pool.acquire() as conn:
        assert await conn.fetchval("SELECT COUNT(*) FROM vibecheck_jobs") == 0


async def test_analyze_images_validates_uploaded_objects_and_enqueues_conversion(
    client: httpx.AsyncClient,
    enqueue_conversion_mock: AsyncMock,
) -> None:
    upload = await client.post(
        "/api/upload-images",
        json={
            "images": [
                {"filename": "first.png", "content_type": "image/png", "size_bytes": 12},
                {"filename": "second.jpg", "content_type": "image/jpeg", "size_bytes": 34},
            ]
        },
    )
    body = upload.json()
    for image, size, content_type in zip(
        body["images"],
        [12, 34],
        ["image/png", "image/jpeg"],
        strict=True,
    ):
        _FakeUploadStore.metadata_by_key[image["gcs_key"]] = {
            "size": size,
            "content_type": content_type,
        }

    response = await client.post("/api/analyze-images", json={"job_id": body["job_id"]})

    assert response.status_code == 202, response.text
    assert response.json() == {
        "job_id": body["job_id"],
        "status": "pending",
        "cached": False,
    }
    assert enqueue_conversion_mock.await_count == 1


async def test_analyze_images_rejects_missing_uploaded_object(
    client: httpx.AsyncClient,
    enqueue_conversion_mock: AsyncMock,
) -> None:
    upload = await client.post(
        "/api/upload-images",
        json={
            "images": [
                {"filename": "missing.png", "content_type": "image/png", "size_bytes": 12}
            ]
        },
    )

    response = await client.post(
        "/api/analyze-images",
        json={"job_id": upload.json()["job_id"]},
    )

    assert response.status_code == 400
    assert response.json()["error_code"] == "upload_not_found"
    assert enqueue_conversion_mock.await_count == 0
