"""OpenAPI emission anchor for the async-pipeline schemas (TASK-1473.03).

This route exists solely to force `JobState` (and transitively `SectionSlot`,
`SectionState`, `SectionSlug`, `JobStatus`, `ErrorCode`, `PageKind`) into the
generated OpenAPI schema so the frontend's `openapi-typescript` build emits
matching string-union and interface types.

It is replaced by the real `GET /api/analyze/{job_id}` endpoint when
TASK-1473.14 lands. Until then, the route is intentionally never called by
the client; calling it returns 410 Gone.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from src.analyses.schemas import JobState

router = APIRouter(prefix="/api/_internal", tags=["_schema_anchor"])


@router.get(
    "/_schema_anchor",
    response_model=JobState,
    summary="Schema anchor (placeholder, removed in TASK-1473.14)",
    description=(
        "Forces JobState into the OpenAPI schema until the real "
        "GET /api/analyze/{job_id} endpoint lands. Always returns 410 Gone."
    ),
    responses={
        410: {
            "description": (
                "Always — this route is a placeholder so openapi-typescript "
                "emits matching JobState/SectionSlot/SectionSlug/etc. type "
                "aliases. TASK-1473.14 replaces it with the real polling "
                "endpoint."
            )
        }
    },
)
async def schema_anchor() -> JobState:
    raise HTTPException(status_code=410, detail="schema-anchor placeholder")


__all__ = ["router"]
