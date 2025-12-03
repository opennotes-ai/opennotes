"""Service for managing previously seen message records."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.fact_checking.previously_seen_models import PreviouslySeenMessage
from src.fact_checking.previously_seen_schemas import (
    PreviouslySeenMessageCreate,
    PreviouslySeenMessageResponse,
)
from src.monitoring import get_logger

logger = get_logger(__name__)


class PreviouslySeenService:
    """Service for storing and managing previously seen message embeddings."""

    async def store_message_embedding(
        self,
        db: AsyncSession,
        community_server_id: UUID,
        original_message_id: str,
        published_note_id: UUID,
        embedding: list[float] | None,
        embedding_provider: str | None = None,
        embedding_model: str | None = None,
        extra_metadata: dict[str, str | int | float | bool | None] | None = None,
    ) -> PreviouslySeenMessageResponse | None:
        """
        Store a previously seen message embedding after note publication.

        Args:
            db: Database session
            community_server_id: Community server UUID
            original_message_id: Platform-specific message ID
            published_note_id: Note ID that was published for this message
            embedding: Vector embedding (1536 dimensions)
            embedding_provider: LLM provider used (e.g., 'openai')
            embedding_model: Model name used (e.g., 'text-embedding-3-small')
            extra_metadata: Additional context metadata

        Returns:
            PreviouslySeenMessageResponse if successful, None if embedding is missing
        """
        if embedding is None:
            logger.warning(
                "Cannot store previously seen message without embedding",
                extra={
                    "community_server_id": str(community_server_id),
                    "original_message_id": original_message_id,
                    "published_note_id": published_note_id,
                },
            )
            return None

        try:
            # Create the record
            create_data = PreviouslySeenMessageCreate(
                community_server_id=community_server_id,
                original_message_id=original_message_id,
                published_note_id=published_note_id,
                embedding=embedding,
                embedding_provider=embedding_provider,
                embedding_model=embedding_model,
                extra_metadata=extra_metadata or {},
            )

            message_record = PreviouslySeenMessage(**create_data.model_dump())
            db.add(message_record)
            await db.commit()
            await db.refresh(message_record)

            logger.info(
                "Stored previously seen message embedding",
                extra={
                    "id": str(message_record.id),
                    "community_server_id": str(community_server_id),
                    "original_message_id": original_message_id,
                    "published_note_id": published_note_id,
                    "embedding_provider": embedding_provider,
                    "embedding_model": embedding_model,
                },
            )

            return PreviouslySeenMessageResponse.model_validate(message_record)

        except Exception as e:
            logger.error(
                "Failed to store previously seen message embedding",
                extra={
                    "community_server_id": str(community_server_id),
                    "original_message_id": original_message_id,
                    "published_note_id": published_note_id,
                    "error": str(e),
                },
                exc_info=True,
            )
            await db.rollback()
            return None
