"""NATS event handlers for Bulk Content Scan."""

import uuid as uuid_module
from typing import Any, Protocol
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.bulk_content_scan.schemas import BulkScanMessage
from src.bulk_content_scan.service import BulkContentScanService
from src.database import get_session_maker
from src.events.schemas import (
    BulkScanCompletedEvent,
    BulkScanMessageBatchEvent,
    BulkScanResultsEvent,
    EventType,
)
from src.events.subscriber import event_subscriber
from src.fact_checking.embedding_service import EmbeddingService
from src.llm_config.models import CommunityServer
from src.monitoring import get_logger

logger = get_logger(__name__)


class BatchProcessingError(Exception):
    """Exception raised when batch processing fails.

    Raising this exception causes the NATS message to be NAKed for retry,
    preventing silent batch dropping.
    """

    pass


class EventPublisher(Protocol):
    """Protocol for event publishing."""

    async def publish(self, **kwargs: Any) -> None:
        """Publish an event."""
        ...


async def get_platform_id(
    session: AsyncSession,
    community_server_id: UUID,
) -> str | None:
    """Get platform ID from community server UUID.

    Args:
        session: Database session
        community_server_id: Community server UUID

    Returns:
        Platform ID (e.g., Discord guild ID) or None if not found
    """
    result = await session.execute(
        select(CommunityServer.platform_id).where(CommunityServer.id == community_server_id)
    )
    return result.scalar_one_or_none()


async def handle_message_batch(
    event: BulkScanMessageBatchEvent,
    service: BulkContentScanService,
) -> None:
    """Handle message batch by processing each message immediately.

    Args:
        event: Message batch event
        service: Bulk scan service
    """
    logger.info(
        "Processing message batch",
        extra={
            "scan_id": str(event.scan_id),
            "batch_number": event.batch_number,
            "message_count": len(event.messages),
        },
    )

    platform_id = await get_platform_id(service.session, event.community_server_id)
    if not platform_id:
        error_msg = (
            f"Platform ID not found for community server {event.community_server_id}"
        )
        logger.error(
            error_msg,
            extra={
                "scan_id": str(event.scan_id),
                "community_server_id": str(event.community_server_id),
            },
        )
        raise BatchProcessingError(error_msg)

    typed_messages = [BulkScanMessage.model_validate(msg) for msg in event.messages]

    flagged = await service.process_messages(
        scan_id=event.scan_id,
        messages=typed_messages,
        platform_id=platform_id,
    )

    for msg in flagged:
        await service.append_flagged_result(event.scan_id, msg)

    logger.debug(
        "Batch processed",
        extra={
            "scan_id": str(event.scan_id),
            "messages_processed": len(event.messages),
            "messages_flagged": len(flagged),
        },
    )


async def handle_scan_completed(
    event: BulkScanCompletedEvent,
    service: BulkContentScanService,
    publisher: EventPublisher,
) -> None:
    """Mark scan as complete and publish final results.

    Args:
        event: Scan completion event
        service: Bulk scan service
        publisher: Event publisher for results
    """
    logger.info(
        "Processing scan completion",
        extra={
            "scan_id": str(event.scan_id),
            "messages_scanned": event.messages_scanned,
        },
    )

    flagged = await service.get_flagged_results(event.scan_id)

    await service.complete_scan(
        scan_id=event.scan_id,
        messages_scanned=event.messages_scanned,
        messages_flagged=len(flagged),
    )

    await publisher.publish(
        scan_id=event.scan_id,
        messages_scanned=event.messages_scanned,
        messages_flagged=len(flagged),
        flagged_messages=[msg.model_dump(mode="json") for msg in flagged],
    )

    logger.info(
        "Scan completion processed",
        extra={
            "scan_id": str(event.scan_id),
            "messages_scanned": event.messages_scanned,
            "messages_flagged": len(flagged),
        },
    )


class BulkScanResultsPublisher:
    """Publisher for bulk scan results events."""

    def __init__(self, nats_client: Any) -> None:
        """Initialize publisher.

        Args:
            nats_client: NATS client instance
        """
        self.nats_client = nats_client

    async def publish(
        self,
        scan_id: UUID,
        messages_scanned: int,
        messages_flagged: int,
        flagged_messages: list[dict],
    ) -> None:
        """Publish bulk scan results event.

        Args:
            scan_id: UUID of the scan
            messages_scanned: Total messages processed
            messages_flagged: Number flagged
            flagged_messages: List of flagged message dicts
        """
        event = BulkScanResultsEvent(
            event_id=f"evt_{uuid_module.uuid4().hex[:12]}",
            scan_id=scan_id,
            messages_scanned=messages_scanned,
            messages_flagged=messages_flagged,
            flagged_messages=flagged_messages,
        )

        await self.nats_client.publish(
            event_type=EventType.BULK_SCAN_RESULTS,
            event_data=event.model_dump(mode="json"),
        )

        logger.debug(
            "Published bulk scan results event",
            extra={
                "scan_id": str(scan_id),
                "event_id": event.event_id,
            },
        )


class BulkScanEventHandler:
    """Event handler for bulk content scan events.

    This handler processes message batches and scan completion events
    from the Discord bot, performing similarity analysis on messages
    as they arrive and storing flagged results incrementally.
    """

    def __init__(
        self,
        embedding_service: EmbeddingService,
        redis_client: Redis,
        nats_client: Any,
    ) -> None:
        """Initialize the handler.

        Args:
            embedding_service: Service for similarity searches
            redis_client: Redis client for temporary storage
            nats_client: NATS client for publishing results
        """
        self.embedding_service = embedding_service
        self.redis_client = redis_client
        self.publisher = BulkScanResultsPublisher(nats_client)
        self.subscriber = event_subscriber

    async def _handle_message_batch(self, event: BulkScanMessageBatchEvent) -> None:
        """Handle incoming message batch from Discord bot."""
        async with get_session_maker()() as session:
            service = BulkContentScanService(
                session=session,
                embedding_service=self.embedding_service,
                redis_client=self.redis_client,
            )
            await handle_message_batch(event, service)

    async def _handle_scan_completed(self, event: BulkScanCompletedEvent) -> None:
        """Process all collected messages when scan is complete."""
        async with get_session_maker()() as session:
            service = BulkContentScanService(
                session=session,
                embedding_service=self.embedding_service,
                redis_client=self.redis_client,
            )
            await handle_scan_completed(event, service, self.publisher)

    def register(self) -> None:
        """Register bulk scan event handlers with the subscriber."""
        logger.info("Registering bulk scan event handlers")
        self.subscriber.register_handler(
            EventType.BULK_SCAN_MESSAGE_BATCH,
            self._handle_message_batch,
        )
        self.subscriber.register_handler(
            EventType.BULK_SCAN_COMPLETED,
            self._handle_scan_completed,
        )
        logger.info("Bulk scan event handlers registered")
