"""API endpoints for previously seen message detection."""

from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_user_or_api_key
from src.config import settings
from src.database import get_db
from src.fact_checking.embedding_service import EmbeddingService
from src.fact_checking.monitored_channel_models import MonitoredChannel
from src.fact_checking.previously_seen_schemas import PreviouslySeenMessageMatch
from src.fact_checking.threshold_helpers import get_previously_seen_thresholds
from src.llm_config.encryption import EncryptionService
from src.llm_config.manager import LLMClientManager
from src.llm_config.models import CommunityServer
from src.llm_config.service import LLMService
from src.monitoring import get_logger
from src.users.models import User

logger = get_logger(__name__)

router = APIRouter(prefix="/previously-seen", tags=["previously-seen"])


@lru_cache
def get_encryption_service() -> EncryptionService:
    """Get or create thread-safe encryption service singleton."""
    return EncryptionService(settings.ENCRYPTION_MASTER_KEY)


@lru_cache
def get_llm_service(
    encryption_service: Annotated[EncryptionService, Depends(get_encryption_service)],
) -> LLMService:
    """Get or create LLM service singleton."""
    client_manager = LLMClientManager(encryption_service)
    return LLMService(client_manager)


def get_embedding_service(
    llm_service: Annotated[LLMService, Depends(get_llm_service)],
) -> EmbeddingService:
    """Get embedding service with LLM service dependency."""
    return EmbeddingService(llm_service)


class PreviouslySeenCheckRequest(BaseModel):
    """Request to check for previously seen messages."""

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    message_text: str = Field(
        ...,
        alias="messageText",
        description="Message text to check",
        min_length=1,
        max_length=50000,
    )
    guild_id: str = Field(..., alias="guildId", description="Discord guild ID", max_length=64)
    channel_id: str = Field(..., alias="channelId", description="Discord channel ID", max_length=64)


class PreviouslySeenCheckResponse(BaseModel):
    """Response with previously seen message matches and action recommendations."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    should_auto_publish: bool = Field(
        ..., alias="shouldAutoPublish", description="Whether to auto-publish existing note"
    )
    should_auto_request: bool = Field(
        ..., alias="shouldAutoRequest", description="Whether to auto-request new note"
    )
    autopublish_threshold: float = Field(
        ..., alias="autopublishThreshold", description="Threshold used for auto-publish decision"
    )
    autorequest_threshold: float = Field(
        ..., alias="autorequestThreshold", description="Threshold used for auto-request decision"
    )
    matches: list[PreviouslySeenMessageMatch] = Field(
        ..., description="Matching previously seen messages (ordered by similarity)"
    )
    top_match: PreviouslySeenMessageMatch | None = Field(
        None, alias="topMatch", description="Best matching message if any"
    )


@router.post("/check", status_code=status.HTTP_200_OK)
async def check_previously_seen(
    request: PreviouslySeenCheckRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user_or_api_key)],
    embedding_service: Annotated[EmbeddingService, Depends(get_embedding_service)],
) -> PreviouslySeenCheckResponse:
    """
    Check if a message has been seen before and get action recommendations.

    This endpoint:
    1. Generates an embedding for the message text
    2. Searches for similar previously seen messages
    3. Resolves thresholds (channel override or global config)
    4. Returns action recommendations (auto-publish/auto-request)

    Auto-publish (default 0.9): High similarity - automatically reply with existing note
    Auto-request (default 0.75): Moderate similarity - trigger auto-request for new note
    """
    try:
        # Get community server UUID from platform_id
        result = await db.execute(
            select(CommunityServer.id).where(CommunityServer.platform_id == request.guild_id)
        )
        community_server_uuid = result.scalar_one_or_none()

        if not community_server_uuid:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Community server not found: {request.guild_id}",
            )

        # Get monitored channel config to resolve thresholds
        monitored_channel_result = await db.execute(
            select(MonitoredChannel).where(
                MonitoredChannel.community_server_id == request.guild_id,
                MonitoredChannel.channel_id == request.channel_id,
            )
        )
        monitored_channel = monitored_channel_result.scalar_one_or_none()

        # Resolve thresholds (use channel override if set, else config default)
        autopublish_threshold, autorequest_threshold = get_previously_seen_thresholds(
            monitored_channel
        )

        logger.debug(
            "Checking previously seen messages",
            extra={
                "guild_id": request.guild_id,
                "channel_id": request.channel_id,
                "autopublish_threshold": autopublish_threshold,
                "autorequest_threshold": autorequest_threshold,
                "text_length": len(request.message_text),
            },
        )

        # Generate embedding for message
        embedding = await embedding_service.generate_embedding(
            db=db, text=request.message_text, community_server_id=request.guild_id
        )

        # Search for previously seen messages at the lower threshold (auto-request)
        # This returns all matches >= autorequest_threshold
        matches = await embedding_service.search_previously_seen(
            db=db,
            embedding=embedding,
            community_server_id=community_server_uuid,
            similarity_threshold=autorequest_threshold,
            limit=5,
        )

        # Determine actions based on top match
        should_auto_publish = False
        should_auto_request = False
        top_match = None

        if matches:
            top_match = matches[0]  # Highest similarity
            top_score = top_match.similarity_score

            # Auto-publish takes precedence (higher threshold)
            if top_score >= autopublish_threshold:
                should_auto_publish = True
                logger.info(
                    "Auto-publish recommended for previously seen message",
                    extra={
                        "guild_id": request.guild_id,
                        "channel_id": request.channel_id,
                        "similarity_score": top_score,
                        "autopublish_threshold": autopublish_threshold,
                        "published_note_id": top_match.published_note_id,
                    },
                )
            # Auto-request if above threshold but below auto-publish
            elif top_score >= autorequest_threshold:
                should_auto_request = True
                logger.info(
                    "Auto-request recommended for similar previously seen message",
                    extra={
                        "guild_id": request.guild_id,
                        "channel_id": request.channel_id,
                        "similarity_score": top_score,
                        "autorequest_threshold": autorequest_threshold,
                        "published_note_id": top_match.published_note_id,
                    },
                )

        return PreviouslySeenCheckResponse.model_validate(
            {
                "should_auto_publish": should_auto_publish,
                "should_auto_request": should_auto_request,
                "autopublish_threshold": autopublish_threshold,
                "autorequest_threshold": autorequest_threshold,
                "matches": matches,
                "top_match": top_match,
            },
            from_attributes=False,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to check previously seen messages",
            extra={
                "guild_id": request.guild_id,
                "channel_id": request.channel_id,
                "error": str(e),
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to check previously seen messages",
        ) from e
