from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi import Request as HTTPRequest
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.community_dependencies import verify_community_membership
from src.auth.dependencies import get_current_user_or_api_key
from src.auth.permissions import is_service_account
from src.database import get_db
from src.fact_checking.previously_seen_service import PreviouslySeenService
from src.llm_config.models import CommunityServer
from src.monitoring import get_logger
from src.notes.models import Note, Request
from src.notes.note_publisher_models import NotePublisherConfig, NotePublisherPost
from src.users.models import User

logger = get_logger(__name__)

router = APIRouter(prefix="/note-publisher", tags=["note-publisher"])


class NotePublisherConfigRequest(BaseModel):
    community_server_id: str = Field(..., max_length=64)
    channel_id: str | None = Field(None, max_length=64)
    enabled: bool
    threshold: float | None = Field(None, ge=0.0, le=1.0)
    updated_by: str | None = Field(None, max_length=64)


class NotePublisherConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    community_server_id: str
    channel_id: str | None
    enabled: bool
    threshold: float | None
    updated_at: str
    updated_by: str | None


class NotePublisherRecordRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    noteId: str = Field(..., alias="noteId", description="UUID of the published note")
    originalMessageId: str = Field(..., max_length=64, alias="originalMessageId")
    channelId: str = Field(..., max_length=64, alias="channelId")
    guildId: str = Field(..., max_length=64, alias="guildId")
    scoreAtPost: float = Field(..., alias="scoreAtPost")
    confidenceAtPost: str = Field(..., max_length=32, alias="confidenceAtPost")
    success: bool
    errorMessage: str | None = Field(None, alias="errorMessage")
    messageEmbedding: list[float] | None = Field(None, alias="messageEmbedding")
    embeddingProvider: str | None = Field(None, alias="embeddingProvider", max_length=50)
    embeddingModel: str | None = Field(None, alias="embeddingModel", max_length=100)


class DuplicateCheckResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    exists: bool
    note_publisher_post_id: str | None = None


class LastPostResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    posted_at: str
    note_id: str
    channel_id: str


@router.post("/config", status_code=status.HTTP_200_OK)
async def set_note_publisher_config(
    request: NotePublisherConfigRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user_or_api_key),
) -> NotePublisherConfigResponse:
    """
    Create or update auto-post configuration for a server or channel.

    Channel-specific configs (channel_id set) override server-wide configs (channel_id=None).
    """
    try:
        stmt = select(NotePublisherConfig).where(
            NotePublisherConfig.community_server_id == request.community_server_id,
            NotePublisherConfig.channel_id == request.channel_id,
        )
        result = await db.execute(stmt)
        config = result.scalar_one_or_none()

        if config:
            config.enabled = request.enabled
            if request.threshold is not None:
                config.threshold = request.threshold
            config.updated_at = datetime.now(UTC)
            if request.updated_by:
                config.updated_by = request.updated_by
        else:
            config = NotePublisherConfig(
                community_server_id=request.community_server_id,
                channel_id=request.channel_id,
                enabled=request.enabled,
                threshold=request.threshold,
                updated_by=request.updated_by,
            )
            db.add(config)

        await db.commit()
        await db.refresh(config)

        logger.info(
            "Auto-post config updated",
            extra={
                "community_server_id": request.community_server_id,
                "channel_id": request.channel_id,
                "enabled": request.enabled,
                "threshold": request.threshold,
            },
        )

        return NotePublisherConfigResponse(
            id=str(config.id),
            community_server_id=config.community_server_id,
            channel_id=config.channel_id,
            enabled=config.enabled,
            threshold=config.threshold,
            updated_at=config.updated_at.isoformat(),
            updated_by=config.updated_by,
        )

    except Exception as e:
        logger.error(f"Failed to set auto-post config: {e}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update configuration",
        )


@router.get("/config", status_code=status.HTTP_200_OK)
async def get_note_publisher_config(
    request: HTTPRequest,
    community_server_id: str = Query(..., max_length=64),
    channel_id: str | None = Query(None, max_length=64),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_or_api_key),
) -> NotePublisherConfigResponse:
    """
    Get auto-post configuration for a server or channel.

    Users can only view config for communities they are members of.
    Service accounts can view all configs.

    If channel_id is provided, returns channel-specific config if it exists,
    otherwise returns server-wide config.
    """
    try:
        # Verify community membership (service accounts bypass)
        if not is_service_account(current_user):
            await verify_community_membership(community_server_id, current_user, db, request)

        stmt = select(NotePublisherConfig).where(
            NotePublisherConfig.community_server_id == community_server_id,
            NotePublisherConfig.channel_id == channel_id,
        )
        result = await db.execute(stmt)
        config = result.scalar_one_or_none()

        if not config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Configuration not found",
            )

        return NotePublisherConfigResponse(
            id=str(config.id),
            community_server_id=config.community_server_id,
            channel_id=config.channel_id,
            enabled=config.enabled,
            threshold=config.threshold,
            updated_at=config.updated_at.isoformat(),
            updated_by=config.updated_by,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get auto-post config: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve configuration",
        )


@router.post("/record", status_code=status.HTTP_201_CREATED)
async def record_note_publisher(
    request: NotePublisherRecordRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user_or_api_key),
) -> dict[str, str]:
    """
    Record an auto-post attempt (successful or failed) for audit trail.

    If the post was successful and embedding data is provided, also stores
    the message embedding for duplicate detection.
    """
    try:
        note_publisher_post = NotePublisherPost(
            note_id=UUID(request.noteId),
            original_message_id=request.originalMessageId,
            auto_post_message_id=request.originalMessageId if request.success else None,
            channel_id=request.channelId,
            community_server_id=request.guildId,
            score_at_post=request.scoreAtPost,
            confidence_at_post=request.confidenceAtPost,
            success=request.success,
            error_message=request.errorMessage,
        )

        db.add(note_publisher_post)

        if request.success:
            note_result = await db.execute(select(Note).where(Note.id == UUID(request.noteId)))
            note = note_result.scalar_one_or_none()
            if note and note.request_id:
                request_result = await db.execute(
                    select(Request).where(Request.request_id == note.request_id)
                )
                associated_request = request_result.scalar_one_or_none()
                if associated_request:
                    associated_request.status = "COMPLETED"
                    logger.info(
                        "Updated request status to COMPLETED for published note",
                        extra={
                            "request_id": note.request_id,
                            "note_id": request.noteId,
                        },
                    )

        await db.commit()
        await db.refresh(note_publisher_post)

        logger.info(
            "Recorded auto-post attempt",
            extra={
                "note_id": request.noteId,
                "success": request.success,
                "original_message_id": request.originalMessageId,
            },
        )

        # Store embedding for duplicate detection if available and post was successful
        if request.success and request.messageEmbedding:
            # Get community_server_id UUID from platform_id (Discord guild ID)
            result = await db.execute(
                select(CommunityServer.id).where(CommunityServer.platform_id == request.guildId)
            )
            community_server_uuid = result.scalar_one_or_none()

            if community_server_uuid:
                previously_seen_service = PreviouslySeenService()
                await previously_seen_service.store_message_embedding(
                    db=db,
                    community_server_id=community_server_uuid,
                    original_message_id=request.originalMessageId,
                    published_note_id=UUID(request.noteId),
                    embedding=request.messageEmbedding,
                    embedding_provider=request.embeddingProvider,
                    embedding_model=request.embeddingModel,
                    extra_metadata={
                        "channel_id": request.channelId,
                        "score_at_post": request.scoreAtPost,
                        "confidence_at_post": request.confidenceAtPost,
                    },
                )
            else:
                logger.warning(
                    "Community server not found for embedding storage",
                    extra={"guild_id": request.guildId},
                )

        return {
            "id": str(note_publisher_post.id),
            "recorded_at": note_publisher_post.posted_at.isoformat(),
        }

    except Exception as e:
        logger.error(f"Failed to record auto-post: {e}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record auto-post attempt",
        )


@router.get("/check-duplicate/{original_message_id}", status_code=status.HTTP_200_OK)
async def check_duplicate(
    original_message_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user_or_api_key),
) -> DuplicateCheckResponse:
    """
    Check if an auto-post already exists for the given original message ID.
    """
    try:
        stmt = select(NotePublisherPost).where(
            NotePublisherPost.original_message_id == original_message_id
        )
        result = await db.execute(stmt)
        note_publisher_post = result.scalar_one_or_none()

        if note_publisher_post:
            return DuplicateCheckResponse(
                exists=True, note_publisher_post_id=str(note_publisher_post.id)
            )

        return DuplicateCheckResponse(exists=False)

    except Exception as e:
        logger.error(f"Failed to check duplicate: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to check for duplicate",
        )


@router.get("/last-post/{channel_id}", status_code=status.HTTP_200_OK)
async def get_last_post(
    channel_id: str,
    request: HTTPRequest,
    community_server_id: str = Query(
        ..., max_length=64, description="Discord guild ID for membership verification"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_or_api_key),
) -> LastPostResponse:
    """
    Get the most recent auto-post in a channel (for cooldown checking).

    Users can only view posts for communities they are members of.
    Service accounts can view all posts.

    Requires community_server_id query parameter for membership verification.
    """
    try:
        # Verify community membership (service accounts bypass)
        if not is_service_account(current_user):
            await verify_community_membership(community_server_id, current_user, db, request)

        stmt = (
            select(NotePublisherPost)
            .where(
                NotePublisherPost.channel_id == channel_id,
                NotePublisherPost.community_server_id == community_server_id,
                NotePublisherPost.success == True,
            )
            .order_by(NotePublisherPost.posted_at.desc())
            .limit(1)
        )
        result = await db.execute(stmt)
        note_publisher_post = result.scalar_one_or_none()

        if not note_publisher_post:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No auto-posts found in this channel",
            )

        return LastPostResponse(
            posted_at=note_publisher_post.posted_at.isoformat(),
            note_id=str(note_publisher_post.note_id),
            channel_id=note_publisher_post.channel_id,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get last post: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve last post",
        )
