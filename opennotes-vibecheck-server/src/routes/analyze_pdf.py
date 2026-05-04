"""`POST /api/upload-pdf` mint endpoint (TASK-1498).

The browser sends PDF bytes directly to GCS using a signed PUT URL. The
server only generates a UUID object key + URL; it never receives or
buffers the file content.
"""
from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.config import Settings, get_settings
from src.jobs.pdf_storage import PdfUploadStore
from src.routes import analyze as analyze_route

router = APIRouter(prefix="/api", tags=["analyze"])


class UploadPDFResponse(BaseModel):
    gcs_key: str
    upload_url: str


def _error_response(message: str) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={
            "error_code": "internal",
            "message": message,
        },
    )


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
