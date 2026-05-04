"""Unit tests for `POST /api/upload-pdf` (TASK-1498.04)."""
from __future__ import annotations

import re
from collections.abc import AsyncIterator
from datetime import timedelta

import httpx
import pytest

from src.config import get_settings
from src.jobs.pdf_storage import PdfUploadStore
from src.main import app
from src.routes import analyze as analyze_route
from src.routes import analyze_pdf


def _assert_uuid_like(value: str) -> None:
    assert re.fullmatch(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        value,
    )


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    get_settings.cache_clear()
    app.state.limiter = analyze_route.limiter
    analyze_route.limiter.reset()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as async_client:
        yield async_client
    analyze_route.limiter.reset()
    get_settings.cache_clear()


def _fake_pdf_store_factory(returned_url: str) -> type[object]:
    class _FakePdfUploadStore:
        def __init__(self, bucket_name: str) -> None:
            assert bucket_name == "test-pdf-bucket"

        def signed_upload_url(self, key: str, *, ttl_seconds: int = 900) -> str:
            assert key
            assert ttl_seconds == 900
            return returned_url

    return _FakePdfUploadStore


def _failing_pdf_store_factory() -> type[object]:
    class _FailingPdfUploadStore:
        def __init__(self, bucket_name: str) -> None:
            assert bucket_name == "test-pdf-bucket"

        def signed_upload_url(self, key: str, *, ttl_seconds: int = 900) -> None:
            assert key
            assert ttl_seconds == 900

    return _FailingPdfUploadStore


def _exploding_pdf_store_factory() -> type[object]:
    class _ExplodingPdfUploadStore:
        def __init__(self, bucket_name: str) -> None:
            assert bucket_name == "test-pdf-bucket"
            raise RuntimeError("storage unavailable")

    return _ExplodingPdfUploadStore


def test_router_includes_upload_pdf_route() -> None:
    assert any(
        route.path == "/api/upload-pdf"
        for route in app.router.routes
        if getattr(route, "methods", None)
    )


async def test_upload_pdf_returns_uuid_and_upload_url(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VIBECHECK_PDF_UPLOAD_BUCKET", "test-pdf-bucket")
    get_settings.cache_clear()
    monkeypatch.setattr(analyze_pdf, "PdfUploadStore", _fake_pdf_store_factory("https://upload.example/upload"))

    response = await client.post("/api/upload-pdf")

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body.keys()) == {"gcs_key", "upload_url"}
    _assert_uuid_like(body["gcs_key"])
    assert body["upload_url"] == "https://upload.example/upload"


async def test_upload_pdf_returns_internal_error_when_bucket_unset(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("VIBECHECK_PDF_UPLOAD_BUCKET", raising=False)
    get_settings.cache_clear()

    response = await client.post("/api/upload-pdf")

    assert response.status_code == 500
    assert response.json() == {
        "error_code": "internal",
        "message": "PDF upload bucket is not configured",
    }


async def test_upload_pdf_returns_internal_error_when_signing_fails(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VIBECHECK_PDF_UPLOAD_BUCKET", "test-pdf-bucket")
    get_settings.cache_clear()
    monkeypatch.setattr(analyze_pdf, "PdfUploadStore", _failing_pdf_store_factory())

    response = await client.post("/api/upload-pdf")

    assert response.status_code == 500
    assert response.json() == {
        "error_code": "internal",
        "message": "PDF upload URL signing failed",
    }


async def test_upload_pdf_returns_internal_error_when_store_setup_fails(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VIBECHECK_PDF_UPLOAD_BUCKET", "test-pdf-bucket")
    get_settings.cache_clear()
    monkeypatch.setattr(analyze_pdf, "PdfUploadStore", _exploding_pdf_store_factory())

    response = await client.post("/api/upload-pdf")

    assert response.status_code == 500
    assert response.json() == {
        "error_code": "internal",
        "message": "PDF upload URL signing failed",
    }


async def test_upload_pdf_route_respects_analyze_rate_limit(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RATE_LIMIT_PER_IP_PER_HOUR", "1")
    monkeypatch.setenv("VIBECHECK_PDF_UPLOAD_BUCKET", "test-pdf-bucket")
    get_settings.cache_clear()
    analyze_route.limiter.reset()
    monkeypatch.setattr(analyze_pdf, "PdfUploadStore", _fake_pdf_store_factory("https://upload.example/upload"))

    first = await client.post("/api/upload-pdf")
    second = await client.post("/api/upload-pdf")

    assert first.status_code == 200
    assert second.status_code == 429


def test_pdf_upload_store_mints_v4_put_url_for_application_pdf(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class _FakeBlob:
        def generate_signed_url(self, **kwargs: object) -> str:
            captured["signed_url_kwargs"] = kwargs
            return "https://storage.example/upload"

    class _FakeBucket:
        def __init__(self, bucket_name: str) -> None:
            captured["bucket_name"] = bucket_name

        def blob(self, key: str) -> _FakeBlob:
            captured["blob_key"] = key
            return _FakeBlob()

    class _FakeStorageClient:
        def bucket(self, bucket_name: str) -> _FakeBucket:
            return _FakeBucket(bucket_name)

    class _FakeCredentials:
        service_account_email = "signer@example.iam.gserviceaccount.com"
        token = "access-token"

        def refresh(self, request: object) -> None:
            captured["refresh_request"] = request

    monkeypatch.setattr("google.cloud.storage.Client", _FakeStorageClient)
    monkeypatch.setattr(
        "google.auth.default",
        lambda: (_FakeCredentials(), "test-project"),
    )

    store = PdfUploadStore("test-pdf-bucket")
    upload_url = store.signed_upload_url("pdf-key", ttl_seconds=123)

    assert upload_url == "https://storage.example/upload"
    assert captured["bucket_name"] == "test-pdf-bucket"
    assert captured["blob_key"] == "pdf-key"
    assert "refresh_request" not in captured
    assert captured["signed_url_kwargs"] == {
        "version": "v4",
        "expiration": timedelta(seconds=123),
        "method": "PUT",
        "content_type": "application/pdf",
        "service_account_email": "signer@example.iam.gserviceaccount.com",
        "access_token": "access-token",
    }
