"""
Service layer for managing Request creation with associated MessageArchive.

This service encapsulates the common pattern of creating a MessageArchive
followed by a Request, reducing duplication across tests and application code.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.monitoring import get_logger
from src.notes.message_archive_service import MessageArchiveService
from src.notes.models import Request

logger = get_logger(__name__)


class RequestService:
    """Service for creating Requests with their associated MessageArchives."""

    @staticmethod
    async def create_from_message(
        db: AsyncSession,
        request_id: str,
        content: str,
        community_server_id: UUID,
        requested_by: str,
        platform_message_id: str | None = None,
        platform_channel_id: str | None = None,
        platform_author_id: str | None = None,
        platform_timestamp: datetime | None = None,
        dataset_item_id: str | None = None,
        similarity_score: float | None = None,
        dataset_name: str | None = None,
        status: str = "PENDING",
        priority: str | None = None,
        reason: str | None = None,
        note_id: UUID | None = None,
        request_metadata: dict[str, Any] | None = None,
    ) -> Request:
        """
        Create a Request with its associated MessageArchive in a single operation.

        This method encapsulates the common pattern of:
        1. Creating a MessageArchive from text content
        2. Creating a Request that references the MessageArchive

        Args:
            db: Database session
            request_id: Unique request identifier
            content: Message content text
            community_server_id: Community server UUID
            requested_by: User who requested the note
            platform_message_id: Platform message ID (optional)
            platform_channel_id: Platform channel ID (optional)
            platform_author_id: Platform author ID (optional)
            platform_timestamp: Platform message timestamp (optional)
            dataset_item_id: Fact-check item UUID (optional, for AI generation)
            similarity_score: Match similarity score (optional)
            dataset_name: Dataset name (optional)
            status: Request status (default: PENDING)
            priority: Request priority (optional)
            reason: Request reason (optional)
            note_id: Associated note ID (optional)
            request_metadata: Additional metadata (optional)

        Returns:
            Created Request object with message_archive relationship loaded

        Raises:
            IntegrityError: If request_id already exists or FK constraints fail
            ValueError: If required parameters are invalid

        Example:
            >>> request = await RequestService.create_from_message(
            ...     db=db_session,
            ...     request_id="req_test_1",
            ...     content="Test message",
            ...     community_server_id=community_server.id,
            ...     requested_by="test_user",
            ...     platform_message_id="1234567890",
            ...     dataset_item_id=str(fact_check_item.id),
            ...     similarity_score=0.85,
            ...     dataset_name="snopes",
            ... )
            >>> await db_session.commit()
        """
        # Create message archive first
        message_archive = await MessageArchiveService.create_from_text(
            db=db,
            content=content,
            platform_message_id=platform_message_id,
            platform_channel_id=platform_channel_id,
            platform_author_id=platform_author_id,
            platform_timestamp=platform_timestamp,
        )

        logger.debug(
            "Created message archive for request",
            extra={
                "request_id": request_id,
                "message_archive_id": str(message_archive.id),
                "content_length": len(content),
            },
        )

        # Create request with message archive reference
        request = Request(
            request_id=request_id,
            community_server_id=community_server_id,
            message_archive_id=message_archive.id,
            requested_by=requested_by,
            status=status,
            dataset_item_id=dataset_item_id,
            similarity_score=similarity_score,
            dataset_name=dataset_name,
            priority=priority,
            reason=reason,
            note_id=note_id,
            request_metadata=request_metadata or {},
        )
        db.add(request)
        await db.flush()  # Get IDs without committing
        await db.refresh(request)

        logger.info(
            "Created request with message archive",
            extra={
                "request_id": request_id,
                "message_archive_id": str(message_archive.id),
                "status": status,
                "has_dataset": dataset_item_id is not None,
            },
        )

        return request
