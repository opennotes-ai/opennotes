"""`POST /api/upload-pdf` mint endpoint (TASK-1498).

The browser sends PDF bytes directly to GCS using a signed PUT URL. The
server only generates a UUID object key + URL; it never receives or
buffers the file content.
"""
from __future__ import annotations

import asyncio
import json
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from src.config import Settings, get_settings
from src.jobs import submit as submit_job
from src.jobs.enqueue import enqueue_image_conversion, enqueue_job
from src.jobs.pdf_storage import get_pdf_upload_store
from src.monitoring import get_logger
from src.monitoring_metrics import SINGLE_FLIGHT_LOCK_WAITS
from src.routes import analyze as analyze_route

router = APIRouter(prefix="/api", tags=["analyze"])

_MAX_PDF_BYTES = 50 * 1024 * 1024
_MAX_IMAGE_BATCH_BYTES = 45 * 1024 * 1024
_MAX_IMAGE_COUNT = 100
_ALLOWED_PDF_TYPES = {"application/pdf", "application/octet-stream"}
_ALLOWED_IMAGE_TYPES = {
    "image/jpeg",
    "image/png",
    "image/tiff",
    "image/bmp",
}

logger = get_logger(__name__)


class UploadPDFResponse(BaseModel):
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
    job_id: UUID
    images: list[ImageUploadUrl]


class AnalyzeImagesRequest(BaseModel):
    job_id: UUID


def _error_response(message: str) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={
            "error_code": "internal",
            "message": message,
        },
    )


def _validation_error_response(error_code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={
            "error_code": error_code,
            "message": message,
        },
    )


def _normalize_gcs_key(raw_key: str) -> str | None:
    try:
        gcs_key = UUID(raw_key)
    except (TypeError, ValueError):
        return None
    return str(gcs_key)


def _image_key(job_id: UUID, ordinal: int) -> str:
    return f"image-uploads/{job_id}/source/{ordinal:03d}-{uuid4()}"


def _generated_pdf_key(job_id: UUID) -> str:
    return f"image-uploads/{job_id}/generated.pdf"


def _validate_image_request(images: list[ImageUploadItem]) -> JSONResponse | None:
    if len(images) > _MAX_IMAGE_COUNT:
        return _validation_error_response(
            "image_count_too_large",
            "image batch cannot contain more than 100 images",
        )
    aggregate_size = sum(image.size_bytes for image in images)
    if aggregate_size > _MAX_IMAGE_BATCH_BYTES:
        return _validation_error_response(
            "image_aggregate_too_large",
            "image batch too large",
        )
    bad_type = next(
        (image.content_type for image in images if image.content_type not in _ALLOWED_IMAGE_TYPES),
        None,
    )
    if bad_type is not None:
        return _validation_error_response(
            "invalid_image_type",
            f"unsupported image content type: {bad_type}",
        )
    return None


def _metadata_matches(
    metadata: dict[str, object] | None,
    *,
    expected_size: int,
    expected_content_type: str,
) -> bool:
    if metadata is None:
        return False
    return (
        metadata.get("size") == expected_size
        and metadata.get("content_type") == expected_content_type
    )


@router.post("/upload-pdf", response_model=UploadPDFResponse)
@analyze_route.limiter.shared_limit(
    analyze_route._rate_limit_value,
    scope=analyze_route.SUBMIT_RATE_LIMIT_SCOPE,
)
async def upload_pdf(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> UploadPDFResponse | JSONResponse:
    """Return `{ gcs_key, upload_url }` for a direct browser upload.

    Returns a stable 500 payload when configuration is missing or signing
    fails. We do not accept or buffer any PDF bytes in this path.
    """
    if not settings.VIBECHECK_PDF_UPLOAD_BUCKET:
        return _error_response("PDF upload bucket is not configured")

    gcs_key = str(uuid4())
    try:
        signer = get_pdf_upload_store(settings.VIBECHECK_PDF_UPLOAD_BUCKET)
        upload_url = signer.signed_upload_url(gcs_key, ttl_seconds=900)
    except Exception:
        return _error_response("PDF upload URL signing failed")
    if not upload_url:
        return _error_response("PDF upload URL signing failed")

    return UploadPDFResponse(gcs_key=gcs_key, upload_url=upload_url)


@router.post("/upload-images", response_model=UploadImagesResponse)
@analyze_route.limiter.shared_limit(
    analyze_route._rate_limit_value,
    scope=analyze_route.SUBMIT_RATE_LIMIT_SCOPE,
)
async def upload_images(
    request: Request,
    body: UploadImagesRequest,
    settings: Settings = Depends(get_settings),
) -> UploadImagesResponse | JSONResponse:
    """Create a pending job and return signed PUT URLs for ordered source images."""
    validation_error = _validate_image_request(body.images)
    if validation_error is not None:
        return validation_error
    if not settings.VIBECHECK_PDF_UPLOAD_BUCKET:
        return _error_response("PDF upload bucket is not configured")

    job_id = uuid4()
    image_records: list[dict[str, object]] = []
    upload_urls: list[ImageUploadUrl] = []
    try:
        signer = get_pdf_upload_store(settings.VIBECHECK_PDF_UPLOAD_BUCKET)
        for ordinal, image in enumerate(body.images):
            key = _image_key(job_id, ordinal)
            upload_url = signer.signed_upload_url(
                key,
                ttl_seconds=900,
                content_type=image.content_type,
            )
            if not upload_url:
                return _error_response("Image upload URL signing failed")
            image_records.append(
                {
                    "ordinal": ordinal,
                    "gcs_key": key,
                    "content_type": image.content_type,
                    "size_bytes": image.size_bytes,
                    "filename": image.filename,
                }
            )
            upload_urls.append(
                ImageUploadUrl(
                    ordinal=ordinal,
                    gcs_key=key,
                    upload_url=upload_url,
                )
            )
    except Exception:
        return _error_response("Image upload URL signing failed")

    pool = analyze_route._get_db_pool(request)
    attempt_id = uuid4()
    placeholder_url = f"image-upload://{job_id}"
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute(
            """
            INSERT INTO vibecheck_jobs (
                job_id, url, normalized_url, host, source_type, status,
                attempt_id, last_stage
            )
            VALUES ($1, $2, $2, 'gcs-image', 'pdf', 'pending', $3, 'converting_images')
            """,
            job_id,
            placeholder_url,
            attempt_id,
        )
        await conn.execute(
            """
            INSERT INTO vibecheck_image_upload_batches (
                job_id, images, conversion_status, generated_pdf_gcs_key
            )
            VALUES ($1, $2::jsonb, 'awaiting_upload', $3)
            """,
            job_id,
            json.dumps(image_records),
            _generated_pdf_key(job_id),
        )

    return UploadImagesResponse(job_id=job_id, images=upload_urls)


@router.post(
    "/analyze-images",
    response_model=analyze_route.AnalyzeResponse,
    status_code=202,
)
@analyze_route.limiter.shared_limit(
    analyze_route._rate_limit_value,
    scope=analyze_route.SUBMIT_RATE_LIMIT_SCOPE,
)
async def analyze_images(  # noqa: PLR0911
    request: Request,
    body: AnalyzeImagesRequest,
) -> analyze_route.AnalyzeResponse | JSONResponse:
    """Validate uploaded source images and enqueue image-to-PDF conversion."""
    settings = get_settings()
    if not settings.VIBECHECK_PDF_UPLOAD_BUCKET:
        return _error_response("PDF upload bucket is not configured")

    pool = analyze_route._get_db_pool(request)
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT j.job_id, j.status, j.attempt_id, b.images, b.conversion_status
            FROM vibecheck_jobs j
            JOIN vibecheck_image_upload_batches b ON b.job_id = j.job_id
            WHERE j.job_id = $1
            """,
            body.job_id,
        )
    if row is None:
        return _validation_error_response("upload_not_found", "image upload job not found")
    if row["status"] in {"done", "partial", "failed"}:
        return _validation_error_response(
            "upload_not_found",
            "image upload job is not pending",
        )
    if row["conversion_status"] in {"submitted", "converting", "converted"}:
        return JSONResponse(
            status_code=202,
            content=analyze_route.AnalyzeResponse(
                job_id=body.job_id,
                status=row["status"],
                cached=False,
            ).model_dump(mode="json"),
            headers={"X-Vibecheck-Job-Id": str(body.job_id)},
        )

    images = json.loads(row["images"]) if isinstance(row["images"], str) else row["images"]
    if not isinstance(images, list):
        return _validation_error_response("upload_not_found", "image upload batch is invalid")

    store = get_pdf_upload_store(settings.VIBECHECK_PDF_UPLOAD_BUCKET)
    try:
        for image in images:
            metadata = store.get_metadata(str(image["gcs_key"]))
            if not _metadata_matches(
                metadata,
                expected_size=int(image["size_bytes"]),
                expected_content_type=str(image["content_type"]),
            ):
                return _validation_error_response(
                    "upload_not_found",
                    "one or more images were not uploaded",
                )
    except Exception:
        return analyze_route._error_response(
            503,
            "upstream_error",
            "Image storage temporarily unavailable; please retry",
        )

    async with pool.acquire() as conn, conn.transaction():
        updated = await conn.fetchrow(
            """
            UPDATE vibecheck_image_upload_batches
            SET conversion_status = 'submitted',
                updated_at = now()
            WHERE job_id = $1
              AND conversion_status = 'awaiting_upload'
            RETURNING job_id
            """,
            body.job_id,
        )
        await conn.execute(
            """
            UPDATE vibecheck_jobs
            SET last_stage = 'converting_images',
                heartbeat_at = now(),
                updated_at = now()
            WHERE job_id = $1
            """,
            body.job_id,
        )
    if updated is not None:
        try:
            await enqueue_image_conversion(body.job_id, row["attempt_id"], settings)
        except Exception:
            logger.warning("enqueue_image_conversion failed for job %s", body.job_id)
            await submit_job._mark_job_failed_enqueue(pool, body.job_id)
            return analyze_route._error_response(500, "internal", "enqueue failed")

    response = analyze_route.AnalyzeResponse(
        job_id=body.job_id,
        status=row["status"],
        cached=False,
    )
    return JSONResponse(
        status_code=202,
        content=response.model_dump(mode="json"),
        headers={"X-Vibecheck-Job-Id": str(body.job_id)},
    )


async def _run_locked_submit(
    request: Request,
    *,
    normalized_url: str,
) -> tuple[analyze_route.AnalyzeResponse | None, UUID | None, bool]:
    pool = analyze_route._get_db_pool(request)

    async def run_locked() -> tuple[
        analyze_route.AnalyzeResponse | None, UUID | None, bool
    ]:
        async with pool.acquire() as conn, conn.transaction():
            got_lock = await analyze_route._try_advisory_lock(conn, normalized_url)
            if not got_lock:
                SINGLE_FLIGHT_LOCK_WAITS.inc()
                existing = await submit_job._find_inflight_job(conn, normalized_url)
                if existing is not None:
                    existing_job_id, existing_status = existing
                    return (
                        analyze_route.AnalyzeResponse(
                            job_id=existing_job_id,
                            status=existing_status,
                            cached=False,
                        ),
                        None,
                        True,
                    )
                return None, None, False
            submit_result, attempt_to_enqueue = await submit_job.handle_locked_submit(
                conn,
                url=normalized_url,
                normalized_url=normalized_url,
                host="gcs-pdf",
                unsafe_finding=None,
                source_type="pdf",
            )
            analyze_response = analyze_route.AnalyzeResponse(
                job_id=submit_result.job_id,
                status=submit_result.status,
                cached=submit_result.cached,
            )
            return analyze_response, attempt_to_enqueue, True

    response, attempt_to_enqueue, got_lock = await run_locked()
    if not got_lock:
        # Bounded retry budget: one extra pass after ~1 second.
        await asyncio.sleep(1.0)
        response, attempt_to_enqueue, got_lock = await run_locked()

    if not got_lock:
        return None, None, False

    if response is None:
        return None, None, True

    if attempt_to_enqueue is not None:
        try:
            settings = get_settings()
            await enqueue_job(response.job_id, attempt_to_enqueue, settings)
        except Exception as exc:
            logger.warning(
                "enqueue_job failed for pdf job %s: %s",
                response.job_id,
                exc,
            )
            await submit_job._mark_job_failed_enqueue(pool, response.job_id)
            return None, None, True

    return response, None, True


@router.post(
    "/analyze-pdf",
    response_model=analyze_route.AnalyzeResponse,
    status_code=202,
)
@analyze_route.limiter.shared_limit(
    analyze_route._rate_limit_value,
    scope=analyze_route.SUBMIT_RATE_LIMIT_SCOPE,
)
async def analyze_pdf(  # noqa: PLR0911
    request: Request,
    body: AnalyzePDFRequest,
) -> analyze_route.AnalyzeResponse | JSONResponse:
    gcs_key = _normalize_gcs_key(body.gcs_key)
    if gcs_key is None:
        return _validation_error_response("upload_key_invalid", "invalid gcs_key")

    settings = get_settings()
    if not settings.VIBECHECK_PDF_UPLOAD_BUCKET:
        return _error_response("PDF upload bucket is not configured")

    try:
        metadata = get_pdf_upload_store(settings.VIBECHECK_PDF_UPLOAD_BUCKET).get_metadata(gcs_key)
    except Exception:
        return analyze_route._error_response(
            503,
            "upstream_error",
            "PDF storage temporarily unavailable; please retry",
        )
    if metadata is None:
        return _validation_error_response(
            "upload_not_found",
            "PDF not found; upload may have failed",
        )

    size = metadata.get("size")
    content_type = metadata.get("content_type")
    if not isinstance(size, int) or size < 0:
        return _validation_error_response(
            "upload_not_found",
            "PDF not found; upload may have failed",
        )
    if size > _MAX_PDF_BYTES:
        return _validation_error_response("pdf_too_large", "PDF too large")
    if not isinstance(content_type, str) or content_type not in _ALLOWED_PDF_TYPES:
        return _validation_error_response(
            "invalid_pdf_type",
            "invalid pdf content type",
        )

    try:
        response, _, ok = await _run_locked_submit(request, normalized_url=gcs_key)
    except analyze_route._AnalyzeRouteError as exc:
        return exc.to_response()
    if response is None:
        if ok:
            return analyze_route._error_response(
                500,
                "internal",
                "enqueue failed",
            )
        return analyze_route._error_response(
            503,
            "rate_limited",
            "advisory lock contended; retry shortly",
            headers={"Retry-After": "2"},
        )

    return JSONResponse(
        status_code=202,
        content=response.model_dump(mode="json"),
        headers={"X-Vibecheck-Job-Id": str(response.job_id)},
    )
