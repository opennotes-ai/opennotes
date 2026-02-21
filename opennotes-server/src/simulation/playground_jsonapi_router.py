from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_user_or_api_key
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
from src.shared.content_extraction import ContentExtractionError, extract_content_from_url
from src.simulation.schemas import (
    PlaygroundNoteRequestBody,
    PlaygroundNoteRequestListResponse,
    PlaygroundNoteRequestResultAttributes,
    PlaygroundNoteRequestResultResource,
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
    response_class=JSONResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_playground_note_requests(
    community_server_id: UUID,
    body: PlaygroundNoteRequestBody,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> JSONResponse:
    try:
        result = await db.execute(
            select(CommunityServer).where(
                CommunityServer.id == community_server_id,
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
                f"Community server {community_server_id} is not a playground (platform={community_server.platform})",
            )

        attrs = body.data.attributes
        results: list[PlaygroundNoteRequestResultResource] = []
        succeeded = 0
        failed = 0

        for url in attrs.urls:
            url_str = str(url)
            request_id = f"playground-{uuid4().hex}"

            try:
                extracted = await extract_content_from_url(url_str)

                message_archive = await MessageArchiveService.create_from_text(
                    db=db,
                    content=extracted.text,
                )
                message_archive.message_metadata = {
                    "source_url": url_str,
                    "domain": extracted.domain,
                    "title": extracted.title,
                    "extracted_at": extracted.extracted_at.isoformat(),
                }

                note_request = Request(
                    request_id=request_id,
                    requested_by=attrs.requested_by,
                    community_server_id=community_server.id,
                    message_archive_id=message_archive.id,
                )
                db.add(note_request)
                await db.flush()

                results.append(
                    PlaygroundNoteRequestResultResource(
                        type="requests",
                        id=str(note_request.id),
                        attributes=PlaygroundNoteRequestResultAttributes(
                            request_id=request_id,
                            requested_by=attrs.requested_by,
                            status="PENDING",
                            community_server_id=str(community_server.id),
                            content=extracted.text[:500] if extracted.text else None,
                            url=url_str,
                        ),
                    )
                )
                succeeded += 1

            except ContentExtractionError as e:
                logger.warning(
                    f"Content extraction failed for URL: {url_str}",
                    extra={"url": url_str, "error": str(e)},
                )
                results.append(
                    PlaygroundNoteRequestResultResource(
                        type="requests",
                        id=request_id,
                        attributes=PlaygroundNoteRequestResultAttributes(
                            request_id=request_id,
                            requested_by=attrs.requested_by,
                            status="FAILED",
                            community_server_id=str(community_server.id),
                            url=url_str,
                            error=str(e),
                        ),
                    )
                )
                failed += 1

            except Exception as e:
                logger.exception(
                    f"Unexpected error processing URL: {url_str}",
                    extra={"url": url_str, "error": str(e)},
                )
                results.append(
                    PlaygroundNoteRequestResultResource(
                        type="requests",
                        id=request_id,
                        attributes=PlaygroundNoteRequestResultAttributes(
                            request_id=request_id,
                            requested_by=attrs.requested_by,
                            status="FAILED",
                            community_server_id=str(community_server.id),
                            url=url_str,
                            error=f"Unexpected error: {str(e)[:200]}",
                        ),
                    )
                )
                failed += 1

        await db.commit()

        response = PlaygroundNoteRequestListResponse(
            data=results,
            meta={"count": len(results), "succeeded": succeeded, "failed": failed},
        )

        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content=response.model_dump(by_alias=True, mode="json"),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to create playground note requests: {e}")
        await db.rollback()
        return _create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to create playground note requests",
        )
