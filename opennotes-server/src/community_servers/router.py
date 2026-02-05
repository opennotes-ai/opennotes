"""Community servers API endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.community_dependencies import get_community_server_by_platform_id
from src.auth.dependencies import get_current_user_or_api_key
from src.database import get_db
from src.monitoring import get_logger
from src.users.models import User

logger = get_logger(__name__)

router = APIRouter(tags=["community-servers"])


class CommunityServerLookupResponse(BaseModel):
    """Response model for community server lookup."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Internal community server UUID")
    platform: str = Field(..., description="Platform type (e.g., 'discord')")
    platform_community_server_id: str = Field(
        ..., description="Platform-specific ID (e.g., Discord guild ID)"
    )
    name: str = Field(..., description="Community server name")
    is_active: bool = Field(..., description="Whether the community server is active")
    flashpoint_detection_enabled: bool = Field(
        ..., description="Whether flashpoint detection is enabled for this community"
    )


class FlashpointDetectionUpdateRequest(BaseModel):
    """Request model for updating flashpoint detection setting."""

    enabled: bool = Field(
        ..., description="Whether to enable flashpoint detection for this community"
    )


class FlashpointDetectionUpdateResponse(BaseModel):
    """Response model for flashpoint detection update."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Internal community server UUID")
    platform_community_server_id: str = Field(
        ..., description="Platform-specific ID (e.g., Discord guild ID)"
    )
    flashpoint_detection_enabled: bool = Field(
        ..., description="Whether flashpoint detection is enabled"
    )


class WelcomeMessageUpdateRequest(BaseModel):
    """Request model for updating welcome message ID."""

    welcome_message_id: str | None = Field(
        ...,
        description="Discord message ID of the welcome message, or null to clear",
        max_length=30,
    )


class WelcomeMessageUpdateResponse(BaseModel):
    """Response model for welcome message update."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Internal community server UUID")
    platform_community_server_id: str = Field(
        ..., description="Platform-specific ID (e.g., Discord guild ID)"
    )
    welcome_message_id: str | None = Field(
        ..., description="Discord message ID of the welcome message"
    )


@router.get("/community-servers/lookup", response_model=CommunityServerLookupResponse)
async def lookup_community_server(
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    db: Annotated[AsyncSession, Depends(get_db)],
    platform: str = Query("discord", description="Platform type"),
    platform_community_server_id: str = Query(
        ..., description="Platform-specific ID (e.g., Discord guild ID)"
    ),
) -> CommunityServerLookupResponse:
    """
    Look up a community server by platform and platform ID.

    Returns the internal UUID for a community server based on its platform-specific identifier.
    Auto-creates the community server if it doesn't exist (for service accounts/bots).

    Args:
        platform: Platform type (default: "discord")
        platform_community_server_id: Platform-specific ID (e.g., Discord guild ID)

    Returns:
        Community server details including internal UUID

    Raises:
        404: If community server not found and user is not a service account
    """
    logger.info(
        "Looking up community server",
        extra={
            "user_id": current_user.id,
            "platform": platform,
            "platform_community_server_id": platform_community_server_id,
        },
    )

    # Auto-create enabled for service accounts (bots), disabled for regular users
    auto_create = current_user.is_service_account

    community_server = await get_community_server_by_platform_id(
        db=db,
        community_server_id=platform_community_server_id,
        platform=platform,
        auto_create=auto_create,
    )

    # Commit if auto-created (flush happened in get_community_server_by_platform_id)
    if auto_create and community_server:
        await db.commit()

    if not community_server:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Community server not found: {platform}:{platform_community_server_id}",
        )

    return CommunityServerLookupResponse(
        id=community_server.id,
        platform=community_server.platform,
        platform_community_server_id=community_server.platform_community_server_id,
        name=community_server.name,
        is_active=community_server.is_active,
        flashpoint_detection_enabled=community_server.flashpoint_detection_enabled,
    )


@router.patch(
    "/community-servers/{platform_community_server_id}/welcome-message",
    response_model=WelcomeMessageUpdateResponse,
)
async def update_welcome_message(
    platform_community_server_id: str,
    request_body: WelcomeMessageUpdateRequest,
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> WelcomeMessageUpdateResponse:
    """
    Update the welcome message ID for a community server.

    This endpoint is typically called by the Discord bot after posting and pinning
    a welcome message in the bot channel. Only service accounts (bots) can call this.

    Args:
        platform_community_server_id: Platform-specific ID (e.g., Discord guild ID)
        request_body: Contains the welcome_message_id to set (or null to clear)

    Returns:
        Updated community server welcome message info

    Raises:
        401: If not authenticated
        403: If not a service account
        404: If community server not found
    """
    logger.info(
        "Updating welcome message ID",
        extra={
            "user_id": current_user.id,
            "platform_community_server_id": platform_community_server_id,
            "welcome_message_id": request_body.welcome_message_id,
        },
    )

    # Only service accounts can update welcome message ID
    if not current_user.is_service_account:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only service accounts can update welcome message ID",
        )

    community_server = await get_community_server_by_platform_id(
        db=db,
        community_server_id=platform_community_server_id,
        platform="discord",
        auto_create=False,
    )

    if not community_server:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Community server not found: discord:{platform_community_server_id}",
        )

    community_server.welcome_message_id = request_body.welcome_message_id
    await db.commit()
    await db.refresh(community_server)

    logger.info(
        "Welcome message ID updated successfully",
        extra={
            "community_server_id": str(community_server.id),
            "platform_community_server_id": platform_community_server_id,
            "welcome_message_id": community_server.welcome_message_id,
        },
    )

    return WelcomeMessageUpdateResponse(
        id=community_server.id,
        platform_community_server_id=community_server.platform_community_server_id,
        welcome_message_id=community_server.welcome_message_id,
    )


@router.patch(
    "/community-servers/{platform_community_server_id}/flashpoint-detection",
    response_model=FlashpointDetectionUpdateResponse,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Not authorized — requires admin or service account"},
        404: {"description": "Community server not found"},
    },
)
async def update_flashpoint_detection(
    platform_community_server_id: str,
    request_body: FlashpointDetectionUpdateRequest,
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    db: Annotated[AsyncSession, Depends(get_db)],
    platform: str = Query("discord", description="Platform type"),
) -> FlashpointDetectionUpdateResponse:
    """
    Update flashpoint detection setting for a community server.

    This endpoint allows toggling the flashpoint detection feature that monitors
    conversations for potential misinformation escalation points.

    Args:
        platform_community_server_id: Platform-specific ID (e.g., Discord guild ID)
        request_body: Contains the enabled flag
        platform: Platform type (default: "discord")

    Returns:
        Updated flashpoint detection status

    Raises:
        401: If not authenticated
        403: If not authorized (requires admin or service account)
        404: If community server not found
    """
    logger.info(
        "Updating flashpoint detection setting",
        extra={
            "user_id": current_user.id,
            "platform_community_server_id": platform_community_server_id,
            "enabled": request_body.enabled,
            "platform": platform,
        },
    )

    if not current_user.is_service_account:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only service accounts can update flashpoint detection settings",
        )

    community_server = await get_community_server_by_platform_id(
        db=db,
        community_server_id=platform_community_server_id,
        platform=platform,
        auto_create=False,
    )

    if not community_server:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Community server not found: {platform}:{platform_community_server_id}",
        )

    community_server.flashpoint_detection_enabled = request_body.enabled
    await db.commit()
    await db.refresh(community_server)

    logger.info(
        "Flashpoint detection setting updated successfully",
        extra={
            "community_server_id": str(community_server.id),
            "platform_community_server_id": platform_community_server_id,
            "flashpoint_detection_enabled": community_server.flashpoint_detection_enabled,
        },
    )

    return FlashpointDetectionUpdateResponse(
        id=community_server.id,
        platform_community_server_id=community_server.platform_community_server_id,
        flashpoint_detection_enabled=community_server.flashpoint_detection_enabled,
    )
