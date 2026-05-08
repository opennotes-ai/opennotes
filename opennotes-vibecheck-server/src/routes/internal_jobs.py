"""Internal Cloud Tasks push-queue handler (TASK-1473.12).

`POST /_internal/jobs/{job_id}/run` is the HTTP entry Cloud Tasks invokes
after `POST /api/analyze` enqueues a fresh submit. The route itself is
thin: OIDC dependency, JSON body parsing, delegate to the orchestrator,
return the status code the orchestrator decided on.

The endpoint is guarded by `verify_cloud_tasks_oidc` as a router-level
dependency so **every** path under `/_internal` requires a valid
Google-signed token bound to our enqueuer SA. Rejection returns 401 via
the dependency itself — the handler never sees an unauthenticated
request.

The body payload carries `{job_id, expected_attempt_id}`: the
orchestrator CAS-claims on the tuple so a Cloud Tasks redelivery after a
retry rotation harmlessly hits a stale attempt and returns 200 no-op.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.analyses.safety.video_moderation_poller import (
    VideoModerationPollPayload,
    video_moderation_poll,
)
from src.analyses.schemas import SectionSlug
from src.auth.cloud_tasks_oidc import verify_cloud_tasks_oidc
from src.config import Settings, get_settings
from src.jobs.image_pdf_conversion import run_image_conversion
from src.jobs.orchestrator import run_job, run_section_retry
from src.monitoring import get_logger

logger = get_logger(__name__)

router = APIRouter(
    prefix="/_internal",
    tags=["internal"],
    dependencies=[Depends(verify_cloud_tasks_oidc)],
)


class RunJobBody(BaseModel):
    """Cloud Tasks request payload for the run endpoint."""

    job_id: UUID
    expected_attempt_id: UUID


def _get_db_pool(request: Request) -> Any:
    """Fetch the asyncpg pool attached at startup.

    Raises 503 with a structured error if the pool is missing — that is
    a deploy-time misconfiguration (lifespan didn't boot) rather than a
    transient condition, but the response shape stays consistent with
    the public API so frontends don't need a separate branch.
    """
    pool = getattr(request.app.state, "db_pool", None)
    if pool is None:
        raise HTTPException(
            status_code=503,
            detail={
                "error_code": "internal",
                "message": "database pool not initialized",
            },
        )
    return pool


@router.post("/jobs/{job_id}/run")
async def run(
    job_id: UUID,
    body: RunJobBody,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """Drive one Cloud Tasks delivery through the orchestrator.

    The path's `job_id` and the body's `job_id` must agree — Cloud Tasks
    signs the URL as well as the body, so a drift here signals either
    misconfig or tampering; we reject with 400 rather than trust one side.

    Orchestrator return values map to HTTP status:
        200: success / stale claim / terminal-failure (no Cloud Tasks retry)
        503: transient failure (Cloud Tasks retries per queue config)

    Response body is intentionally minimal — Cloud Tasks ignores it.
    """
    if body.job_id != job_id:
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "invalid_request",
                "message": "path job_id does not match body job_id",
            },
        )

    pool = _get_db_pool(request)

    result = await run_job(
        pool, job_id, body.expected_attempt_id, settings
    )
    return JSONResponse(
        status_code=result.status_code,
        content={"status_code": result.status_code},
    )


@router.post("/jobs/{job_id}/convert-images")
async def convert_images(
    job_id: UUID,
    body: RunJobBody,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """Drive one Cloud Tasks delivery through image-to-PDF conversion."""
    if body.job_id != job_id:
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "invalid_request",
                "message": "path job_id does not match body job_id",
            },
        )

    pool = _get_db_pool(request)

    result = await run_image_conversion(
        pool, job_id, body.expected_attempt_id, settings
    )
    return JSONResponse(
        status_code=result.status_code,
        content={"status_code": result.status_code},
    )


class RunSectionBody(BaseModel):
    """Cloud Tasks request payload for the per-section retry endpoint."""

    job_id: UUID
    slug: SectionSlug
    expected_slot_attempt_id: UUID


@router.post("/jobs/{job_id}/sections/{slug}/run")
async def run_section(
    job_id: UUID,
    slug: SectionSlug,
    body: RunSectionBody,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """Drive one section-retry Cloud Tasks delivery.

    OIDC verification runs at the router-level dependency so a reject
    happens before this handler sees the request. On entry we validate
    that the path parameters match the body (Cloud Tasks signs both — a
    mismatch is either tampering or misconfig; we refuse), then hand off
    to `run_section_retry` which owns the CAS-claim → analyze →
    mark-done/failed → maybe-finalize sequence.

    Status codes mirror the main worker: 200 on success / stale / terminal,
    503 on transient failure (Cloud Tasks retries per queue config).
    """
    if body.job_id != job_id:
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "invalid_request",
                "message": "path job_id does not match body job_id",
            },
        )
    if body.slug != slug:
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "invalid_request",
                "message": "path slug does not match body slug",
            },
        )

    pool = _get_db_pool(request)

    result = await run_section_retry(
        pool, job_id, slug, body.expected_slot_attempt_id, settings
    )
    return JSONResponse(
        status_code=result.status_code,
        content={"status_code": result.status_code},
    )


@router.post("/jobs/{job_id}/video-moderation/poll")
async def poll_video_moderation(
    job_id: UUID,
    body: VideoModerationPollPayload,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """Drive one Video Intelligence LRO polling Cloud Task delivery."""
    if body.job_id != job_id:
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "invalid_request",
                "message": "path job_id does not match body job_id",
            },
        )

    pool = _get_db_pool(request)
    status = await video_moderation_poll(body, pool=pool, settings=settings)
    return JSONResponse(status_code=200, content={"status": status})


__all__ = ["router"]
