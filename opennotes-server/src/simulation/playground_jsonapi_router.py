from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_user_or_api_key, require_admin
from src.common.jsonapi import (
    JSONAPI_CONTENT_TYPE,
)
from src.common.jsonapi import (
    create_error_response as create_error_response_model,
)
from src.database import get_db
from src.llm_config.models import CommunityServer
from src.monitoring import get_logger
from src.shared.url_validation import validate_url_security
from src.simulation.schemas import (
    PlaygroundNoteRequestBody,
    PlaygroundNoteRequestJobAttributes,
    PlaygroundNoteRequestJobResource,
    PlaygroundNoteRequestJobResponse,
)
from src.simulation.workflows.playground_url_workflow import (
    dispatch_playground_url_extraction,
)
from src.users.models import User

logger = get_logger(__name__)

router = APIRouter()


def _create_error_response(
    status_code: int,
    title: str,
    detail: str | None = None,
) -> JSONResponse:
    error_response = create_error_response_model(
        status_code=status_code,
        title=title,
        detail=detail,
    )
    return JSONResponse(
        status_code=status_code,
        content=error_response.model_dump(by_alias=True),
        media_type=JSONAPI_CONTENT_TYPE,
    )


@router.post(
    "/playgrounds/{community_server_id}/note-requests",
    response_model=PlaygroundNoteRequestJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={202: {"content": {"application/vnd.api+json": {}}}},
)
async def create_playground_note_requests(
    community_server_id: UUID,
    body: PlaygroundNoteRequestBody,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> PlaygroundNoteRequestJobResponse | JSONResponse:
    require_admin(current_user)

    try:
        result = await db.execute(
            select(CommunityServer).where(
                CommunityServer.id == community_server_id,
                CommunityServer.is_active.is_(True),
            )
        )
        community_server = result.scalar_one_or_none()

        if not community_server:
            return _create_error_response(
                status.HTTP_404_NOT_FOUND,
                "Not Found",
                f"Community server {community_server_id} not found",
            )

        if community_server.platform != "playground":
            return _create_error_response(
                status.HTTP_400_BAD_REQUEST,
                "Bad Request",
                f"Community server {community_server_id} is not a playground",
            )

        attrs = body.data.attributes
        urls = [str(u) for u in attrs.urls]

        url_errors: list[dict[str, str]] = []
        for url in urls:
            try:
                validate_url_security(url)
            except ValueError as exc:
                url_errors.append({"url": url, "error": str(exc)})

        if url_errors:
            detail_parts = [f"{e['url']}: {e['error']}" for e in url_errors]
            return _create_error_response(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "URL Validation Failed",
                "; ".join(detail_parts),
            )

        workflow_id = await dispatch_playground_url_extraction(
            urls=urls,
            community_server_id=community_server.id,
            requested_by=attrs.requested_by,
        )

        return PlaygroundNoteRequestJobResponse(
            data=PlaygroundNoteRequestJobResource(
                id=workflow_id,
                attributes=PlaygroundNoteRequestJobAttributes(
                    workflow_id=workflow_id,
                    url_count=len(urls),
                ),
            ),
        )

    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to create playground note requests")
        await db.rollback()
        return _create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to create playground note requests",
        )
