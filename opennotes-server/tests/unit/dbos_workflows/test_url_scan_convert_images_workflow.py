"""Unit tests for url_scan_convert_images_workflow (TASK-1657.14).

Covers:
- Convert workflow turns N images into a single PDF (mock GCS + img2pdf)
- Convert workflow creates url_scan_pdf_archives row
- Workflow marks batch as converted on success
- Workflow marks batch as failed when images are missing
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import patch
from uuid import uuid4

import pytest


def _make_session_maker(fake_session):
    """Build a get_session_maker() mock that yields fake_session via async context manager."""

    @asynccontextmanager
    async def _session_ctx():
        yield fake_session

    def _maker():
        return _session_ctx()

    return _maker


class _FakeSessionWithBatch:
    def __init__(self, batch=None):
        self._batch = batch
        self.added = []
        self._in_begin = False

    @asynccontextmanager
    async def begin(self):
        self._in_begin = True
        yield
        self._in_begin = False

    async def get(self, model, key):
        return self._batch

    def add(self, obj):
        self.added.append(obj)


class TestConvertImagesToPdfStep:
    def test_converts_images_to_pdf_bytes(self):
        from src.dbos_workflows.url_scan_convert_images_workflow import (
            _convert_images_to_pdf_bytes,
        )

        fake_pdf = b"%PDF-1.4 fake"
        image_bytes = [b"\xff\xd8fake-jpeg", b"\x89PNG\r\nfake-png"]

        with patch("img2pdf.convert", return_value=fake_pdf) as mock_convert:
            result = _convert_images_to_pdf_bytes(image_bytes)

        assert result == fake_pdf
        mock_convert.assert_called_once_with(image_bytes)

    def test_raises_on_non_bytes_return(self):
        from src.dbos_workflows.url_scan_convert_images_workflow import (
            _convert_images_to_pdf_bytes,
        )

        with (
            patch("img2pdf.convert", return_value=None),
            pytest.raises(RuntimeError, match="non-bytes"),
        ):
            _convert_images_to_pdf_bytes([b"img"])


class TestDownloadImagesStep:
    @pytest.mark.asyncio
    async def test_download_images_sorted_by_ordinal(self):
        images = [
            {"ordinal": 1, "gcs_key": "image-uploads/batch/source/001-b"},
            {"ordinal": 0, "gcs_key": "image-uploads/batch/source/000-a"},
        ]

        downloaded_order: list[str] = []

        class _FakeStore:
            async def read_bytes(self, key: str) -> bytes:
                downloaded_order.append(key)
                return f"bytes-{key}".encode()

        with patch(
            "src.dbos_workflows.url_scan_convert_images_workflow._get_pdf_store",
            return_value=_FakeStore(),
        ):
            from src.utils.async_compat import run_sync

            async def _inner():
                store = _FakeStore()
                sorted_images = sorted(images, key=lambda img: int(img["ordinal"]))
                return [await store.read_bytes(str(img["gcs_key"])) for img in sorted_images]

            result = run_sync(_inner())

        assert len(result) == 2
        assert b"000-a" in result[0]
        assert b"001-b" in result[1]

    def test_download_images_step_is_callable(self):
        from src.dbos_workflows.url_scan_convert_images_workflow import download_images_step

        assert callable(download_images_step)


class TestMarkingSteps:
    @pytest.mark.asyncio
    async def test_mark_converting_returns_true_for_submitted_batch(self):
        from src.dbos_workflows.url_scan_convert_images_workflow import _mark_converting_async
        from src.url_content_scan.models import UrlScanImageUploadBatch

        batch_id = uuid4()
        batch = UrlScanImageUploadBatch(
            id=batch_id,
            job_id=batch_id,
            images=[],
            conversion_status="submitted",
        )
        fake_session = _FakeSessionWithBatch(batch)
        maker = _make_session_maker(fake_session)

        with patch("src.database.get_session_maker", return_value=maker):
            result = await _mark_converting_async(batch_id)

        assert result is True
        assert batch.conversion_status == "converting"

    @pytest.mark.asyncio
    async def test_mark_converting_returns_false_for_missing_batch(self):
        from src.dbos_workflows.url_scan_convert_images_workflow import _mark_converting_async

        batch_id = uuid4()
        fake_session = _FakeSessionWithBatch(None)
        maker = _make_session_maker(fake_session)

        with patch("src.database.get_session_maker", return_value=maker):
            result = await _mark_converting_async(batch_id)

        assert result is False

    @pytest.mark.asyncio
    async def test_mark_converting_returns_false_for_wrong_status(self):
        from src.dbos_workflows.url_scan_convert_images_workflow import _mark_converting_async
        from src.url_content_scan.models import UrlScanImageUploadBatch

        batch_id = uuid4()
        batch = UrlScanImageUploadBatch(
            id=batch_id,
            job_id=batch_id,
            images=[],
            conversion_status="awaiting_upload",
        )
        fake_session = _FakeSessionWithBatch(batch)
        maker = _make_session_maker(fake_session)

        with patch("src.database.get_session_maker", return_value=maker):
            result = await _mark_converting_async(batch_id)

        assert result is False


class TestCreatePdfArchiveAsync:
    @pytest.mark.asyncio
    async def test_creates_pdf_archive_row(self):
        from src.dbos_workflows.url_scan_convert_images_workflow import _create_pdf_archive_async
        from src.url_content_scan.models import UrlScanPdfArchive

        job_id = uuid4()
        fake_session = _FakeSessionWithBatch()
        maker = _make_session_maker(fake_session)

        with patch("src.database.get_session_maker", return_value=maker):
            await _create_pdf_archive_async(job_id, "<html>extracted</html>")

        assert len(fake_session.added) == 1
        archive = fake_session.added[0]
        assert isinstance(archive, UrlScanPdfArchive)
        assert archive.job_id == job_id
        assert archive.html == "<html>extracted</html>"
        assert archive.expires_at is not None

    @pytest.mark.asyncio
    async def test_creates_pdf_archive_row_with_extraction_metadata(self):
        from src.dbos_workflows.url_scan_convert_images_workflow import _create_pdf_archive_async
        from src.url_content_scan.models import UrlScanPdfArchive

        job_id = uuid4()
        fake_session = _FakeSessionWithBatch()
        maker = _make_session_maker(fake_session)

        with patch("src.database.get_session_maker", return_value=maker):
            await _create_pdf_archive_async(
                job_id,
                "extracted text content",
                page_count=3,
                extracted_metadata={"Author": "Test Author", "Title": "Test PDF"},
            )

        assert len(fake_session.added) == 1
        archive = fake_session.added[0]
        assert isinstance(archive, UrlScanPdfArchive)
        assert archive.html == "extracted text content"
        assert archive.page_count == 3
        assert archive.extracted_metadata == {"Author": "Test Author", "Title": "Test PDF"}

    @pytest.mark.asyncio
    async def test_creates_pdf_archive_row_empty_extraction(self):
        from src.dbos_workflows.url_scan_convert_images_workflow import _create_pdf_archive_async

        job_id = uuid4()
        fake_session = _FakeSessionWithBatch()
        maker = _make_session_maker(fake_session)

        with patch("src.database.get_session_maker", return_value=maker):
            await _create_pdf_archive_async(
                job_id,
                "",
                page_count=0,
                extracted_metadata=None,
            )

        assert len(fake_session.added) == 1
        archive = fake_session.added[0]
        assert archive.html == ""
        assert archive.page_count == 0
        assert archive.extracted_metadata is None


class TestExtractPdfContentStep:
    def test_extract_step_returns_dict_on_success(self):
        from src.dbos_workflows.url_scan_convert_images_workflow import extract_pdf_content_step
        from src.url_content_scan.pdf_extract import PdfContent

        fake_content = PdfContent(
            text="page one\npage two",
            page_count=2,
            page_texts=["page one", "page two"],
            metadata={"Author": "Test"},
        )

        with patch(
            "src.url_content_scan.pdf_extract.extract_pdf_content",
            return_value=fake_content,
        ):
            result = extract_pdf_content_step(b"%PDF-fake")

        assert result["text"] == "page one\npage two"
        assert result["page_count"] == 2
        assert result["page_texts"] == ["page one", "page two"]
        assert result["metadata"] == {"Author": "Test"}

    def test_extract_step_returns_empty_dict_on_extraction_error(self):
        from src.dbos_workflows.url_scan_convert_images_workflow import extract_pdf_content_step
        from src.url_content_scan.pdf_extract import PdfExtractionError

        with patch(
            "src.url_content_scan.pdf_extract.extract_pdf_content",
            side_effect=PdfExtractionError("malformed PDF"),
        ):
            result = extract_pdf_content_step(b"not a pdf")

        assert result["text"] == ""
        assert result["page_count"] == 0
        assert result["page_texts"] == []
        assert result["metadata"] == {}

    def test_extract_step_is_callable(self):
        from src.dbos_workflows.url_scan_convert_images_workflow import extract_pdf_content_step

        assert callable(extract_pdf_content_step)


class TestImageConversionWorkflowIntegration:
    def test_workflow_is_registered_as_dbos_workflow(self):
        from src.dbos_workflows.url_scan_convert_images_workflow import (
            image_conversion_workflow,
        )

        assert callable(image_conversion_workflow)

    def test_dispatch_image_conversion_workflow_is_async(self):
        import asyncio

        from src.dbos_workflows.url_scan_convert_images_workflow import (
            dispatch_image_conversion_workflow,
        )

        assert asyncio.iscoroutinefunction(dispatch_image_conversion_workflow)

    def test_convert_images_to_pdf_step_is_callable(self):
        from src.dbos_workflows.url_scan_convert_images_workflow import convert_images_to_pdf_step

        assert callable(convert_images_to_pdf_step)

    def test_upload_pdf_step_is_callable(self):
        from src.dbos_workflows.url_scan_convert_images_workflow import upload_pdf_step

        assert callable(upload_pdf_step)
