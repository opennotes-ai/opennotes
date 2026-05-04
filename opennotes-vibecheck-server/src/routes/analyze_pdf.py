"""`POST /api/upload-pdf` mint endpoint (TASK-1498).

The browser sends PDF bytes directly to GCS using a signed PUT URL. The
server only generates a UUID object key + URL; it never receives or
buffers the file content.
"""
from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.config import Settings, get_settings
from src.jobs import submit as submit_job
from src.jobs.enqueue import enqueue_job
from src.jobs.pdf_storage import PdfUploadStore
from src.monitoring import get_logger
from src.monitoring_metrics import SINGLE_FLIGHT_LOCK_WAITS
from src.routes import analyze as analyze_route

router = APIRouter(prefix="/api", tags=["analyze"])

_MAX_PDF_BYTES = 50 * 1024 * 1024
_ALLOWED_PDF_TYPES = {"application/pdf", "application/octet-stream"}

logger = get_logger(__name__)


class UploadPDFResponse(BaseModel):
    gcs_key: str
    upload_url: str


class AnalyzePDFRequest(BaseModel):
    gcs_key: str
    filename: str | None = None


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
    if gcs_key.version != 4:
        return None
    return str(gcs_key)


@router.post("/upload-pdf", response_model=UploadPDFResponse)
@analyze_route.limiter.limit(analyze_route._rate_limit_value)
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
        signer = PdfUploadStore(settings.VIBECHECK_PDF_UPLOAD_BUCKET)
        upload_url = signer.signed_upload_url(gcs_key, ttl_seconds=900)
    except Exception:
        return _error_response("PDF upload URL signing failed")
    if not upload_url:
        return _error_response("PDF upload URL signing failed")

    return UploadPDFResponse(gcs_key=gcs_key, upload_url=upload_url)


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
                host="",
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


@router.post("/analyze-pdf", response_model=analyze_route.AnalyzeResponse)
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
        return _validation_error_response("invalid_url", "invalid gcs_key")

    settings = get_settings()
    if not settings.VIBECHECK_PDF_UPLOAD_BUCKET:
        return _error_response("PDF upload bucket is not configured")

    try:
        analyze_route._get_db_pool(request)
    except analyze_route._AnalyzeRouteError as exc:  # pragma: no cover - delegated
        return exc.to_response()

    try:
        metadata = PdfUploadStore(settings.VIBECHECK_PDF_UPLOAD_BUCKET).get_metadata(gcs_key)
    except Exception:
        return _validation_error_response(
            "invalid_url",
            "PDF not found; upload may have failed",
        )
    if metadata is None:
        return _validation_error_response(
            "invalid_url",
            "PDF not found; upload may have failed",
        )

    size = metadata.get("size")
    content_type = metadata.get("content_type")
    if not isinstance(size, int) or size < 0:
        return _validation_error_response(
            "invalid_url",
            "PDF not found; upload may have failed",
        )
    if size > _MAX_PDF_BYTES:
        return _validation_error_response("pdf_too_large", "PDF too large")
    if not isinstance(content_type, str) or content_type not in _ALLOWED_PDF_TYPES:
        return _validation_error_response(
            "pdf_extraction_failed",
            "invalid pdf content type",
        )

    response, _, ok = await _run_locked_submit(request, normalized_url=gcs_key)
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
