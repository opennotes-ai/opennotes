"""JSON:API v2 router for ModerationAction resources.

Provides CRUD endpoints for moderation actions with JSON:API 1.1 response
envelopes and NATS event emission on create and state transitions.

Endpoints:
- POST   /api/v2/moderation-actions        Create (PROPOSED state)
- GET    /api/v2/moderation-actions/{id}   Fetch single action
- GET    /api/v2/moderation-actions        List with optional filters
- PATCH  /api/v2/moderation-actions/{id}   State transition
"""

from __future__ import annotations

from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_user_or_api_key
from src.common.jsonapi import JSONAPI_CONTENT_TYPE, create_error_response
from src.common.responses import AUTHENTICATED_RESPONSES
from src.database import get_db
from src.events.publisher import event_publisher
from src.moderation_actions.crud import (
    create_moderation_action,
    get_moderation_action,
    list_moderation_actions,
    update_moderation_action_state,
)
from src.moderation_actions.models import ActionState, ActionTier
from src.moderation_actions.schemas import (
    ModerationActionCreate,
    ModerationActionRead,
    ModerationActionUpdate,
)
from src.monitoring import get_logger
from src.users.models import User

logger = get_logger(__name__)

router = APIRouter(
    prefix="/moderation-actions",
    tags=["moderation-actions"],
    responses=AUTHENTICATED_RESPONSES,
)


class ModerationActionResource(BaseModel):
    type: Literal["moderation-actions"] = "moderation-actions"
    id: str
    attributes: ModerationActionRead

    model_config = {"from_attributes": True}


class ModerationActionSingleResponse(BaseModel):
    data: ModerationActionResource
    jsonapi: dict[str, str] = {"version": "1.1"}


class ModerationActionListResponse(BaseModel):
    data: list[ModerationActionResource]
    jsonapi: dict[str, str] = {"version": "1.1"}
    meta: dict[str, Any] = {}


def _to_resource(action: Any) -> ModerationActionResource:
    return ModerationActionResource(
        id=str(action.id),
        attributes=ModerationActionRead.model_validate(action),
    )


def _single_response(action: Any) -> dict[str, Any]:
    return ModerationActionSingleResponse(data=_to_resource(action)).model_dump(mode="json")


def _list_response(actions: list[Any]) -> dict[str, Any]:
    return ModerationActionListResponse(
        data=[_to_resource(a) for a in actions],
        meta={"count": len(actions)},
    ).model_dump(mode="json")


async def _publish_for_state(action: Any, target_state: ActionState) -> None:
    action_id = action.id
    request_id = action.request_id
    action_type = action.action_type
    community_server_id = action.community_server_id

    if target_state == ActionState.APPLIED:
        await event_publisher.publish_moderation_action_applied(
            action_id=action_id,
            request_id=request_id,
            action_type=action_type,
            community_server_id=community_server_id,
            platform_action_id=action.platform_action_id,
        )
    elif target_state == ActionState.RETRO_REVIEW:
        await event_publisher.publish_moderation_action_retro_review_started(
            action_id=action_id,
            request_id=request_id,
            action_type=action_type,
            community_server_id=community_server_id,
        )
    elif target_state == ActionState.CONFIRMED:
        await event_publisher.publish_moderation_action_confirmed(
            action_id=action_id,
            request_id=request_id,
            action_type=action_type,
            community_server_id=community_server_id,
        )
    elif target_state == ActionState.OVERTURNED:
        await event_publisher.publish_moderation_action_overturned(
            action_id=action_id,
            request_id=request_id,
            action_type=action_type,
            community_server_id=community_server_id,
            overturned_reason=action.overturned_reason,
        )
    elif target_state == ActionState.DISMISSED:
        await event_publisher.publish_moderation_action_dismissed(
            action_id=action_id,
            request_id=request_id,
            action_type=action_type,
            community_server_id=community_server_id,
        )


@router.post("", response_class=JSONResponse, status_code=status.HTTP_201_CREATED)
async def create_moderation_action_endpoint(
    body: ModerationActionCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> JSONResponse:
    """Create a moderation action in PROPOSED state.

    Publishes a moderation_action.proposed NATS event after successful creation.
    """
    try:
        action = await create_moderation_action(db, body)
    except Exception as e:
        logger.exception(f"Failed to create moderation action: {e}")
        error = create_error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            title="Internal Server Error",
            detail="Failed to create moderation action",
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error.model_dump(by_alias=True),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    try:
        await event_publisher.publish_moderation_action_proposed(
            action_id=action.id,
            request_id=action.request_id,
            action_type=action.action_type,
            action_tier=action.action_tier,
            classifier_evidence=action.classifier_evidence or {},
            review_group=action.review_group,
            community_server_id=action.community_server_id,
        )
    except Exception as e:
        logger.error(f"Failed to publish moderation_action.proposed event: {e}")

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=_single_response(action),
        media_type=JSONAPI_CONTENT_TYPE,
    )


@router.get("/{action_id}", response_class=JSONResponse)
async def get_moderation_action_endpoint(
    action_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> JSONResponse:
    """Fetch a single moderation action by UUID."""
    action = await get_moderation_action(db, action_id)
    if action is None:
        error = create_error_response(
            status_code=status.HTTP_404_NOT_FOUND,
            title="Not Found",
            detail=f"ModerationAction {action_id} not found",
        )
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=error.model_dump(by_alias=True),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=_single_response(action),
        media_type=JSONAPI_CONTENT_TYPE,
    )


@router.get("", response_class=JSONResponse)
async def list_moderation_actions_endpoint(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    community_server_id: UUID | None = None,
    action_state: ActionState | None = None,
    action_tier: ActionTier | None = None,
    limit: int = 50,
    offset: int = 0,
) -> JSONResponse:
    """List moderation actions with optional filters.

    Query params:
    - community_server_id: filter by community
    - action_state: filter by state (e.g. proposed, applied)
    - action_tier: filter by tier
    - limit: max results (default 50)
    - offset: pagination offset (default 0)
    """
    actions = await list_moderation_actions(
        db=db,
        community_server_id=community_server_id,
        action_state=action_state,
        action_tier=action_tier,
        limit=limit,
        offset=offset,
    )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=_list_response(actions),
        media_type=JSONAPI_CONTENT_TYPE,
    )


@router.patch("/{action_id}", response_class=JSONResponse)
async def patch_moderation_action_endpoint(
    action_id: UUID,
    body: ModerationActionUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> JSONResponse:
    """Transition a moderation action to a new state.

    Validates the state transition against VALID_TRANSITIONS and returns 422
    on invalid transitions.  Publishes a NATS event for all target states
    except scan_exempt (plugin-initiated acknowledgement, no event needed).
    """
    existing = await get_moderation_action(db, action_id)
    if existing is None:
        error = create_error_response(
            status_code=status.HTTP_404_NOT_FOUND,
            title="Not Found",
            detail=f"ModerationAction {action_id} not found",
        )
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=error.model_dump(by_alias=True),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    try:
        action = await update_moderation_action_state(db, action_id, body)
    except ValueError as e:
        error = create_error_response(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            title="Unprocessable Entity",
            detail=str(e),
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=error.model_dump(by_alias=True),
            media_type=JSONAPI_CONTENT_TYPE,
        )
    except Exception as e:
        logger.exception(f"Failed to update moderation action state: {e}")
        error = create_error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            title="Internal Server Error",
            detail="Failed to update moderation action",
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error.model_dump(by_alias=True),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    target_state = ActionState(action.action_state)
    if target_state != ActionState.SCAN_EXEMPT:
        try:
            await _publish_for_state(action, target_state)
        except Exception as e:
            logger.error(f"Failed to publish moderation_action event for state {target_state}: {e}")

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=_single_response(action),
        media_type=JSONAPI_CONTENT_TYPE,
    )
