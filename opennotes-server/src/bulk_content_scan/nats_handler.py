"""NATS event handlers for Bulk Content Scan."""

import uuid as uuid_module
from typing import Any, Protocol
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.bulk_content_scan.schemas import BulkScanMessage, BulkScanStatus, FlaggedMessage
from src.bulk_content_scan.service import BulkContentScanService
from src.community_config.models import CommunityConfig
from src.config import settings
from src.database import get_session_maker
from src.events.publisher import event_publisher
from src.events.schemas import (
    BulkScanAllBatchesTransmittedEvent,
    BulkScanMessageBatchEvent,
    BulkScanProcessingFinishedEvent,
    BulkScanProgressEvent,
    BulkScanResultsEvent,
    EventType,
    MessageScoreInfo,
    ScanErrorInfo,
    ScanErrorSummary,
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


async def get_vibecheck_debug_mode(
    session: AsyncSession,
    community_server_id: UUID,
) -> bool:
    """Get vibecheck_debug_mode setting from community_config table.

    Reads from the community_config key-value store which is set via
    Discord bot's /config opennotes set command.

    Args:
        session: Database session
        community_server_id: Community server UUID

    Returns:
        True if vibecheck_debug_mode is enabled, False otherwise
    """
    result = await session.execute(
        select(CommunityConfig.config_value).where(
            CommunityConfig.community_server_id == community_server_id,
            CommunityConfig.config_key == "vibecheck_debug_mode",
        )
    )
    value = result.scalar_one_or_none()
    if value is None:
        return False
    return value.lower() in ("true", "1", "yes")


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
        error_msg = f"Platform ID not found for community server {event.community_server_id}"
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
        community_server_platform_id=platform_id,
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


async def handle_message_batch_with_progress(
    event: BulkScanMessageBatchEvent,
    service: BulkContentScanService,
    nats_client: Any,
    platform_id: str,
    debug_mode: bool,
    publisher: EventPublisher | None = None,
) -> None:
    """Handle message batch with optional progress event emission.

    When debug_mode is True, this function processes messages and publishes
    a progress event containing similarity scores for ALL messages (not just
    flagged ones).

    This function processes messages individually to track per-message errors
    while still allowing successful messages to be processed.

    After processing, checks if all_batches_transmitted flag is set and
    all messages are processed - if so, triggers scan completion (dual-completion
    trigger pattern to fix race condition). The messages_scanned count is
    retrieved from Redis where it was stored by the transmitted handler.

    Args:
        event: Message batch event
        service: Bulk scan service
        nats_client: NATS client for publishing progress events
        platform_id: Platform ID for the community server
        debug_mode: Whether vibecheck_debug_mode is enabled
        publisher: Event publisher for results (for completion trigger)
    """
    logger.info(
        "Processing message batch with progress",
        extra={
            "scan_id": str(event.scan_id),
            "batch_number": event.batch_number,
            "message_count": len(event.messages),
            "debug_mode": debug_mode,
        },
    )

    typed_messages = [BulkScanMessage.model_validate(msg) for msg in event.messages]
    threshold = settings.SIMILARITY_SEARCH_DEFAULT_THRESHOLD

    flagged: list[FlaggedMessage] = []
    all_scores: list[dict] = []
    successful_count = 0
    error_count = 0

    for msg in typed_messages:
        try:
            if debug_mode:
                msg_flagged, msg_scores = await service.process_messages_with_scores(
                    scan_id=event.scan_id,
                    messages=[msg],
                    community_server_platform_id=platform_id,
                )
                flagged.extend(msg_flagged)
                all_scores.extend(msg_scores)
            else:
                msg_flagged = await service.process_messages(
                    scan_id=event.scan_id,
                    messages=[msg],
                    community_server_platform_id=platform_id,
                )
                flagged.extend(msg_flagged)
            successful_count += 1
        except Exception as e:
            error_count += 1
            error_type = type(e).__name__
            logger.warning(
                "Error processing message in batch",
                extra={
                    "scan_id": str(event.scan_id),
                    "message_id": msg.message_id,
                    "batch_number": event.batch_number,
                    "error_type": error_type,
                    "error": str(e),
                },
            )
            await service.record_error(
                scan_id=event.scan_id,
                error_type=error_type,
                error_message=str(e),
                message_id=msg.message_id,
                batch_number=event.batch_number,
            )
            if debug_mode:
                all_scores.append(
                    {
                        "message_id": msg.message_id,
                        "channel_id": msg.channel_id,
                        "similarity_score": 0.0,
                        "is_flagged": False,
                        "matched_claim": None,
                    }
                )

    await service.increment_processed_count(event.scan_id, successful_count)

    processed_count = await service.get_processed_count(event.scan_id)
    channel_ids = list({msg.channel_id for msg in typed_messages})

    message_score_infos: list[MessageScoreInfo] = []
    if debug_mode and all_scores:
        message_score_infos = [
            MessageScoreInfo(
                message_id=score["message_id"],
                channel_id=score["channel_id"],
                similarity_score=score["similarity_score"],
                threshold=threshold,
                is_flagged=score["is_flagged"],
                matched_claim=score.get("matched_claim"),
                moderation_flagged=score.get("moderation_flagged"),
                moderation_categories=score.get("moderation_categories"),
                moderation_scores=score.get("moderation_scores"),
            )
            for score in all_scores
        ]

    progress_event = BulkScanProgressEvent(
        event_id=f"evt_{uuid_module.uuid4().hex[:12]}",
        scan_id=event.scan_id,
        community_server_id=event.community_server_id,
        platform_id=platform_id,
        batch_number=event.batch_number,
        messages_in_batch=len(typed_messages),
        messages_processed=processed_count,
        channel_ids=channel_ids,
        message_scores=message_score_infos,
        threshold_used=threshold,
    )

    await event_publisher.publish_event(progress_event)

    logger.debug(
        "Published progress event",
        extra={
            "scan_id": str(event.scan_id),
            "batch_number": event.batch_number,
            "messages_processed": processed_count,
            "channel_ids": channel_ids,
            "scores_count": len(message_score_infos),
        },
    )

    for msg in flagged:
        await service.append_flagged_result(event.scan_id, msg)

    logger.debug(
        "Batch processed with progress",
        extra={
            "scan_id": str(event.scan_id),
            "messages_processed": len(event.messages),
            "messages_successful": successful_count,
            "messages_errored": error_count,
            "messages_flagged": len(flagged),
        },
    )

    if publisher is not None:
        transmitted, transmitted_messages = await service.get_all_batches_transmitted(event.scan_id)
        if transmitted and transmitted_messages is not None:
            processed_count = await service.get_processed_count(event.scan_id)
            if processed_count >= transmitted_messages:
                logger.info(
                    "Batch handler triggering completion (transmitted flag set)",
                    extra={
                        "scan_id": str(event.scan_id),
                        "processed_count": processed_count,
                        "messages_scanned": transmitted_messages,
                    },
                )
                await finalize_scan(
                    scan_id=event.scan_id,
                    community_server_id=event.community_server_id,
                    messages_scanned=transmitted_messages,
                    service=service,
                    publisher=publisher,
                )


async def finalize_scan(
    scan_id: UUID,
    community_server_id: UUID,
    messages_scanned: int,
    service: BulkContentScanService,
    publisher: EventPublisher,
) -> None:
    """Finalize a scan and publish results.

    This is called by whichever handler finishes last (batch or transmitted).
    Implements the dual-completion-trigger pattern to fix the race condition.

    Args:
        scan_id: UUID of the scan
        community_server_id: Community server UUID
        messages_scanned: Total messages scanned
        service: Bulk scan service
        publisher: Event publisher for results
    """
    flagged = await service.get_flagged_results(scan_id)
    error_summary_data = await service.get_error_summary(scan_id)
    processed_count = await service.get_processed_count(scan_id)

    total_errors = error_summary_data.get("total_errors", 0)
    error_types = error_summary_data.get("error_types", {})
    sample_errors = error_summary_data.get("sample_errors", [])

    error_summary = None
    if total_errors > 0:
        error_summary = ScanErrorSummary(
            total_errors=total_errors,
            error_types=error_types,
            sample_errors=[
                ScanErrorInfo(
                    error_type=err.get("error_type", "Unknown"),
                    message_id=err.get("message_id"),
                    batch_number=err.get("batch_number"),
                    error_message=err.get("error_message", ""),
                )
                for err in sample_errors
            ],
        )

    status = BulkScanStatus.COMPLETED
    if messages_scanned > 0 and processed_count == 0 and total_errors > 0:
        status = BulkScanStatus.FAILED
        logger.warning(
            "Scan marked as failed - 100% of messages had errors",
            extra={
                "scan_id": str(scan_id),
                "messages_scanned": messages_scanned,
                "total_errors": total_errors,
            },
        )

    await service.complete_scan(
        scan_id=scan_id,
        messages_scanned=messages_scanned,
        messages_flagged=len(flagged),
        status=status,
    )

    await publisher.publish(
        scan_id=scan_id,
        messages_scanned=messages_scanned,
        messages_flagged=len(flagged),
        flagged_messages=flagged,
        error_summary=error_summary,
    )

    processing_finished_event = BulkScanProcessingFinishedEvent(
        event_id=f"evt_{uuid_module.uuid4().hex[:12]}",
        scan_id=scan_id,
        community_server_id=community_server_id,
        messages_scanned=messages_scanned,
        messages_flagged=len(flagged),
    )
    await event_publisher.publish_event(processing_finished_event)

    logger.info(
        "Scan finalized",
        extra={
            "scan_id": str(scan_id),
            "messages_scanned": messages_scanned,
            "messages_flagged": len(flagged),
            "status": status,
            "total_errors": total_errors,
        },
    )


async def handle_all_batches_transmitted(
    event: BulkScanAllBatchesTransmittedEvent,
    service: BulkContentScanService,
    publisher: EventPublisher,
) -> None:
    """Handle all_batches_transmitted event from Discord bot.

    Sets the transmitted flag and checks if all batches are already processed.
    If so, triggers scan completion. Otherwise, the batch handler will trigger
    completion when the last batch is processed.

    Args:
        event: All batches transmitted event
        service: Bulk scan service
        publisher: Event publisher for results
    """
    logger.info(
        "Processing all_batches_transmitted",
        extra={
            "scan_id": str(event.scan_id),
            "messages_scanned": event.messages_scanned,
        },
    )

    await service.set_all_batches_transmitted(event.scan_id, event.messages_scanned)

    processed_count = await service.get_processed_count(event.scan_id)
    if processed_count >= event.messages_scanned:
        logger.info(
            "Transmitted handler triggering completion (all batches processed)",
            extra={
                "scan_id": str(event.scan_id),
                "processed_count": processed_count,
                "messages_scanned": event.messages_scanned,
            },
        )
        await finalize_scan(
            scan_id=event.scan_id,
            community_server_id=event.community_server_id,
            messages_scanned=event.messages_scanned,
            service=service,
            publisher=publisher,
        )
    else:
        logger.info(
            "Transmitted handler not triggering completion (batches still pending)",
            extra={
                "scan_id": str(event.scan_id),
                "processed_count": processed_count,
                "messages_scanned": event.messages_scanned,
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
        scan_id: UUID | None = None,
        messages_scanned: int = 0,
        messages_flagged: int = 0,
        flagged_messages: list[FlaggedMessage] | None = None,
        error_summary: ScanErrorSummary | None = None,
        **_kwargs: Any,
    ) -> None:
        """Publish bulk scan results event.

        Args:
            scan_id: UUID of the scan
            messages_scanned: Total messages processed
            messages_flagged: Number flagged
            flagged_messages: List of FlaggedMessage objects
            error_summary: Summary of errors encountered during scan
            **_kwargs: Additional arguments (ignored, for protocol compatibility)
        """
        if scan_id is None:
            raise ValueError("scan_id is required")

        event = BulkScanResultsEvent(
            event_id=f"evt_{uuid_module.uuid4().hex[:12]}",
            scan_id=scan_id,
            messages_scanned=messages_scanned,
            messages_flagged=messages_flagged,
            flagged_messages=flagged_messages or [],
            error_summary=error_summary,
        )

        # Convert event_type to NATS subject (matching EventPublisher pattern)
        event_name = EventType.BULK_SCAN_RESULTS.value.replace(".", "_")
        subject = f"{settings.NATS_STREAM_NAME}.{event_name}"

        # Serialize event to bytes
        data = event.model_dump_json().encode()

        # Build headers for correlation and deduplication
        headers = {
            "event-id": event.event_id,
            "event-type": EventType.BULK_SCAN_RESULTS.value,
            "Msg-Id": event.event_id,
            "X-Correlation-Id": event.event_id,
        }

        await self.nats_client.publish(subject, data, headers=headers)

        logger.debug(
            "Published bulk scan results event",
            extra={
                "scan_id": str(scan_id),
                "event_id": event.event_id,
                "has_errors": error_summary is not None,
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
        self.nats_client = nats_client
        self.publisher = BulkScanResultsPublisher(nats_client)
        self.subscriber = event_subscriber

    async def _handle_message_batch(self, event: BulkScanMessageBatchEvent) -> None:
        """Handle incoming message batch from Discord bot."""
        async with get_session_maker()() as session:
            platform_id = await get_platform_id(session, event.community_server_id)
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

            debug_mode = await get_vibecheck_debug_mode(session, event.community_server_id)

            service = BulkContentScanService(
                session=session,
                embedding_service=self.embedding_service,
                redis_client=self.redis_client,
            )
            await handle_message_batch_with_progress(
                event=event,
                service=service,
                nats_client=self.nats_client,
                platform_id=platform_id,
                debug_mode=debug_mode,
                publisher=self.publisher,
            )

    async def _handle_all_batches_transmitted(
        self, event: BulkScanAllBatchesTransmittedEvent
    ) -> None:
        """Handle all_batches_transmitted event from Discord bot."""
        async with get_session_maker()() as session:
            service = BulkContentScanService(
                session=session,
                embedding_service=self.embedding_service,
                redis_client=self.redis_client,
            )
            await handle_all_batches_transmitted(event, service, self.publisher)

    def register(self) -> None:
        """Register bulk scan event handlers with the subscriber."""
        logger.info("Registering bulk scan event handlers")
        self.subscriber.register_handler(
            EventType.BULK_SCAN_MESSAGE_BATCH,
            self._handle_message_batch,
        )
        self.subscriber.register_handler(
            EventType.BULK_SCAN_ALL_BATCHES_TRANSMITTED,
            self._handle_all_batches_transmitted,
        )
        logger.info("Bulk scan event handlers registered")
