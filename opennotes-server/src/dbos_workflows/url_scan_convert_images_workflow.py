"""DBOS durable workflow: convert image batch to PDF and trigger url_scan.

Ports vibecheck-server PR525 / TASK-1590 image conversion pipeline.

Workflow steps:
1. read_image_batch_step        — load image records from DB, return GCS keys
2. download_images_step         — download each source image from GCS
3. convert_images_to_pdf_step   — combine images into a single PDF via img2pdf
4. upload_pdf_step              — write generated PDF to GCS staging bucket
5. create_pdf_archive_row_step  — insert url_scan_pdf_archives row
6. dispatch_url_scan_step       — enqueue standard url_scan workflow on PDF URL

Each step is checkpointed independently; crashes after any step will resume
from the next step on retry rather than repeating side effects.

The caller (analyze_images handler) must have already set
``conversion_status = 'submitted'`` on the UrlScanImageUploadBatch row
before enqueuing this workflow.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from dbos import DBOS, Queue, SetEnqueueOptions, SetWorkflowID

from src.dbos_workflows.enqueue_utils import safe_enqueue
from src.monitoring import get_logger
from src.utils.async_compat import run_sync

logger = get_logger(__name__)

image_conversion_queue = Queue(
    name="url_scan_image_conversion",
    worker_concurrency=2,
    concurrency=4,
)


def _convert_images_to_pdf_bytes(image_bytes_list: list[bytes]) -> bytes:
    import img2pdf

    result = img2pdf.convert(image_bytes_list)
    if not isinstance(result, bytes):
        raise RuntimeError("img2pdf returned non-bytes result")
    return result


def _get_pdf_store(bucket_name: str):
    from src.url_content_scan.pdf_upload_store import PdfUploadStore

    return PdfUploadStore(bucket_name=bucket_name)


async def _load_batch_async(batch_id: UUID) -> dict[str, Any] | None:
    from src.database import get_session_maker
    from src.url_content_scan.models import UrlScanImageUploadBatch

    async with get_session_maker()() as session:
        batch = await session.get(UrlScanImageUploadBatch, batch_id)
        if batch is None:
            return None
        images = batch.images if isinstance(batch.images, list) else json.loads(batch.images)
        return {
            "batch_id": str(batch_id),
            "images": images,
            "generated_pdf_gcs_key": batch.generated_pdf_gcs_key,
            "conversion_status": batch.conversion_status,
        }


async def _mark_converting_async(batch_id: UUID) -> bool:
    from src.database import get_session_maker
    from src.url_content_scan.models import UrlScanImageUploadBatch

    async with get_session_maker()() as session, session.begin():
        batch = await session.get(UrlScanImageUploadBatch, batch_id)
        if batch is None:
            return False
        if batch.conversion_status not in {"submitted", "converting"}:
            return False
        batch.conversion_status = "converting"
        return True


async def _mark_converted_async(batch_id: UUID, generated_pdf_key: str) -> None:
    from src.database import get_session_maker
    from src.url_content_scan.models import UrlScanImageUploadBatch

    async with get_session_maker()() as session, session.begin():
        batch = await session.get(UrlScanImageUploadBatch, batch_id)
        if batch is not None:
            batch.conversion_status = "converted"
            batch.generated_pdf_gcs_key = generated_pdf_key


async def _mark_failed_async(batch_id: UUID, error_code: str, error_message: str) -> None:
    from src.database import get_session_maker
    from src.url_content_scan.models import UrlScanImageUploadBatch

    async with get_session_maker()() as session, session.begin():
        batch = await session.get(UrlScanImageUploadBatch, batch_id)
        if batch is not None:
            batch.conversion_status = "failed"
            batch.error_code = error_code
            batch.error_message = error_message


async def _create_pdf_archive_async(
    job_id: UUID,
    html: str,
    *,
    page_count: int | None = None,
    extracted_metadata: dict[str, object] | None = None,
    expires_days: int = 60,
) -> None:
    import pendulum

    from src.database import get_session_maker
    from src.url_content_scan.models import UrlScanPdfArchive

    expires_at = pendulum.now("UTC").add(days=expires_days)
    async with get_session_maker()() as session, session.begin():
        archive = UrlScanPdfArchive(
            job_id=job_id,
            html=html,
            page_count=page_count,
            extracted_metadata=extracted_metadata,
            expires_at=expires_at,
        )
        session.add(archive)


@DBOS.step()
def read_image_batch_step(batch_id: str) -> dict[str, Any] | None:
    return run_sync(_load_batch_async(UUID(batch_id)))


@DBOS.step()
def mark_converting_step(batch_id: str) -> bool:
    return run_sync(_mark_converting_async(UUID(batch_id)))


@DBOS.step()
def download_images_step(images: list[dict], bucket_name: str) -> list[bytes]:
    async def _download() -> list[bytes]:
        store = _get_pdf_store(bucket_name)
        sorted_images = sorted(images, key=lambda img: int(img["ordinal"]))
        return [await store.read_bytes(str(img["gcs_key"])) for img in sorted_images]

    return run_sync(_download())


@DBOS.step()
def convert_images_to_pdf_step(image_bytes_list: list[bytes]) -> bytes:
    return _convert_images_to_pdf_bytes(image_bytes_list)


@DBOS.step()
def upload_pdf_step(pdf_bytes: bytes, gcs_key: str, bucket_name: str) -> None:
    async def _upload() -> None:
        store = _get_pdf_store(bucket_name)
        await store.write_bytes(gcs_key, pdf_bytes, content_type="application/pdf")

    run_sync(_upload())


@DBOS.step()
def mark_converted_step(batch_id: str, generated_pdf_key: str) -> None:
    run_sync(_mark_converted_async(UUID(batch_id), generated_pdf_key))


@DBOS.step()
def mark_failed_step(batch_id: str, error_code: str, error_message: str) -> None:
    run_sync(_mark_failed_async(UUID(batch_id), error_code, error_message))


@DBOS.step()
def extract_pdf_content_step(pdf_bytes: bytes) -> dict[str, object]:
    from src.url_content_scan.pdf_extract import PdfExtractionError, extract_pdf_content

    try:
        content = extract_pdf_content(pdf_bytes)
    except PdfExtractionError as exc:
        logger.warning("pdf_extract_step: extraction failed: %s", exc)
        return {"text": "", "page_count": 0, "page_texts": [], "metadata": {}}
    return {
        "text": content.text,
        "page_count": content.page_count,
        "page_texts": content.page_texts,
        "metadata": content.metadata,
    }


@DBOS.step()
def create_pdf_archive_row_step(
    job_id: str,
    html: str,
    page_count: int | None = None,
    extracted_metadata: dict[str, object] | None = None,
) -> None:
    run_sync(
        _create_pdf_archive_async(
            UUID(job_id),
            html,
            page_count=page_count,
            extracted_metadata=extracted_metadata,
        )
    )


@DBOS.step()
def dispatch_url_scan_for_pdf_step(job_id: str, pdf_gcs_url: str, batch_id: str) -> str | None:
    async def _dispatch() -> str | None:
        from src.database import get_session_maker
        from src.dbos_workflows.url_scan_workflow import dispatch_url_scan_workflow
        from src.url_content_scan.analyze_handler import _insert_pending_job

        normalized_url = pdf_gcs_url
        source_url = pdf_gcs_url
        host = "gcs-pdf"

        async with get_session_maker()() as session, session.begin():
            new_job_id, attempt_id = await _insert_pending_job(
                session,
                source_url=source_url,
                normalized_url=normalized_url,
                host=host,
                api_key_id=None,
            )

        return await dispatch_url_scan_workflow(new_job_id, source_url, normalized_url, attempt_id)

    return run_sync(_dispatch())


@DBOS.workflow()
def image_conversion_workflow(batch_id: str, bucket_name: str) -> None:
    batch_data = read_image_batch_step(batch_id)
    if batch_data is None:
        logger.warning("image_conversion_workflow: batch not found batch_id=%s", batch_id)
        return

    if batch_data.get("conversion_status") == "converted":
        logger.info("image_conversion_workflow: already converted batch_id=%s", batch_id)
        return

    ok = mark_converting_step(batch_id)
    if not ok:
        logger.warning(
            "image_conversion_workflow: failed to claim batch batch_id=%s status=%s",
            batch_id,
            batch_data.get("conversion_status"),
        )
        return

    generated_pdf_key = batch_data.get("generated_pdf_gcs_key") or (
        f"image-uploads/{batch_id}/generated.pdf"
    )

    try:
        image_bytes_list = download_images_step(batch_data["images"], bucket_name)
    except Exception as exc:
        mark_failed_step(batch_id, "upload_not_found", f"source image missing: {exc}")
        return

    try:
        pdf_bytes = convert_images_to_pdf_step(image_bytes_list)
    except Exception as exc:
        mark_failed_step(batch_id, "image_conversion_failed", f"conversion failed: {exc}")
        return

    try:
        upload_pdf_step(pdf_bytes, generated_pdf_key, bucket_name)
    except Exception as exc:
        logger.warning(
            "image_conversion_workflow: PDF upload failed batch_id=%s: %s", batch_id, exc
        )
        return

    mark_converted_step(batch_id, generated_pdf_key)

    extraction = extract_pdf_content_step(pdf_bytes)
    extracted_text = str(extraction.get("text") or "")
    extracted_page_count_val = extraction.get("page_count")
    extracted_meta = dict(extraction.get("metadata") or {})

    page_count_int: int | None = (
        int(extracted_page_count_val) if extracted_page_count_val is not None else None
    )

    create_pdf_archive_row_step(
        str(batch_id),
        extracted_text,
        page_count=page_count_int,
        extracted_metadata=extracted_meta if extracted_meta else None,
    )

    pdf_gcs_url = f"gcs-pdf://{generated_pdf_key}"
    dispatch_url_scan_for_pdf_step(str(batch_id), pdf_gcs_url, batch_id)


async def dispatch_image_conversion_workflow(batch_id: UUID, settings: Any) -> str | None:
    from src.config import Settings

    bucket_name = (
        settings.URL_SCAN_PDF_UPLOAD_BUCKET if isinstance(settings, Settings) else str(settings)
    )

    workflow_id = f"image-conversion-{batch_id}"

    def _enqueue() -> Any:
        with SetWorkflowID(workflow_id), SetEnqueueOptions(deduplication_id=workflow_id):
            return image_conversion_queue.enqueue(
                image_conversion_workflow,
                str(batch_id),
                bucket_name,
            )

    handle = await safe_enqueue(_enqueue)
    dispatched_id = getattr(handle, "workflow_id", None) or str(handle)
    return str(dispatched_id)
