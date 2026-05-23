"""Handler functions for PDF and image upload endpoints.

Ports vibecheck-server PR525 / TASK-1590 into opennotes-server.

Four endpoints:
- POST /upload-pdf   — returns a GCS signed URL for direct browser upload
- POST /analyze-pdf  — validates an uploaded PDF and enqueues url_scan workflow
- POST /upload-images — creates a pending image batch and returns signed PUT URLs
- POST /analyze-images — validates uploaded images and dispatches conversion workflow

The image-to-PDF conversion happens in a DBOS workflow
(src/dbos_workflows/url_scan_convert_images_workflow.py) that is
enqueued by dispatch_image_conversion_workflow().
"""

from __future__ import annotations

import asyncio
import json
from uuid import UUID, uuid4

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import get_settings
from src.url_content_scan.analyze_handler import (
    _insert_pending_job,
    _mark_dispatch_failure,
    _try_advisory_lock,
)
from src.url_content_scan.models import UrlScanImageUploadBatch
from src.url_content_scan.schemas import AnalyzeResponse, JobStatus

_MAX_PDF_BYTES = 50 * 1024 * 1024
_MAX_IMAGE_BATCH_BYTES = 45 * 1024 * 1024
_MAX_IMAGE_COUNT = 100
_LOCK_RETRY_DELAY_SECONDS = 1.0
_ALLOWED_IMAGE_TYPES = frozenset(
    {
        "image/jpeg",
        "image/png",
        "image/tiff",
        "image/bmp",
    }
)


class UploadPDFResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    gcs_key: str
    upload_url: str


class AnalyzePDFRequest(BaseModel):
    gcs_key: str
    filename: str | None = None


class ImageUploadItem(BaseModel):
    filename: str | None = None
    content_type: str
    size_bytes: int = Field(ge=0)

    @field_validator("content_type")
    @classmethod
    def _normalize_content_type(cls, value: str) -> str:
        return value.lower().split(";", 1)[0].strip()


class UploadImagesRequest(BaseModel):
    images: list[ImageUploadItem] = Field(min_length=1)


class ImageUploadUrl(BaseModel):
    ordinal: int
    gcs_key: str
    upload_url: str


class UploadImagesResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    batch_id: UUID
    images: list[ImageUploadUrl]


class AnalyzeImagesRequest(BaseModel):
    batch_id: UUID


def _validation_error(error_code: str, message: str, status_code: int = 400) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error_code": error_code, "message": message},
    )


def _internal_error(message: str) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={"error_code": "internal", "message": message},
    )


def _image_gcs_key(batch_id: UUID, ordinal: int) -> str:
    return f"image-uploads/{batch_id}/source/{ordinal:03d}-{uuid4()}"


def _generated_pdf_gcs_key(batch_id: UUID) -> str:
    return f"image-uploads/{batch_id}/generated.pdf"


def _validate_image_request(images: list[ImageUploadItem]) -> JSONResponse | None:
    if len(images) > _MAX_IMAGE_COUNT:
        return _validation_error(
            "image_count_too_large",
            "image batch cannot contain more than 100 images",
        )
    aggregate_size = sum(img.size_bytes for img in images)
    if aggregate_size > _MAX_IMAGE_BATCH_BYTES:
        return _validation_error("image_aggregate_too_large", "image batch too large")
    bad_type = next(
        (img.content_type for img in images if img.content_type not in _ALLOWED_IMAGE_TYPES),
        None,
    )
    if bad_type is not None:
        return _validation_error(
            "invalid_image_type",
            f"unsupported image content type: {bad_type}",
        )
    return None


def _get_pdf_store(bucket_name: str):
    from src.url_content_scan.pdf_upload_store import PdfUploadStore  # noqa: PLC0415

    return PdfUploadStore(bucket_name=bucket_name)


async def handle_upload_pdf(
    request: Request,
    *,
    _pdf_store=None,
) -> UploadPDFResponse | JSONResponse:
    settings = get_settings()
    if not settings.URL_SCAN_PDF_UPLOAD_BUCKET:
        return _internal_error("PDF upload bucket is not configured")

    gcs_key = str(uuid4())
    try:
        store = _pdf_store or _get_pdf_store(settings.URL_SCAN_PDF_UPLOAD_BUCKET)
        upload_url = await store.signed_upload_url(gcs_key, ttl_seconds=900)
    except Exception:
        return _internal_error("PDF upload URL signing failed")
    if not upload_url:
        return _internal_error("PDF upload URL signing failed")

    return UploadPDFResponse(gcs_key=gcs_key, upload_url=upload_url)


async def handle_upload_images(
    request: Request,
    body: UploadImagesRequest,
    db: AsyncSession,
    *,
    _pdf_store=None,
) -> UploadImagesResponse | JSONResponse:
    validation_error = _validate_image_request(body.images)
    if validation_error is not None:
        return validation_error

    settings = get_settings()
    if not settings.URL_SCAN_PDF_UPLOAD_BUCKET:
        return _internal_error("PDF upload bucket is not configured")

    batch_id = uuid4()
    image_records: list[dict] = []
    upload_urls: list[ImageUploadUrl] = []

    try:
        store = _pdf_store or _get_pdf_store(settings.URL_SCAN_PDF_UPLOAD_BUCKET)
        for ordinal, img in enumerate(body.images):
            key = _image_gcs_key(batch_id, ordinal)
            upload_url = await store.signed_upload_url(
                key,
                ttl_seconds=900,
                content_type=img.content_type,
            )
            if not upload_url:
                return _internal_error("Image upload URL signing failed")
            image_records.append(
                {
                    "ordinal": ordinal,
                    "gcs_key": key,
                    "content_type": img.content_type,
                    "size_bytes": img.size_bytes,
                    "filename": img.filename,
                }
            )
            upload_urls.append(ImageUploadUrl(ordinal=ordinal, gcs_key=key, upload_url=upload_url))
    except Exception:
        return _internal_error("Image upload URL signing failed")

    generated_pdf_key = _generated_pdf_gcs_key(batch_id)
    batch = UrlScanImageUploadBatch(
        id=batch_id,
        job_id=batch_id,
        images=image_records,
        conversion_status="awaiting_upload",
        generated_pdf_gcs_key=generated_pdf_key,
    )

    async with db.begin():
        db.add(batch)
        await db.flush()

    return UploadImagesResponse(batch_id=batch_id, images=upload_urls)


async def handle_analyze_images(  # noqa: PLR0911,PLR0912
    request: Request,
    body: AnalyzeImagesRequest,
    db: AsyncSession,
    *,
    _pdf_store=None,
    _dispatch=None,
) -> AnalyzeResponse | JSONResponse:
    settings = get_settings()
    if not settings.URL_SCAN_PDF_UPLOAD_BUCKET:
        return _internal_error("PDF upload bucket is not configured")

    batch = await db.get(UrlScanImageUploadBatch, body.batch_id)
    if batch is None:
        return _validation_error("upload_not_found", "image upload batch not found")

    if batch.conversion_status in {"submitted", "converting", "converted"}:
        return JSONResponse(
            status_code=202,
            content={"batch_id": str(body.batch_id), "status": "pending", "cached": False},
        )

    if batch.conversion_status != "awaiting_upload":
        return _validation_error(
            "upload_not_found",
            "image upload batch is not in awaiting_upload state",
        )

    store = _pdf_store or _get_pdf_store(settings.URL_SCAN_PDF_UPLOAD_BUCKET)
    images = batch.images if isinstance(batch.images, list) else json.loads(batch.images)

    try:
        for img in images:
            metadata = await store.get_metadata(str(img["gcs_key"]))
            if metadata is None:
                return _validation_error(
                    "upload_not_found",
                    "one or more images were not uploaded",
                )
            if metadata.get("size") != img["size_bytes"]:
                return _validation_error(
                    "upload_not_found",
                    "one or more images were not uploaded",
                )
    except Exception:
        return _validation_error(
            "upstream_error",
            "Image storage temporarily unavailable; please retry",
            status_code=503,
        )

    async with db.begin():
        batch_fresh = await db.get(UrlScanImageUploadBatch, body.batch_id)
        if batch_fresh is None or batch_fresh.conversion_status != "awaiting_upload":
            return JSONResponse(
                status_code=202,
                content={"batch_id": str(body.batch_id), "status": "pending", "cached": False},
            )
        batch_fresh.conversion_status = "submitted"
        await db.flush()

    if _dispatch is not None:
        try:
            await _dispatch(body.batch_id, settings)
        except Exception:
            async with db.begin():
                b = await db.get(UrlScanImageUploadBatch, body.batch_id)
                if b is not None:
                    b.conversion_status = "failed"
                    b.error_code = "internal"
                    b.error_message = "dispatch failed"
            return _internal_error("enqueue failed")
    else:
        try:
            from src.dbos_workflows.url_scan_convert_images_workflow import (  # noqa: PLC0415
                dispatch_image_conversion_workflow,
            )

            await dispatch_image_conversion_workflow(body.batch_id, settings)
        except Exception:
            async with db.begin():
                b = await db.get(UrlScanImageUploadBatch, body.batch_id)
                if b is not None:
                    b.conversion_status = "failed"
                    b.error_code = "internal"
                    b.error_message = "dispatch failed"
            return _internal_error("enqueue failed")

    return JSONResponse(
        status_code=202,
        content={"batch_id": str(body.batch_id), "status": "pending", "cached": False},
    )


async def handle_analyze_pdf(  # noqa: PLR0911,PLR0912
    request: Request,
    body: AnalyzePDFRequest,
    db: AsyncSession,
    *,
    _pdf_store=None,
    _dispatch=None,
) -> AnalyzeResponse | JSONResponse:
    try:
        gcs_key = str(UUID(body.gcs_key))
    except (TypeError, ValueError):
        return _validation_error("upload_key_invalid", "invalid gcs_key")

    settings = get_settings()
    if not settings.URL_SCAN_PDF_UPLOAD_BUCKET:
        return _internal_error("PDF upload bucket is not configured")

    try:
        store = _pdf_store or _get_pdf_store(settings.URL_SCAN_PDF_UPLOAD_BUCKET)
        metadata = await store.get_metadata(gcs_key)
    except Exception:
        return _validation_error(
            "upstream_error",
            "PDF storage temporarily unavailable; please retry",
            status_code=503,
        )

    if metadata is None:
        return _validation_error("upload_not_found", "PDF not found; upload may have failed")

    size = metadata.get("size")
    if not isinstance(size, int) or size < 0:
        return _validation_error("upload_not_found", "PDF not found; upload may have failed")
    if size > _MAX_PDF_BYTES:
        return _validation_error("pdf_too_large", "PDF too large")

    normalized_url = f"gcs-pdf://{gcs_key}"
    source_url = normalized_url
    host = "gcs-pdf"

    for attempt in range(2):
        async with db.begin():
            got_lock = await _try_advisory_lock(db, normalized_url)
            if got_lock:
                job_id, attempt_id = await _insert_pending_job(
                    db,
                    source_url=source_url,
                    normalized_url=normalized_url,
                    host=host,
                    api_key_id=None,
                )
                break
        if attempt == 0:
            await asyncio.sleep(_LOCK_RETRY_DELAY_SECONDS)
    else:
        return JSONResponse(
            status_code=503,
            content={
                "error_code": "rate_limited",
                "message": "advisory lock contended; retry shortly",
            },
            headers={"Retry-After": "2"},
        )

    dispatch_fn = _dispatch
    if dispatch_fn is None:
        from src.dbos_workflows.url_scan_workflow import dispatch_url_scan_workflow  # noqa: PLC0415

        dispatch_fn = dispatch_url_scan_workflow

    try:
        workflow_id = await dispatch_fn(job_id, source_url, normalized_url, attempt_id)
        if workflow_id is None:
            raise RuntimeError("dispatch returned no workflow id")
    except Exception as exc:
        await _mark_dispatch_failure(db, job_id, str(exc))
        return _internal_error("failed to dispatch url scan workflow")

    return JSONResponse(
        status_code=202,
        content=AnalyzeResponse(job_id=job_id, status=JobStatus.PENDING, cached=False).model_dump(
            mode="json"
        ),
        headers={"X-Url-Scan-Job-Id": str(job_id)},
    )
