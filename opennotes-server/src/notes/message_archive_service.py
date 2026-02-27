from datetime import datetime
from typing import TYPE_CHECKING, Literal
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.monitoring import get_logger
from src.notes import loaders as note_loaders
from src.notes.message_archive_models import ContentType, MessageArchive
from src.notes.message_archive_schemas import MessageArchiveCreate
from src.notes.models import Note, Request

if TYPE_CHECKING:
    from src.services.vision_service import VisionService

logger = get_logger(__name__)


class MessageArchiveService:
    """
    Service layer for managing message archive CRUD operations.

    Handles creation, retrieval, and soft deletion of message archives.
    All methods use SQLAlchemy 2.0 async patterns.
    """

    @staticmethod
    async def create(db: AsyncSession, data: MessageArchiveCreate) -> MessageArchive:
        """
        Create a new message archive from Pydantic schema.

        Args:
            db: Async database session
            data: Message archive creation data

        Returns:
            Created MessageArchive instance
        """
        message_archive = MessageArchive(**data.model_dump())
        db.add(message_archive)
        await db.flush()
        return message_archive

    @staticmethod
    async def create_from_text(
        db: AsyncSession,
        content: str,
        platform_message_id: str | None = None,
        platform_channel_id: str | None = None,
        platform_author_id: str | None = None,
        platform_timestamp: datetime | None = None,
    ) -> MessageArchive:
        """
        Convenience method to create a text content message archive.

        Args:
            db: Async database session
            content: Text content to store
            platform_message_id: Optional platform message ID
            platform_channel_id: Optional platform channel ID
            platform_author_id: Optional platform author ID
            platform_timestamp: Optional platform message timestamp

        Returns:
            Created MessageArchive instance with TEXT content type
        """
        message_archive = MessageArchive(
            content_type=ContentType.TEXT,
            content_text=content,
            platform_message_id=platform_message_id,
            platform_channel_id=platform_channel_id,
            platform_author_id=platform_author_id,
            platform_timestamp=platform_timestamp,
        )
        db.add(message_archive)
        await db.flush()
        return message_archive

    @staticmethod
    async def create_from_image(
        db: AsyncSession,
        image_url: str,
        community_server_id: str,
        vision_service: "VisionService",
        platform_message_id: str | None = None,
        platform_channel_id: str | None = None,
        platform_author_id: str | None = None,
        platform_timestamp: datetime | None = None,
        detail: Literal["low", "high", "auto"] = "auto",
        max_tokens: int | None = None,
    ) -> MessageArchive:
        """
        Create an image content message archive with AI-generated description.

        Args:
            db: Async database session
            image_url: URL of the image
            community_server_id: Community server (guild) ID for API key lookup
            vision_service: VisionService instance for generating descriptions
            platform_message_id: Optional platform message ID
            platform_channel_id: Optional platform channel ID
            platform_author_id: Optional platform author ID
            platform_timestamp: Optional platform message timestamp
            detail: Vision detail level ('low', 'high', or 'auto')
            max_tokens: Maximum tokens for description (uses setting default if None)

        Returns:
            Created MessageArchive instance with IMAGE content type and description

        Raises:
            Exception: If vision description generation fails
        """
        resolved_max_tokens: int = (
            max_tokens if max_tokens is not None else settings.VISION_MAX_TOKENS
        )

        try:
            description = await vision_service.describe_image(
                db=db,
                image_url=image_url,
                community_server_id=community_server_id,
                detail=detail,
                max_tokens=resolved_max_tokens,
            )

            logger.info(
                "Generated vision description for image",
                extra={
                    "image_url": image_url[:100],
                    "community_server_id": community_server_id,
                    "description_length": len(description),
                },
            )

        except Exception as e:
            logger.error(
                "Failed to generate vision description, creating archive without description",
                extra={
                    "image_url": image_url[:100],
                    "community_server_id": community_server_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            description = None

        message_archive = MessageArchive(
            content_type=ContentType.IMAGE,
            content_url=image_url,
            image_description=description,
            platform_message_id=platform_message_id,
            platform_channel_id=platform_channel_id,
            platform_author_id=platform_author_id,
            platform_timestamp=platform_timestamp,
        )
        db.add(message_archive)
        await db.flush()
        return message_archive

    @staticmethod
    async def get_by_id(db: AsyncSession, message_archive_id: UUID) -> MessageArchive | None:
        """
        Get message archive by ID, excluding soft-deleted records.

        Args:
            db: Async database session
            message_archive_id: UUID of the message archive

        Returns:
            MessageArchive instance if found and not deleted, None otherwise
        """
        stmt = select(MessageArchive).where(
            MessageArchive.id == message_archive_id, MessageArchive.deleted_at.is_(None)
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_platform_message_id(
        db: AsyncSession, platform_message_id: str
    ) -> MessageArchive | None:
        """
        Get message archive by platform message ID, excluding soft-deleted records.

        Args:
            db: Async database session
            platform_message_id: Platform message ID to search for

        Returns:
            MessageArchive instance if found and not deleted, None otherwise
        """
        stmt = select(MessageArchive).where(
            MessageArchive.platform_message_id == platform_message_id,
            MessageArchive.deleted_at.is_(None),
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def soft_delete(db: AsyncSession, message_archive_id: UUID) -> bool:
        """
        Soft delete a message archive by setting deleted_at timestamp.

        Args:
            db: Async database session
            message_archive_id: UUID of the message archive to delete

        Returns:
            True if archive was found and deleted, False if not found
        """
        message_archive = await MessageArchiveService.get_by_id(db, message_archive_id)
        if not message_archive:
            return False

        message_archive.soft_delete()
        await db.flush()
        return True

    @staticmethod
    def _resolve_note_action(
        note: Note | None,
    ) -> tuple[bool, bool, str | None]:
        if note is None:
            return False, True, None
        if not note.ai_generated:
            return False, False, "human_note"
        if len(note.ratings) > 0:
            return False, False, "rated_ai_note"
        return True, True, None

    @staticmethod
    async def cascade_soft_delete(
        db: AsyncSession,
        message_archive_id: UUID,
        dry_run: bool = False,
    ) -> dict:
        stmt = select(MessageArchive).where(MessageArchive.id == message_archive_id)
        archive = (await db.execute(stmt)).scalar_one_or_none()

        base = {
            "archive_id": str(message_archive_id),
            "archive_deleted": False,
            "request_id": None,
            "request_deleted": False,
            "note_id": None,
            "note_deleted": False,
            "skipped_reason": None,
            "dry_run": dry_run,
        }

        if archive is None:
            return base

        base["archive_id"] = str(archive.id)
        base["archive_deleted"] = archive.deleted_at is None

        if not dry_run and base["archive_deleted"]:
            archive.soft_delete()

        request = (
            await db.execute(
                select(Request).where(Request.message_archive_id == message_archive_id)
            )
        ).scalar_one_or_none()

        if request is not None:
            base["request_id"] = str(request.request_id)
            base.update(await MessageArchiveService._resolve_request_cascade(db, request, dry_run))

        if not dry_run:
            await db.flush()

        return base

    @staticmethod
    async def _resolve_request_cascade(
        db: AsyncSession,
        request: Request,
        dry_run: bool,
    ) -> dict:
        if not request.requested_by.startswith("system-"):
            return {"skipped_reason": "non_system_request"}

        if request.note_id is None:
            if not dry_run:
                request.soft_delete()
            return {"request_deleted": True}

        note = (
            await db.execute(
                select(Note).where(Note.id == request.note_id).options(*note_loaders.ratings())
            )
        ).scalar_one_or_none()

        note_deleted, request_deleted, skipped_reason = MessageArchiveService._resolve_note_action(
            note
        )

        if not dry_run and (note_deleted or request_deleted):
            if note_deleted and note is not None:
                note.soft_delete()
            if request_deleted:
                request.soft_delete()

        return {
            "note_id": str(note.id) if note else None,
            "note_deleted": note_deleted,
            "request_deleted": request_deleted,
            "skipped_reason": skipped_reason,
        }

    @staticmethod
    async def find_bad_archives(
        db: AsyncSession,
        min_content_length: int = 10,
        max_similarity_score: float = 0.6,
    ) -> list[UUID]:
        stmt = (
            select(MessageArchive.id)
            .join(Request, Request.message_archive_id == MessageArchive.id)
            .where(
                MessageArchive.deleted_at.is_(None),
                Request.requested_by.like("system-%"),
                or_(
                    MessageArchive.content_text.isnot(None)
                    & (func.length(MessageArchive.content_text) < min_content_length),
                    Request.similarity_score.isnot(None)
                    & (Request.similarity_score < max_similarity_score),
                ),
            )
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())
