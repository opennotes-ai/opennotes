"""Image conversion behavior with fake database, storage, and durable-step boundaries."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager, nullcontext
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call
from uuid import UUID

import pytest

pytestmark = pytest.mark.unit

BATCH_ID = "00000000-0000-0000-0000-000000000123"
BUCKET = "synthetic-image-bucket"


@pytest.fixture
def workflow_steps(monkeypatch):
    module = import_module("src.dbos_workflows.url_scan_convert_images_workflow")
    steps = MagicMock()
    defaults = {
        "read_image_batch_step": {
            "conversion_status": "submitted",
            "generated_pdf_gcs_key": None,
            "images": [{"ordinal": 0, "gcs_key": "synthetic/source.png"}],
        },
        "mark_converting_step": True,
        "download_images_step": [b"synthetic-image"],
        "convert_images_to_pdf_step": b"%PDF-synthetic",
        "upload_pdf_step": None,
        "mark_converted_step": None,
        "extract_pdf_content_step": {
            "text": "Extracted page",
            "page_count": 2,
            "metadata": {"Title": "Example"},
        },
        "create_pdf_archive_row_step": None,
        "dispatch_url_scan_for_pdf_step": "synthetic-workflow-id",
        "mark_failed_step": None,
    }
    for name, result in defaults.items():
        step = getattr(steps, name)
        step.return_value = result
        monkeypatch.setattr(module, name, step)
    return module, steps


@pytest.mark.parametrize("existing_key", [None, "synthetic/existing.pdf"])
def test_workflow_orders_conversion_archive_and_dispatch(workflow_steps, existing_key):
    module, steps = workflow_steps
    batch = steps.read_image_batch_step.return_value
    batch["generated_pdf_gcs_key"] = existing_key
    if existing_key:
        steps.extract_pdf_content_step.return_value = {}
    key = existing_key or f"image-uploads/{BATCH_ID}/generated.pdf"

    module.image_conversion_workflow.__wrapped__(BATCH_ID, BUCKET)

    assert steps.mock_calls == [
        call.read_image_batch_step(BATCH_ID),
        call.mark_converting_step(BATCH_ID),
        call.download_images_step(batch["images"], BUCKET),
        call.convert_images_to_pdf_step([b"synthetic-image"]),
        call.upload_pdf_step(b"%PDF-synthetic", key, BUCKET),
        call.mark_converted_step(BATCH_ID, key),
        call.extract_pdf_content_step(b"%PDF-synthetic"),
        call.create_pdf_archive_row_step(
            BATCH_ID,
            "" if existing_key else "Extracted page",
            page_count=None if existing_key else 2,
            extracted_metadata=None if existing_key else {"Title": "Example"},
        ),
        call.dispatch_url_scan_for_pdf_step(BATCH_ID, f"gcs-pdf://{key}", BATCH_ID),
    ]


@pytest.mark.parametrize("reason", ["missing", "converted", "unclaimed"])
def test_workflow_stops_without_side_effects_for_unavailable_batch(workflow_steps, reason):
    module, steps = workflow_steps
    if reason == "missing":
        steps.read_image_batch_step.return_value = None
    elif reason == "converted":
        steps.read_image_batch_step.return_value["conversion_status"] = "converted"
    else:
        steps.mark_converting_step.return_value = False

    module.image_conversion_workflow.__wrapped__(BATCH_ID, BUCKET)

    expected = [call.read_image_batch_step(BATCH_ID)]
    if reason == "unclaimed":
        expected.append(call.mark_converting_step(BATCH_ID))
    assert steps.mock_calls == expected


@pytest.mark.parametrize(
    ("failed_step", "error_code", "message"),
    [
        ("download_images_step", "upload_not_found", "source image missing: synthetic failure"),
        (
            "convert_images_to_pdf_step",
            "image_conversion_failed",
            "conversion failed: synthetic failure",
        ),
        ("upload_pdf_step", None, None),
    ],
)
def test_workflow_distinguishes_terminal_input_errors_from_retryable_upload(
    workflow_steps, failed_step, error_code, message, caplog
):
    module, steps = workflow_steps
    getattr(steps, failed_step).side_effect = RuntimeError("synthetic failure")

    module.image_conversion_workflow.__wrapped__(BATCH_ID, BUCKET)

    if error_code:
        steps.mark_failed_step.assert_called_once_with(BATCH_ID, error_code, message)
    else:
        steps.mark_failed_step.assert_not_called()
        assert "PDF upload failed" in caplog.text
    steps.mark_converted_step.assert_not_called()
    steps.extract_pdf_content_step.assert_not_called()
    steps.create_pdf_archive_row_step.assert_not_called()
    steps.dispatch_url_scan_for_pdf_step.assert_not_called()
    if failed_step == "download_images_step":
        steps.convert_images_to_pdf_step.assert_not_called()
    if failed_step != "upload_pdf_step":
        steps.upload_pdf_step.assert_not_called()


class _Session:
    def __init__(self):
        self.row = None
        self.added = []
        self.lookups = []

    async def get(self, model, key):
        self.lookups.append((model, key))
        return self.row

    @asynccontextmanager
    async def begin(self):
        yield self

    def add(self, row):
        self.added.append(row)


@pytest.fixture
def batch_session(monkeypatch):
    session = _Session()

    @asynccontextmanager
    async def maker():
        yield session

    monkeypatch.setattr("src.database.get_session_maker", lambda: maker)
    return session


@pytest.mark.parametrize("encoded", [False, True])
def test_read_step_loads_stored_images_and_preserves_batch_state(batch_session, encoded):
    module = import_module("src.dbos_workflows.url_scan_convert_images_workflow")
    images = [{"ordinal": 0, "gcs_key": "synthetic/source.png"}]
    batch_session.row = SimpleNamespace(
        images=json.dumps(images) if encoded else images,
        generated_pdf_gcs_key="synthetic/previous.pdf",
        conversion_status="converting",
    )

    result = module.read_image_batch_step(BATCH_ID)

    assert result == {
        "batch_id": BATCH_ID,
        "images": images,
        "generated_pdf_gcs_key": "synthetic/previous.pdf",
        "conversion_status": "converting",
    }
    assert batch_session.lookups[0][1] == UUID(BATCH_ID)


def test_read_step_returns_none_for_missing_batch(batch_session):
    module = import_module("src.dbos_workflows.url_scan_convert_images_workflow")

    assert module.read_image_batch_step(BATCH_ID) is None


@pytest.mark.parametrize("transition", ["converting", "converted", "failed"])
def test_status_steps_persist_conversion_outcomes(batch_session, transition):
    module = import_module("src.dbos_workflows.url_scan_convert_images_workflow")
    row = SimpleNamespace(
        conversion_status="submitted",
        generated_pdf_gcs_key=None,
        error_code=None,
        error_message=None,
    )
    batch_session.row = row

    if transition == "converting":
        assert module.mark_converting_step(BATCH_ID) is True
    elif transition == "converted":
        module.mark_converted_step(BATCH_ID, "synthetic/generated.pdf")
        assert row.generated_pdf_gcs_key == "synthetic/generated.pdf"
    else:
        module.mark_failed_step(BATCH_ID, "upload_not_found", "synthetic image missing")
        assert (row.error_code, row.error_message) == (
            "upload_not_found",
            "synthetic image missing",
        )

    assert row.conversion_status == transition
    assert batch_session.added == []


def test_status_steps_do_not_create_missing_batches(batch_session):
    module = import_module("src.dbos_workflows.url_scan_convert_images_workflow")

    assert module.mark_converting_step(BATCH_ID) is False
    module.mark_converted_step(BATCH_ID, "synthetic/generated.pdf")
    module.mark_failed_step(BATCH_ID, "upload_not_found", "synthetic missing")

    assert batch_session.added == []


def test_archive_step_persists_extraction_metadata(batch_session):
    module = import_module("src.dbos_workflows.url_scan_convert_images_workflow")

    module.create_pdf_archive_row_step(
        BATCH_ID, "Extracted text", page_count=3, extracted_metadata={"Title": "Synthetic"}
    )

    assert len(batch_session.added) == 1
    archive = batch_session.added[0]
    assert (archive.job_id, archive.html, archive.page_count) == (
        UUID(BATCH_ID),
        "Extracted text",
        3,
    )
    assert archive.extracted_metadata == {"Title": "Synthetic"}
    assert archive.expires_at is not None


def test_upload_step_uses_requested_bucket_key_and_pdf_content_type(monkeypatch):
    module = import_module("src.dbos_workflows.url_scan_convert_images_workflow")
    store = SimpleNamespace(write_bytes=AsyncMock())
    constructor = MagicMock(return_value=store)
    monkeypatch.setattr("src.url_content_scan.pdf_upload_store.PdfUploadStore", constructor)

    module.upload_pdf_step(b"%PDF-synthetic", "synthetic/generated.pdf", BUCKET)

    constructor.assert_called_once_with(bucket_name=BUCKET)
    store.write_bytes.assert_awaited_once_with(
        "synthetic/generated.pdf", b"%PDF-synthetic", content_type="application/pdf"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("use_settings", [False, True])
async def test_dispatch_executes_deduplicated_enqueue_and_returns_handle(monkeypatch, use_settings):
    module = import_module("src.dbos_workflows.url_scan_convert_images_workflow")
    from src.config import get_settings

    cfg = get_settings()
    monkeypatch.setattr(cfg, "URL_SCAN_PDF_UPLOAD_BUCKET", BUCKET)
    handle = "fallback-handle" if use_settings else SimpleNamespace(workflow_id="queued-id")
    queue = MagicMock()
    queue.enqueue.return_value = handle
    monkeypatch.setattr(module, "image_conversion_queue", queue)
    workflow_context = MagicMock(side_effect=lambda *args, **kwargs: nullcontext())
    enqueue_context = MagicMock(side_effect=lambda *args, **kwargs: nullcontext())
    monkeypatch.setattr(module, "SetWorkflowID", workflow_context)
    monkeypatch.setattr(module, "SetEnqueueOptions", enqueue_context)

    async def enqueue(callback):
        return callback()

    safe_enqueue = AsyncMock(side_effect=enqueue)
    monkeypatch.setattr(module, "safe_enqueue", safe_enqueue)

    result = await module.dispatch_image_conversion_workflow(
        UUID(BATCH_ID), cfg if use_settings else BUCKET
    )

    assert result == ("fallback-handle" if use_settings else "queued-id")
    safe_enqueue.assert_awaited_once()
    workflow_id = f"image-conversion-{BATCH_ID}"
    workflow_context.assert_called_once_with(workflow_id)
    enqueue_context.assert_called_once_with(deduplication_id=workflow_id)
    queue.enqueue.assert_called_once_with(module.image_conversion_workflow, BATCH_ID, BUCKET)
