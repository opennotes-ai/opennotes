"""NATS event handlers for Bulk Content Scan."""

import uuid as uuid_module
from typing import Any
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.bulk_content_scan.scan_types import DEFAULT_SCAN_TYPES, ScanType
from src.bulk_content_scan.schemas import FlaggedMessage
from src.community_config.models import CommunityConfig
from src.config import settings
from src.database import get_session_maker
from src.dbos_workflows.content_scan_workflow import (
    enqueue_content_scan_batch,
    send_all_transmitted_signal,
)
from src.events.schemas import (
    BulkScanAllBatchesTransmittedEvent,
    BulkScanMessageBatchEvent,
    BulkScanResultsEvent,
    EventType,
    ScanErrorSummary,
)
from src.events.subscriber import event_subscriber
from src.fact_checking.embedding_service import EmbeddingService
from src.llm_config.models import CommunityServer
from src.llm_config.service import LLMService
from src.monitoring import get_logger

logger = get_logger(__name__)


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
        messages_skipped: int = 0,
        flagged_messages: list[FlaggedMessage] | None = None,
        error_summary: ScanErrorSummary | None = None,
        **_kwargs: Any,
    ) -> None:
        """Publish bulk scan results event.

        Args:
            scan_id: UUID of the scan
            messages_scanned: Total messages processed
            messages_flagged: Number flagged
            messages_skipped: Messages skipped (already have note requests)
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
            messages_skipped=messages_skipped,
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
        llm_service: LLMService | None = None,
    ) -> None:
        """Initialize the handler.

        Args:
            embedding_service: Service for similarity searches
            redis_client: Redis client for temporary storage
            nats_client: NATS client for publishing results
            llm_service: Optional LLM service for relevance checking
        """
        self.embedding_service = embedding_service
        self.redis_client = redis_client
        self.nats_client = nats_client
        self.llm_service = llm_service
        self.publisher = BulkScanResultsPublisher(nats_client)
        self.subscriber = event_subscriber

    async def _get_scan_types_for_community(self, community_server_id: UUID) -> list[str]:
        """Determine scan types based on community server configuration.

        Checks if flashpoint detection is enabled for the community and
        includes CONVERSATION_FLASHPOINT scan type if so.

        Args:
            community_server_id: Community server UUID

        Returns:
            List of scan type strings
        """
        scan_types = list(DEFAULT_SCAN_TYPES)

        try:
            async with get_session_maker()() as session:
                result = await session.execute(
                    select(CommunityServer.flashpoint_detection_enabled).where(
                        CommunityServer.id == community_server_id
                    )
                )
                enabled = result.scalar_one_or_none()
                if enabled:
                    scan_types.append(ScanType.CONVERSATION_FLASHPOINT)
        except Exception:
            logger.warning(
                "Failed to check flashpoint_detection_enabled for DBOS dispatch",
                extra={"community_server_id": str(community_server_id)},
                exc_info=True,
            )

        return [str(st) for st in scan_types]

    async def _handle_message_batch(self, event: BulkScanMessageBatchEvent) -> None:
        """Handle incoming message batch by enqueuing DBOS batch workflow.

        Uses the NATS -> DBOS pattern:
        - NATS provides cross-service event routing from Discord bot
        - DBOS provides durable execution with retries and checkpointing
        - Batch workflow sends batch_complete signal to orchestrator when done
        """
        scan_types = await self._get_scan_types_for_community(event.community_server_id)
        orchestrator_workflow_id = str(event.scan_id)

        logger.info(
            "Dispatching bulk scan batch to DBOS",
            extra={
                "scan_id": str(event.scan_id),
                "batch_number": event.batch_number,
                "message_count": len(event.messages),
                "scan_types": scan_types,
            },
        )

        await enqueue_content_scan_batch(
            orchestrator_workflow_id=orchestrator_workflow_id,
            scan_id=event.scan_id,
            community_server_id=event.community_server_id,
            batch_number=event.batch_number,
            messages=[msg.model_dump(mode="json") for msg in event.messages],
            scan_types=scan_types,
        )

    async def _handle_all_batches_transmitted(
        self, event: BulkScanAllBatchesTransmittedEvent
    ) -> None:
        """Handle all_batches_transmitted event by sending signal to DBOS orchestrator.

        Uses the NATS -> DBOS pattern:
        - NATS delivers the transmitted event from Discord bot
        - DBOS.send() delivers the all_transmitted signal to the orchestrator workflow
        - The orchestrator handles finalization when all conditions are met

        The orchestrator workflow ID is the scan_id (set via SetWorkflowID at dispatch).
        """
        logger.info(
            "Sending all_transmitted signal to DBOS orchestrator",
            extra={
                "scan_id": str(event.scan_id),
                "messages_scanned": event.messages_scanned,
            },
        )

        orchestrator_workflow_id = str(event.scan_id)

        await send_all_transmitted_signal(
            orchestrator_workflow_id=orchestrator_workflow_id,
            messages_scanned=event.messages_scanned,
        )

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
