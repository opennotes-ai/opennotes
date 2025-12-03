from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.community_dependencies import verify_community_admin
from src.auth.dependencies import get_current_user_or_api_key
from src.database import get_db
from src.fact_checking.monitored_channel_models import MonitoredChannel
from src.fact_checking.monitored_channel_schemas import (
    MonitoredChannelCreate,
    MonitoredChannelListResponse,
    MonitoredChannelResponse,
    MonitoredChannelUpdate,
)
from src.monitoring import get_logger
from src.users.models import User

logger = get_logger(__name__)

router = APIRouter(tags=["monitored-channels"])


@router.get("/monitored-channels", response_model=MonitoredChannelListResponse)
async def list_monitored_channels(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    db: AsyncSession = Depends(get_db),
    community_server_id: str | None = Query(
        None,
        description="Filter by community server ID (platform ID, e.g., Discord guild ID). Required - user must be admin of this server.",
    ),
    enabled_only: bool = Query(False, description="Only return enabled channels"),
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(20, ge=1, le=100, description="Items per page"),
) -> MonitoredChannelListResponse:
    """
    List monitored channel configurations for a specific community server.

    Requires the community_server_id parameter and user must be an admin or moderator
    of that community server to view its monitored channels.

    Returns paginated results filtered by community server and optionally by enabled status.
    """
    # Authorization: community_server_id is required and user must be admin
    if not community_server_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="community_server_id is required to list monitored channels",
        )

    # Verify user is admin of the community server
    await verify_community_admin(community_server_id, current_user, db, request)

    logger.debug(
        f"User {current_user.id} listing monitored channels for server {community_server_id}"
    )

    # Build query
    query = select(MonitoredChannel).where(
        MonitoredChannel.community_server_id == community_server_id
    )

    if enabled_only:
        query = query.where(MonitoredChannel.enabled == True)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply pagination
    query = query.offset((page - 1) * size).limit(size)

    result = await db.execute(query)
    channels = result.scalars().all()

    return MonitoredChannelListResponse(
        channels=[MonitoredChannelResponse.model_validate(ch) for ch in channels],
        total=total,
        page=page,
        size=size,
    )


@router.get("/monitored-channels/{channel_id}", response_model=MonitoredChannelResponse)
async def get_monitored_channel(
    channel_id: str,
    request: Request,
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    db: AsyncSession = Depends(get_db),
) -> MonitoredChannelResponse:
    """
    Get configuration for a specific monitored channel.

    Requires user to be an admin or moderator of the community server that owns the channel.
    Returns 404 if the channel is not monitored.
    Returns 403 if the user is not authorized to access this channel.
    """
    logger.debug(f"User {current_user.id} getting monitored channel {channel_id}")

    result = await db.execute(
        select(MonitoredChannel).where(MonitoredChannel.channel_id == channel_id)
    )
    channel = result.scalar_one_or_none()

    if not channel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Channel {channel_id} is not monitored"
        )

    # Verify user is admin of the community server that owns this channel
    await verify_community_admin(channel.community_server_id, current_user, db, request)

    return MonitoredChannelResponse.model_validate(channel)


@router.post(
    "/monitored-channels",
    response_model=MonitoredChannelResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_monitored_channel(
    http_request: Request,
    request: MonitoredChannelCreate,
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    db: AsyncSession = Depends(get_db),
) -> MonitoredChannelResponse:
    """
    Create a new monitored channel configuration.

    Requires user to be an admin or moderator of the community server.
    Returns 409 if channel is already monitored.
    Returns 403 if user is not authorized to manage this community server.
    """
    # Verify user is admin of the community server
    await verify_community_admin(request.community_server_id, current_user, db, http_request)

    logger.info(
        f"User {current_user.id} creating monitored channel {request.channel_id} "
        f"in server {request.community_server_id}"
    )

    # Check if channel already monitored
    result = await db.execute(
        select(MonitoredChannel).where(MonitoredChannel.channel_id == request.channel_id)
    )
    existing = result.scalar_one_or_none()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Channel {request.channel_id} is already monitored",
        )

    # Create new monitored channel
    new_channel = MonitoredChannel(
        community_server_id=request.community_server_id,
        channel_id=request.channel_id,
        enabled=request.enabled,
        similarity_threshold=request.similarity_threshold,
        dataset_tags=request.dataset_tags,
        previously_seen_autopublish_threshold=request.previously_seen_autopublish_threshold,
        previously_seen_autorequest_threshold=request.previously_seen_autorequest_threshold,
        updated_by=request.updated_by,
    )

    db.add(new_channel)
    await db.commit()
    await db.refresh(new_channel)

    return MonitoredChannelResponse.model_validate(new_channel)


@router.patch("/monitored-channels/{channel_id}", response_model=MonitoredChannelResponse)
async def update_monitored_channel(
    channel_id: str,
    http_request: Request,
    request: MonitoredChannelUpdate,
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    db: AsyncSession = Depends(get_db),
) -> MonitoredChannelResponse:
    """
    Update configuration for a monitored channel.

    Requires user to be an admin or moderator of the community server that owns the channel.
    Only provided fields are updated.
    Returns 404 if channel is not monitored.
    Returns 403 if user is not authorized to manage this channel.
    """
    logger.info(f"User {current_user.id} updating monitored channel {channel_id}")

    result = await db.execute(
        select(MonitoredChannel).where(MonitoredChannel.channel_id == channel_id)
    )
    channel = result.scalar_one_or_none()

    if not channel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Channel {channel_id} is not monitored"
        )

    # Verify user is admin of the community server that owns this channel
    await verify_community_admin(channel.community_server_id, current_user, db, http_request)

    # Update fields if provided
    if request.enabled is not None:
        channel.enabled = request.enabled
    if request.similarity_threshold is not None:
        channel.similarity_threshold = request.similarity_threshold
    if request.dataset_tags is not None:
        channel.dataset_tags = request.dataset_tags
    if request.previously_seen_autopublish_threshold is not None:
        channel.previously_seen_autopublish_threshold = (
            request.previously_seen_autopublish_threshold
        )
    if request.previously_seen_autorequest_threshold is not None:
        channel.previously_seen_autorequest_threshold = (
            request.previously_seen_autorequest_threshold
        )
    if request.updated_by is not None:
        channel.updated_by = request.updated_by

    await db.commit()
    await db.refresh(channel)

    return MonitoredChannelResponse.model_validate(channel)


@router.delete("/monitored-channels/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_monitored_channel(
    channel_id: str,
    http_request: Request,
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Remove a channel from monitoring.

    Requires user to be an admin or moderator of the community server that owns the channel.
    Returns 404 if channel is not monitored.
    Returns 403 if user is not authorized to manage this channel.
    """
    logger.info(f"User {current_user.id} deleting monitored channel {channel_id}")

    # First, fetch the channel to verify it exists and get the community_server_id
    result = await db.execute(
        select(MonitoredChannel).where(MonitoredChannel.channel_id == channel_id)
    )
    channel = result.scalar_one_or_none()

    if not channel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Channel {channel_id} is not monitored"
        )

    # Verify user is admin of the community server that owns this channel
    await verify_community_admin(channel.community_server_id, current_user, db, http_request)

    # Now delete the channel
    await db.execute(delete(MonitoredChannel).where(MonitoredChannel.channel_id == channel_id))

    await db.commit()
