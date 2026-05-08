"""Image batch to generated-PDF conversion worker."""
from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from src.analyses.schemas import ErrorCode
from src.config import Settings
from src.jobs.enqueue import enqueue_job
from src.jobs.orchestrator import RunResult
from src.jobs.pdf_storage import get_pdf_upload_store
from src.monitoring import get_logger

logger = get_logger(__name__)


def _convert_images_to_pdf(image_bytes: list[bytes]) -> bytes:
    import img2pdf  # noqa: PLC0415

    result = img2pdf.convert(image_bytes)
    if not isinstance(result, bytes):
        raise RuntimeError("img2pdf returned non-bytes result")
    return result


async def _mark_failed(
    pool: Any,
    job_id: UUID,
    *,
    error_code: ErrorCode,
    error_message: str,
) -> None:
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute(
            """
            UPDATE vibecheck_image_upload_batches
            SET conversion_status = 'failed',
                error_code = $2,
                error_message = $3,
                updated_at = now()
            WHERE job_id = $1
            """,
            job_id,
            error_code.value,
            error_message,
        )
        await conn.execute(
            """
            UPDATE vibecheck_jobs
            SET status = 'failed',
                error_code = $2,
                error_message = $3,
                finished_at = now(),
                updated_at = now()
            WHERE job_id = $1
            """,
            job_id,
            error_code.value,
            error_message,
        )


async def _claim_conversion(
    pool: Any,
    job_id: UUID,
    expected_attempt_id: UUID,
) -> dict[str, Any] | None:
    async with pool.acquire() as conn, conn.transaction():
        row = await conn.fetchrow(
            """
            UPDATE vibecheck_image_upload_batches b
            SET conversion_status = 'converting',
                updated_at = now()
            FROM vibecheck_jobs j
            WHERE b.job_id = j.job_id
              AND b.job_id = $1
              AND j.attempt_id = $2
              AND j.status = 'pending'
              AND b.conversion_status = 'submitted'
            RETURNING b.images, b.generated_pdf_gcs_key
            """,
            job_id,
            expected_attempt_id,
        )
        if row is not None:
            await conn.execute(
                """
                UPDATE vibecheck_jobs
                SET last_stage = 'converting_images',
                    heartbeat_at = now(),
                    updated_at = now()
                WHERE job_id = $1
                  AND attempt_id = $2
                """,
                job_id,
                expected_attempt_id,
            )
            return dict(row)

        converted = await conn.fetchrow(
            """
            SELECT b.generated_pdf_gcs_key
            FROM vibecheck_image_upload_batches b
            JOIN vibecheck_jobs j ON j.job_id = b.job_id
            WHERE b.job_id = $1
              AND j.attempt_id = $2
              AND j.status = 'pending'
              AND b.conversion_status = 'converted'
            """,
            job_id,
            expected_attempt_id,
        )
    return {"already_converted": True, **dict(converted)} if converted else None


async def _mark_converted(
    pool: Any,
    job_id: UUID,
    expected_attempt_id: UUID,
    generated_pdf_key: str,
) -> None:
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute(
            """
            UPDATE vibecheck_image_upload_batches
            SET conversion_status = 'converted',
                generated_pdf_gcs_key = $2,
                updated_at = now()
            WHERE job_id = $1
            """,
            job_id,
            generated_pdf_key,
        )
        await conn.execute(
            """
            UPDATE vibecheck_jobs
            SET url = $2,
                normalized_url = $2,
                host = 'gcs-pdf',
                last_stage = 'pdf_extract',
                heartbeat_at = now(),
                updated_at = now()
            WHERE job_id = $1
              AND attempt_id = $3
              AND status = 'pending'
            """,
            job_id,
            generated_pdf_key,
            expected_attempt_id,
        )


async def run_image_conversion(  # noqa: PLR0911
    pool: Any,
    job_id: UUID,
    expected_attempt_id: UUID,
    settings: Settings,
) -> RunResult:
    """Convert a submitted image batch to PDF and enqueue the normal PDF pipeline."""
    claim = await _claim_conversion(pool, job_id, expected_attempt_id)
    if claim is None:
        logger.info("image conversion stale or missing job=%s", job_id)
        return RunResult(status_code=200)

    generated_pdf_key = str(claim["generated_pdf_gcs_key"])
    if not claim.get("already_converted"):
        images = claim["images"]
        decoded_images = json.loads(images) if isinstance(images, str) else images
        if not isinstance(decoded_images, list):
            await _mark_failed(
                pool,
                job_id,
                error_code=ErrorCode.IMAGE_CONVERSION_FAILED,
                error_message="image batch metadata invalid",
            )
            return RunResult(status_code=200)

        store = get_pdf_upload_store(settings.VIBECHECK_PDF_UPLOAD_BUCKET)
        try:
            source_bytes = [
                store.read_bytes(str(image["gcs_key"]))
                for image in sorted(decoded_images, key=lambda item: int(item["ordinal"]))
            ]
        except Exception as exc:
            await _mark_failed(
                pool,
                job_id,
                error_code=ErrorCode.UPLOAD_NOT_FOUND,
                error_message=f"source image missing or unreadable: {exc}",
            )
            return RunResult(status_code=200)

        try:
            pdf_bytes = _convert_images_to_pdf(source_bytes)
        except Exception as exc:
            await _mark_failed(
                pool,
                job_id,
                error_code=ErrorCode.IMAGE_CONVERSION_FAILED,
                error_message=f"image conversion failed: {exc}",
            )
            return RunResult(status_code=200)

        try:
            store.write_pdf(generated_pdf_key, pdf_bytes)
        except Exception as exc:
            logger.warning("generated PDF upload failed for job %s: %s", job_id, exc)
            return RunResult(status_code=503)

        await _mark_converted(pool, job_id, expected_attempt_id, generated_pdf_key)

    try:
        await enqueue_job(job_id, expected_attempt_id, settings)
    except Exception as exc:
        logger.warning("normal PDF pipeline enqueue failed for image job %s: %s", job_id, exc)
        return RunResult(status_code=503)
    return RunResult(status_code=200)
