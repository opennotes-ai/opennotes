from __future__ import annotations

import ipaddress
import socket
from typing import Annotated
from urllib.parse import urlparse
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

SSRF_ALLOWED_SCHEMES = {"http", "https"}

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
    status_code=status.HTTP_202_ACCEPTED,
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
        urls = [str(u) for u in attrs.urls]

        workflow_id = await dispatch_playground_url_extraction(
            urls=urls,
            community_server_id=community_server.id,
            requested_by=attrs.requested_by,
        )

        response = PlaygroundNoteRequestJobResponse(
            data=PlaygroundNoteRequestJobResource(
                id=workflow_id,
                attributes=PlaygroundNoteRequestJobAttributes(
                    workflow_id=workflow_id,
                    url_count=len(urls),
                ),
            ),
        )

        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
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
