"""Unit tests for analyze_pdf_handler (TASK-1657.14).

Covers:
- upload-images endpoint: validates input, writes to staging (mocked GCS)
- analyze-images endpoint: dispatches image-to-PDF conversion
- analyze-pdf endpoint: validates uploaded PDF and enqueues url_scan workflow
- conversion workflow: turns N images into a single PDF (mocked GCS + img2pdf)
"""

from __future__ import annotations

import json
from contextlib import AbstractAsyncContextManager
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from src.url_content_scan.analyze_pdf_handler import (
    AnalyzeImagesRequest,
    AnalyzePDFRequest,
    ImageUploadItem,
    UploadImagesRequest,
    handle_analyze_images,
    handle_analyze_pdf,
    handle_upload_images,
    handle_upload_pdf,
)
from src.url_content_scan.models import UrlScanImageUploadBatch


class _FakeRequest:
    def __init__(self):
        self.app = SimpleNamespace(state=SimpleNamespace())
        self.state = SimpleNamespace()
        self.client = SimpleNamespace(host="127.0.0.1")


class _FakeTransaction(AbstractAsyncContextManager["_FakeTransaction"]):
    def __init__(self, session: _FakeSession) -> None:
        self._session = session

    async def __aenter__(self) -> _FakeTransaction:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        pass


class _FakeSession:
    def __init__(self) -> None:
        self._objects: dict[UUID, object] = {}
        self.added: list[object] = []
        self.flush_count = 0

    def begin(self) -> _FakeTransaction:
        return _FakeTransaction(self)

    def add(self, obj: object) -> None:
        self.added.append(obj)
        if isinstance(obj, UrlScanImageUploadBatch):
            self._objects[obj.id] = obj

    async def flush(self) -> None:
        self.flush_count += 1
        for obj in self.added:
            if isinstance(obj, UrlScanImageUploadBatch) and obj.id not in self._objects:
                self._objects[obj.id] = obj

    async def get(self, model, key):
        return self._objects.get(key)


class _FakePdfStore:
    def __init__(
        self,
        *,
        upload_url: str = "https://storage.googleapis.com/bucket/key?sig=abc",
        metadata: dict | None = None,
        should_fail_sign: bool = False,
        should_fail_metadata: bool = False,
    ) -> None:
        self._upload_url = upload_url
        self._metadata = metadata
        self._should_fail_sign = should_fail_sign
        self._should_fail_metadata = should_fail_metadata
        self.signed_calls: list[tuple] = []
        self.metadata_calls: list[str] = []

    async def signed_upload_url(
        self, key: str, *, ttl_seconds: int = 900, content_type: str | None = None
    ) -> str:
        if self._should_fail_sign:
            raise RuntimeError("sign failed")
        self.signed_calls.append((key, ttl_seconds, content_type))
        return self._upload_url

    async def get_metadata(self, key: str) -> dict | None:
        if self._should_fail_metadata:
            raise RuntimeError("metadata failed")
        self.metadata_calls.append(key)
        return self._metadata


class TestHandleUploadPdf:
    @pytest.mark.asyncio
    async def test_returns_gcs_key_and_upload_url(self, monkeypatch):
        monkeypatch.setenv("URL_SCAN_PDF_UPLOAD_BUCKET", "test-bucket")
        from src import config as cfg

        cfg._settings_instance = None
        cfg._settings_initialized = False

        store = _FakePdfStore(upload_url="https://storage.example.com/signed")
        result = await handle_upload_pdf(_FakeRequest(), _pdf_store=store)

        assert hasattr(result, "gcs_key")
        assert hasattr(result, "upload_url")
        assert result.upload_url == "https://storage.example.com/signed"
        UUID(result.gcs_key)

    @pytest.mark.asyncio
    async def test_returns_error_when_bucket_not_configured(self, monkeypatch):
        monkeypatch.setenv("URL_SCAN_PDF_UPLOAD_BUCKET", "")
        from src import config as cfg

        cfg._settings_instance = None
        cfg._settings_initialized = False

        from fastapi.responses import JSONResponse

        result = await handle_upload_pdf(_FakeRequest())
        assert isinstance(result, JSONResponse)
        assert result.status_code == 500

    @pytest.mark.asyncio
    async def test_returns_error_when_signing_fails(self, monkeypatch):
        monkeypatch.setenv("URL_SCAN_PDF_UPLOAD_BUCKET", "test-bucket")
        from src import config as cfg

        cfg._settings_instance = None
        cfg._settings_initialized = False

        store = _FakePdfStore(should_fail_sign=True)
        from fastapi.responses import JSONResponse

        result = await handle_upload_pdf(_FakeRequest(), _pdf_store=store)
        assert isinstance(result, JSONResponse)
        assert result.status_code == 500


class TestHandleUploadImages:
    @pytest.mark.asyncio
    async def test_returns_batch_id_and_signed_urls(self, monkeypatch):
        monkeypatch.setenv("URL_SCAN_PDF_UPLOAD_BUCKET", "test-bucket")
        from src import config as cfg

        cfg._settings_instance = None
        cfg._settings_initialized = False

        store = _FakePdfStore(upload_url="https://storage.example.com/img-signed")
        db = _FakeSession()
        body = UploadImagesRequest(
            images=[
                ImageUploadItem(content_type="image/jpeg", size_bytes=1024),
                ImageUploadItem(content_type="image/png", size_bytes=2048),
            ]
        )
        result = await handle_upload_images(_FakeRequest(), body, db, _pdf_store=store)

        assert hasattr(result, "batch_id")
        assert len(result.images) == 2
        assert result.images[0].ordinal == 0
        assert result.images[1].ordinal == 1
        assert result.images[0].upload_url == "https://storage.example.com/img-signed"

    @pytest.mark.asyncio
    async def test_validates_max_image_count(self, monkeypatch):
        monkeypatch.setenv("URL_SCAN_PDF_UPLOAD_BUCKET", "test-bucket")
        from src import config as cfg

        cfg._settings_instance = None
        cfg._settings_initialized = False

        store = _FakePdfStore()
        db = _FakeSession()
        body = UploadImagesRequest(
            images=[ImageUploadItem(content_type="image/jpeg", size_bytes=100)] * 101
        )
        from fastapi.responses import JSONResponse

        result = await handle_upload_images(_FakeRequest(), body, db, _pdf_store=store)
        assert isinstance(result, JSONResponse)
        assert result.status_code == 400
        data = json.loads(result.body)
        assert data["error_code"] == "image_count_too_large"

    @pytest.mark.asyncio
    async def test_rejects_invalid_image_type(self, monkeypatch):
        monkeypatch.setenv("URL_SCAN_PDF_UPLOAD_BUCKET", "test-bucket")
        from src import config as cfg

        cfg._settings_instance = None
        cfg._settings_initialized = False

        store = _FakePdfStore()
        db = _FakeSession()
        body = UploadImagesRequest(
            images=[ImageUploadItem(content_type="application/pdf", size_bytes=1024)]
        )
        from fastapi.responses import JSONResponse

        result = await handle_upload_images(_FakeRequest(), body, db, _pdf_store=store)
        assert isinstance(result, JSONResponse)
        assert result.status_code == 400
        data = json.loads(result.body)
        assert data["error_code"] == "invalid_image_type"

    @pytest.mark.asyncio
    async def test_persists_batch_to_db(self, monkeypatch):
        monkeypatch.setenv("URL_SCAN_PDF_UPLOAD_BUCKET", "test-bucket")
        from src import config as cfg

        cfg._settings_instance = None
        cfg._settings_initialized = False

        store = _FakePdfStore()
        db = _FakeSession()
        body = UploadImagesRequest(
            images=[ImageUploadItem(content_type="image/png", size_bytes=512)]
        )
        result = await handle_upload_images(_FakeRequest(), body, db, _pdf_store=store)
        assert not isinstance(result, __import__("fastapi").responses.JSONResponse)
        assert len(db.added) == 1
        batch = db.added[0]
        assert isinstance(batch, UrlScanImageUploadBatch)
        assert batch.conversion_status == "awaiting_upload"
        assert len(batch.images) == 1


class TestHandleAnalyzeImages:
    @pytest.mark.asyncio
    async def test_dispatches_conversion_when_images_uploaded(self, monkeypatch):
        monkeypatch.setenv("URL_SCAN_PDF_UPLOAD_BUCKET", "test-bucket")
        from src import config as cfg

        cfg._settings_instance = None
        cfg._settings_initialized = False

        batch_id = uuid4()
        batch = UrlScanImageUploadBatch(
            id=batch_id,
            job_id=batch_id,
            images=[
                {
                    "ordinal": 0,
                    "gcs_key": f"image-uploads/{batch_id}/source/000-abc",
                    "content_type": "image/jpeg",
                    "size_bytes": 1024,
                }
            ],
            conversion_status="awaiting_upload",
            generated_pdf_gcs_key=f"image-uploads/{batch_id}/generated.pdf",
        )

        db = _FakeSession()
        db._objects[batch_id] = batch

        store = _FakePdfStore(metadata={"size": 1024, "content_type": "image/jpeg"})

        dispatched: list[UUID] = []

        async def _fake_dispatch(bid, settings):
            dispatched.append(bid)

        result = await handle_analyze_images(
            _FakeRequest(),
            AnalyzeImagesRequest(batch_id=batch_id),
            db,
            _pdf_store=store,
            _dispatch=_fake_dispatch,
        )

        assert result.status_code == 202
        assert len(dispatched) == 1
        assert dispatched[0] == batch_id

    @pytest.mark.asyncio
    async def test_returns_not_found_for_missing_batch(self, monkeypatch):
        monkeypatch.setenv("URL_SCAN_PDF_UPLOAD_BUCKET", "test-bucket")
        from src import config as cfg

        cfg._settings_instance = None
        cfg._settings_initialized = False

        db = _FakeSession()
        store = _FakePdfStore()
        result = await handle_analyze_images(
            _FakeRequest(),
            AnalyzeImagesRequest(batch_id=uuid4()),
            db,
            _pdf_store=store,
        )
        assert result.status_code == 400
        data = json.loads(result.body)
        assert data["error_code"] == "upload_not_found"

    @pytest.mark.asyncio
    async def test_returns_202_for_already_submitted_batch(self, monkeypatch):
        monkeypatch.setenv("URL_SCAN_PDF_UPLOAD_BUCKET", "test-bucket")
        from src import config as cfg

        cfg._settings_instance = None
        cfg._settings_initialized = False

        batch_id = uuid4()
        batch = UrlScanImageUploadBatch(
            id=batch_id,
            job_id=batch_id,
            images=[],
            conversion_status="submitted",
        )
        db = _FakeSession()
        db._objects[batch_id] = batch
        store = _FakePdfStore()

        result = await handle_analyze_images(
            _FakeRequest(),
            AnalyzeImagesRequest(batch_id=batch_id),
            db,
            _pdf_store=store,
        )
        assert result.status_code == 202


class TestHandleAnalyzePdf:
    @pytest.mark.asyncio
    async def test_rejects_invalid_gcs_key(self, monkeypatch):
        monkeypatch.setenv("URL_SCAN_PDF_UPLOAD_BUCKET", "test-bucket")
        from src import config as cfg

        cfg._settings_instance = None
        cfg._settings_initialized = False

        db = _FakeSession()
        store = _FakePdfStore()
        result = await handle_analyze_pdf(
            _FakeRequest(),
            AnalyzePDFRequest(gcs_key="not-a-uuid"),
            db,
            _pdf_store=store,
        )
        assert result.status_code == 400
        data = json.loads(result.body)
        assert data["error_code"] == "upload_key_invalid"

    @pytest.mark.asyncio
    async def test_rejects_missing_pdf(self, monkeypatch):
        monkeypatch.setenv("URL_SCAN_PDF_UPLOAD_BUCKET", "test-bucket")
        from src import config as cfg

        cfg._settings_instance = None
        cfg._settings_initialized = False

        db = _FakeSession()
        store = _FakePdfStore(metadata=None)
        result = await handle_analyze_pdf(
            _FakeRequest(),
            AnalyzePDFRequest(gcs_key=str(uuid4())),
            db,
            _pdf_store=store,
        )
        assert result.status_code == 400
        data = json.loads(result.body)
        assert data["error_code"] == "upload_not_found"

    @pytest.mark.asyncio
    async def test_rejects_oversized_pdf(self, monkeypatch):
        monkeypatch.setenv("URL_SCAN_PDF_UPLOAD_BUCKET", "test-bucket")
        from src import config as cfg

        cfg._settings_instance = None
        cfg._settings_initialized = False

        db = _FakeSession()
        store = _FakePdfStore(
            metadata={"size": 60 * 1024 * 1024, "content_type": "application/pdf"}
        )
        result = await handle_analyze_pdf(
            _FakeRequest(),
            AnalyzePDFRequest(gcs_key=str(uuid4())),
            db,
            _pdf_store=store,
        )
        assert result.status_code == 400
        data = json.loads(result.body)
        assert data["error_code"] == "pdf_too_large"

    @pytest.mark.asyncio
    async def test_dispatches_url_scan_for_valid_pdf(self, monkeypatch):
        monkeypatch.setenv("URL_SCAN_PDF_UPLOAD_BUCKET", "test-bucket")
        from src import config as cfg

        cfg._settings_instance = None
        cfg._settings_initialized = False

        dispatched: list = []

        async def _fake_dispatch(job_id, source_url, normalized_url, attempt_id):
            dispatched.append((job_id, source_url, normalized_url, attempt_id))
            return f"wf-{job_id}"

        gcs_key = str(uuid4())
        store = _FakePdfStore(metadata={"size": 1024 * 1024, "content_type": "application/pdf"})

        from tests.unit.url_content_scan.test_analyze_handler import (
            _FakeResult,
        )
        from tests.unit.url_content_scan.test_analyze_handler import (
            _FakeSession as _FullFakeSession,
        )

        class _SessionWithLock(_FullFakeSession):
            async def execute(self, stmt, params=None):
                sql = str(stmt)
                if "pg_try_advisory_xact_lock" in sql:
                    return _FakeResult(True)
                return await super().execute(stmt, params)

        db = _SessionWithLock()
        result = await handle_analyze_pdf(
            _FakeRequest(),
            AnalyzePDFRequest(gcs_key=gcs_key),
            db,
            _pdf_store=store,
            _dispatch=_fake_dispatch,
        )
        assert result.status_code == 202
        assert len(dispatched) == 1
        _job_id, _source_url, normalized_url, _attempt_id = dispatched[0]
        assert "gcs-pdf" in normalized_url
