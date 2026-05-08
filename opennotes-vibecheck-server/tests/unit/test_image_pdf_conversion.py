"""Unit tests for image-to-PDF conversion orchestration."""
from __future__ import annotations

import json
import socket
from collections.abc import AsyncIterator, Iterator
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import asyncpg
import pytest

from src.config import get_settings
from src.jobs import image_pdf_conversion
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


class _FakeStore:
    def __init__(self) -> None:
        self.read_keys: list[str] = []
        self.writes: dict[str, bytes] = {}

    def read_bytes(self, key: str) -> bytes:
        self.read_keys.append(key)
        return f"bytes:{key}".encode()

    def write_pdf(self, key: str, data: bytes) -> None:
        self.writes[key] = data


@pytest.fixture
def fake_store(monkeypatch: pytest.MonkeyPatch) -> _FakeStore:
    store = _FakeStore()
    monkeypatch.setenv("VIBECHECK_PDF_UPLOAD_BUCKET", "test-pdf-bucket")
    get_settings.cache_clear()
    monkeypatch.setattr(image_pdf_conversion, "get_pdf_upload_store", lambda _: store)
    return store


async def _insert_image_job(
    pool: Any,
    *,
    conversion_status: str = "submitted",
) -> tuple[UUID, UUID]:
    job_id = uuid4()
    attempt_id = uuid4()
    images = [
        {
            "ordinal": 1,
            "gcs_key": "image-uploads/job/source/001-second",
            "content_type": "image/jpeg",
            "size_bytes": 34,
            "filename": "second.jpg",
        },
        {
            "ordinal": 0,
            "gcs_key": "image-uploads/job/source/000-first",
            "content_type": "image/png",
            "size_bytes": 12,
            "filename": "first.png",
        },
    ]
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO vibecheck_jobs (
                job_id, url, normalized_url, host, source_type, status, attempt_id
            )
            VALUES ($1, $2, $2, 'gcs-image', 'pdf', 'pending', $3)
            """,
            job_id,
            f"image-upload://{job_id}",
            attempt_id,
        )
        await conn.execute(
            """
            INSERT INTO vibecheck_image_upload_batches (
                job_id, images, conversion_status, generated_pdf_gcs_key
            )
            VALUES ($1, $2::jsonb, $3, $4)
            """,
            job_id,
            json.dumps(images),
            conversion_status,
            f"image-uploads/{job_id}/generated.pdf",
        )
    return job_id, attempt_id


async def test_run_image_conversion_writes_pdf_and_enqueues_normal_pipeline(
    db_pool: Any,
    fake_store: _FakeStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id, attempt_id = await _insert_image_job(db_pool)
    enqueue_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(image_pdf_conversion, "enqueue_job", enqueue_mock)
    monkeypatch.setattr(
        image_pdf_conversion,
        "_convert_images_to_pdf",
        lambda image_bytes: b"%PDF generated",
    )

    result = await image_pdf_conversion.run_image_conversion(
        db_pool, job_id, attempt_id, get_settings()
    )

    assert result.status_code == 200
    assert fake_store.read_keys == [
        "image-uploads/job/source/000-first",
        "image-uploads/job/source/001-second",
    ]
    assert fake_store.writes == {f"image-uploads/{job_id}/generated.pdf": b"%PDF generated"}
    enqueue_mock.assert_awaited_once_with(job_id, attempt_id, get_settings())
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT j.url, j.normalized_url, j.host, j.status, j.last_stage,
                   b.conversion_status
            FROM vibecheck_jobs j
            JOIN vibecheck_image_upload_batches b ON b.job_id = j.job_id
            WHERE j.job_id = $1
            """,
            job_id,
        )
    assert row["url"] == f"image-uploads/{job_id}/generated.pdf"
    assert row["normalized_url"] == f"image-uploads/{job_id}/generated.pdf"
    assert row["host"] == "gcs-pdf"
    assert row["status"] == "pending"
    assert row["last_stage"] == "pdf_extract"
    assert row["conversion_status"] == "converted"


async def test_run_image_conversion_marks_conversion_failure_terminal(
    db_pool: Any,
    fake_store: _FakeStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id, attempt_id = await _insert_image_job(db_pool)
    enqueue_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(image_pdf_conversion, "enqueue_job", enqueue_mock)

    def _raise_conversion_error(_image_bytes: list[bytes]) -> bytes:
        raise RuntimeError("cannot decode")

    monkeypatch.setattr(
        image_pdf_conversion,
        "_convert_images_to_pdf",
        _raise_conversion_error,
    )

    result = await image_pdf_conversion.run_image_conversion(
        db_pool, job_id, attempt_id, get_settings()
    )

    assert result.status_code == 200
    assert enqueue_mock.await_count == 0
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT j.status, j.error_code AS job_error_code,
                   b.conversion_status, b.error_code AS batch_error_code
            FROM vibecheck_jobs j
            JOIN vibecheck_image_upload_batches b ON b.job_id = j.job_id
            WHERE j.job_id = $1
            """,
            job_id,
        )
    assert row["status"] == "failed"
    assert row["job_error_code"] == "image_conversion_failed"
    assert row["conversion_status"] == "failed"
    assert row["batch_error_code"] == "image_conversion_failed"


async def test_run_image_conversion_reenqueues_already_converted_job(
    db_pool: Any,
    fake_store: _FakeStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id, attempt_id = await _insert_image_job(db_pool, conversion_status="converted")
    enqueue_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(image_pdf_conversion, "enqueue_job", enqueue_mock)

    result = await image_pdf_conversion.run_image_conversion(
        db_pool, job_id, attempt_id, get_settings()
    )

    assert result.status_code == 200
    assert fake_store.read_keys == []
    assert fake_store.writes == {}
    enqueue_mock.assert_awaited_once_with(job_id, attempt_id, get_settings())
