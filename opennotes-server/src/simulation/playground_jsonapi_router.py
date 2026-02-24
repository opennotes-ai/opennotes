from __future__ import annotations

import asyncio
import ipaddress
import socket
from typing import Annotated
from urllib.parse import urlparse
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

SSRF_ALLOWED_SCHEMES = {"http", "https"}
URL_FETCH_TIMEOUT = 30
URL_CONCURRENCY_LIMIT = 5

_PRIVATE_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def _validate_url_security(url_str: str) -> None:
    parsed = urlparse(url_str)

    if parsed.scheme not in SSRF_ALLOWED_SCHEMES:
        raise ValueError(f"Scheme '{parsed.scheme}' is not allowed; use http or https")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("URL must contain a valid hostname")

    try:
        addr_infos = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError(f"DNS resolution failed for hostname '{hostname}'") from exc

    for _family, _type, _proto, _canonname, sockaddr in addr_infos:
        ip_str = sockaddr[0]
        ip = ipaddress.ip_address(ip_str)
        for network in _PRIVATE_NETWORKS:
            if ip in network:
                raise ValueError("URLs pointing to private or reserved IP ranges are not allowed")


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
                f"Community server {community_server_id} is not a playground (platform={community_server.platform})",
            )

        attrs = body.data.attributes
        results: list[PlaygroundNoteRequestResultResource] = []
        succeeded = 0
        failed = 0
        semaphore = asyncio.Semaphore(URL_CONCURRENCY_LIMIT)

        async def _process_url(url_str: str) -> tuple[PlaygroundNoteRequestResultResource, bool]:
            request_id = f"playground-{uuid4().hex}"

            try:
                _validate_url_security(url_str)
            except ValueError as exc:
                logger.warning(
                    "URL failed SSRF validation",
                    extra={"url": url_str, "error": str(exc)},
                )
                return (
                    PlaygroundNoteRequestResultResource(
                        type="requests",
                        id=request_id,
                        attributes=PlaygroundNoteRequestResultAttributes(
                            request_id=request_id,
                            requested_by=attrs.requested_by,
                            status="FAILED",
                            community_server_id=str(community_server.id),
                            url=url_str,
                            error="URL validation failed",
                        ),
                    ),
                    False,
                )

            try:
                async with semaphore:
                    extracted = await asyncio.wait_for(
                        extract_content_from_url(url_str),
                        timeout=URL_FETCH_TIMEOUT,
                    )

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

                return (
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
                    ),
                    True,
                )

            except ContentExtractionError as e:
                logger.warning(
                    "Content extraction failed for URL",
                    extra={"url": url_str, "error": str(e)},
                )
                return (
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
                    ),
                    False,
                )

            except TimeoutError:
                logger.warning(
                    "URL fetch timed out",
                    extra={"url": url_str, "timeout": URL_FETCH_TIMEOUT},
                )
                return (
                    PlaygroundNoteRequestResultResource(
                        type="requests",
                        id=request_id,
                        attributes=PlaygroundNoteRequestResultAttributes(
                            request_id=request_id,
                            requested_by=attrs.requested_by,
                            status="FAILED",
                            community_server_id=str(community_server.id),
                            url=url_str,
                            error="Content extraction timed out",
                        ),
                    ),
                    False,
                )

            except Exception:
                logger.exception(
                    "Unexpected error processing URL",
                    extra={"url": url_str},
                )
                return (
                    PlaygroundNoteRequestResultResource(
                        type="requests",
                        id=request_id,
                        attributes=PlaygroundNoteRequestResultAttributes(
                            request_id=request_id,
                            requested_by=attrs.requested_by,
                            status="FAILED",
                            community_server_id=str(community_server.id),
                            url=url_str,
                            error="Failed to process URL",
                        ),
                    ),
                    False,
                )

        for url in attrs.urls:
            resource, ok = await _process_url(str(url))
            results.append(resource)
            if ok:
                succeeded += 1
            else:
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
    except Exception:
        logger.exception("Failed to create playground note requests")
        await db.rollback()
        return _create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to create playground note requests",
        )
