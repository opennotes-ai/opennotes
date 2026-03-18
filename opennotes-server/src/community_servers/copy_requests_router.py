from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import require_superuser_or_service_account
from src.common.base_schemas import StrictInputSchema
from src.common.responses import AUTHENTICATED_RESPONSES
from src.database import get_db
from src.dbos_workflows.copy_requests_workflow import dispatch_copy_requests
from src.llm_config.models import CommunityServer
from src.monitoring import get_logger
from src.users.models import User

logger = get_logger(__name__)

router = APIRouter(tags=["community-servers"], responses=AUTHENTICATED_RESPONSES)


class CopyRequestsAttributes(StrictInputSchema):
    source_community_server_id: UUID = Field(
        ..., description="Source community server to copy requests from"
    )


class CopyRequestsData(StrictInputSchema):
    type: str = Field("copy-requests")
    attributes: CopyRequestsAttributes


class CopyRequestsPayload(StrictInputSchema):
    data: CopyRequestsData


@router.post(
    "/community-servers/{community_server_id}/copy-requests",
    status_code=status.HTTP_202_ACCEPTED,
)
async def copy_requests(
    community_server_id: UUID,
    payload: CopyRequestsPayload,
    current_user: Annotated[User, Depends(require_superuser_or_service_account)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    source_id = payload.data.attributes.source_community_server_id

    target_result = await db.execute(
        select(CommunityServer).where(
            CommunityServer.id == community_server_id,
        )
    )
    if target_result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Target community server {community_server_id} not found",
        )

    source_result = await db.execute(
        select(CommunityServer).where(
            CommunityServer.id == source_id,
        )
    )
    if source_result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source community server {source_id} not found",
        )

    batch_job_id = await dispatch_copy_requests(
        db=db,
        source_community_server_id=source_id,
        target_community_server_id=community_server_id,
    )

    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={
            "data": {
                "type": "batch-jobs",
                "id": str(batch_job_id),
                "attributes": {
                    "job_type": "copy:requests",
                    "status": "pending",
                },
            }
        },
        media_type="application/vnd.api+json",
    )
