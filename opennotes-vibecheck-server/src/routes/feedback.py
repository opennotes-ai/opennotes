from uuid import UUID

import uuid_utils
from fastapi import APIRouter, HTTPException, Request
from slowapi.util import get_ipaddr

from src.middleware.uid_cookie import get_uid
from src.routes import analyze as _analyze_module
from src.routes.feedback_models import (
    FeedbackCombinedRequest,
    FeedbackOpenResponse,
    FeedbackRequest,
    FeedbackSubmitRequest,
)

router = APIRouter(prefix="/api", tags=["feedback"])

limiter = _analyze_module.limiter

POST_RATE_LIMIT = "10/hour"
PATCH_RATE_LIMIT = "30/hour"


def _uid_or_ip_key(request: Request) -> str:
    uid = getattr(request.state, "uid", None)
    if uid is not None:
        return f"uid:{uid}"
    return f"ip:{get_ipaddr(request)}"


def _get_db_pool(request: Request):
    pool = getattr(request.app.state, "db_pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="database pool not initialized")
    return pool


@router.post("/feedback", response_model=FeedbackOpenResponse, status_code=201)
@limiter.limit(POST_RATE_LIMIT, key_func=_uid_or_ip_key)
@limiter.limit(POST_RATE_LIMIT, key_func=get_ipaddr)
async def open_or_combined_feedback(
    payload: FeedbackRequest,
    request: Request,
) -> FeedbackOpenResponse:
    uid = get_uid(request)
    feedback_id = UUID(str(uuid_utils.uuid7()))
    pool = _get_db_pool(request)

    if isinstance(payload, FeedbackCombinedRequest):
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO vibecheck_feedback
                    (id, page_path, user_agent, referrer, uid, bell_location,
                     initial_type, email, message, final_type, submitted_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, pg_catalog.now())
                """,
                feedback_id,
                payload.page_path,
                payload.user_agent,
                payload.referrer,
                uid,
                payload.bell_location,
                payload.initial_type,
                payload.email,
                payload.message,
                payload.final_type,
            )
    else:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO vibecheck_feedback
                    (id, page_path, user_agent, referrer, uid, bell_location, initial_type)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                feedback_id,
                payload.page_path,
                payload.user_agent,
                payload.referrer,
                uid,
                payload.bell_location,
                payload.initial_type,
            )

    return FeedbackOpenResponse(id=feedback_id)


@router.patch("/feedback/{feedback_id}", status_code=200)
@limiter.limit(PATCH_RATE_LIMIT, key_func=_uid_or_ip_key)
@limiter.limit(PATCH_RATE_LIMIT, key_func=get_ipaddr)
async def submit_feedback(
    feedback_id: UUID,
    payload: FeedbackSubmitRequest,
    request: Request,
) -> dict:
    pool = _get_db_pool(request)
    async with pool.acquire() as conn:
        result = await conn.execute(
            """
            UPDATE vibecheck_feedback
            SET email = $1,
                message = $2,
                final_type = $3,
                submitted_at = pg_catalog.now()
            WHERE id = $4
            """,
            payload.email,
            payload.message,
            payload.final_type,
            feedback_id,
        )
    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail="feedback not found")
    return {}
