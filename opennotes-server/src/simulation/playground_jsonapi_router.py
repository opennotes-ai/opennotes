from __future__ import annotations

from typing import Annotated
from uuid import UUID, uuid4

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
from src.notes.message_archive_service import MessageArchiveService
from src.notes.models import Request
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


async def _create_text_note_requests(
    texts: list[str],
    community_server_id: UUID,
    requested_by: str,
    job_id: str,
    db: AsyncSession,
) -> None:
    for idx, text in enumerate(texts):
        message_archive = await MessageArchiveService.create_from_text(
            db=db,
            content=text,
        )
        message_archive.message_metadata = {
            "source": "text_input",
        }

        request_id = f"playground-text-{job_id}-{idx}"
        note_request = Request(
            request_id=request_id,
            requested_by=requested_by,
            community_server_id=community_server_id,
            message_archive_id=message_archive.id,
        )
        db.add(note_request)

    await db.commit()


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
        urls = [str(u) for u in attrs.urls] if attrs.urls else []
        texts = list(attrs.texts) if attrs.texts else []

        if urls:
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

        workflow_id: str | None = None
        if urls:
            workflow_id = await dispatch_playground_url_extraction(
                urls=urls,
                community_server_id=community_server.id,
                requested_by=attrs.requested_by,
            )

        job_id = workflow_id or f"playground-text-{uuid4().hex}"

        if texts:
            await _create_text_note_requests(
                texts=texts,
                community_server_id=community_server.id,
                requested_by=attrs.requested_by,
                job_id=job_id,
                db=db,
            )

        return PlaygroundNoteRequestJobResponse(
            data=PlaygroundNoteRequestJobResource(
                id=job_id,
                attributes=PlaygroundNoteRequestJobAttributes(
                    workflow_id=job_id,
                    url_count=len(urls),
                    text_count=len(texts),
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
