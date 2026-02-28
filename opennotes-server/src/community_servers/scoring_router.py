from __future__ import annotations

import logging
from typing import Annotated
from uuid import UUID

from dbos._error import (
    DBOSConflictingWorkflowError,
    DBOSQueueDeduplicatedError,
    DBOSWorkflowConflictIDError,
)
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.community_dependencies import verify_community_admin_by_uuid
from src.auth.dependencies import get_current_user_or_api_key
from src.common.responses import AUTHENTICATED_RESPONSES
from src.database import get_db
from src.simulation.workflows.scoring_workflow import dispatch_community_scoring
from src.users.models import User

router = APIRouter(
    prefix="/community-servers",
    tags=["community-scoring"],
    responses=AUTHENTICATED_RESPONSES,
)
logger = logging.getLogger(__name__)

_DBOS_CONFLICT_ERRORS = (
    DBOSWorkflowConflictIDError,
    DBOSConflictingWorkflowError,
    DBOSQueueDeduplicatedError,
)


class ScoreCommunityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    workflow_id: str
    message: str


@router.post(
    "/{community_server_id}/score",
    response_model=ScoreCommunityResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def score_community_server(
    community_server_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    http_request: Request,
) -> ScoreCommunityResponse:
    """Trigger manual scoring for all eligible notes in a community server.

    Admin-only. Dispatches a DBOS workflow and returns the workflow ID.
    Returns 409 if scoring is already in progress.
    """
    await verify_community_admin_by_uuid(community_server_id, current_user, db, http_request)

    try:
        workflow_id = await dispatch_community_scoring(community_server_id)
    except _DBOS_CONFLICT_ERRORS as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Scoring is already in progress for this community server",
        ) from e

    return ScoreCommunityResponse(
        workflow_id=workflow_id,
        message=f"Scoring workflow dispatched for community server {community_server_id}",
    )
