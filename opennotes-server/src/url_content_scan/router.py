from fastapi import APIRouter, HTTPException

from src.url_content_scan.schemas import JobState, SidebarPayload

router = APIRouter(prefix="/api/v1/url_scan", tags=["url_scan"])


@router.get(
    "/_schema_anchor",
    response_model=JobState,
    summary="URL scan schema anchor",
    description=(
        "Forces URL scan polling/sidebar schemas into OpenAPI until the real "
        "polling endpoint is implemented. Always returns 410 Gone."
    ),
    responses={410: {"description": "Always. Placeholder route for schema generation."}},
)
async def schema_anchor() -> JobState:
    raise HTTPException(status_code=410, detail="schema-anchor placeholder")


@router.get(
    "/_sidebar_schema_anchor",
    response_model=SidebarPayload,
    summary="URL scan sidebar schema anchor",
    description=(
        "Forces SidebarPayload into OpenAPI until the real analyze/poll endpoints "
        "are implemented. Always returns 410 Gone."
    ),
    responses={410: {"description": "Always. Placeholder route for schema generation."}},
)
async def sidebar_schema_anchor() -> SidebarPayload:
    raise HTTPException(status_code=410, detail="schema-anchor placeholder")
