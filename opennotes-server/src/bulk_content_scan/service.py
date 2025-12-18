"""Service layer for Bulk Content Scan operations."""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.bulk_content_scan.models import BulkContentScanLog
from src.bulk_content_scan.scan_types import DEFAULT_SCAN_TYPES, ScanType
from src.bulk_content_scan.schemas import BulkScanMessage, BulkScanStatus, FlaggedMessage
from src.config import settings
from src.fact_checking.embedding_service import EmbeddingService
from src.monitoring import get_logger

logger = get_logger(__name__)

REDIS_KEY_PREFIX = "bulk_scan"
REDIS_TTL_SECONDS = 86400  # 24 hours


def _get_redis_results_key(scan_id: UUID) -> str:
    """Get environment-prefixed Redis key for scan results.

    Format: {environment}:{prefix}:results:{scan_id}
    Example: production:bulk_scan:results:abc-123
    """
    return f"{settings.ENVIRONMENT}:{REDIS_KEY_PREFIX}:results:{scan_id}"


class BulkContentScanService:
    """Service for managing bulk content scans."""

    def __init__(
        self,
        session: AsyncSession,
        embedding_service: EmbeddingService,
        redis_client: Redis,
    ) -> None:
        """Initialize the service.

        Args:
            session: Database session for scan log operations
            embedding_service: Service for similarity search
            redis_client: Redis client for temporary message storage
        """
        self.session = session
        self.embedding_service = embedding_service
        self.redis_client = redis_client

    async def initiate_scan(
        self,
        community_server_id: UUID,
        initiated_by_user_id: UUID,
        scan_window_days: int,
    ) -> BulkContentScanLog:
        """Create a new scan log entry and return it.

        Args:
            community_server_id: UUID of the community server to scan
            initiated_by_user_id: UUID of the user who initiated the scan
            scan_window_days: Number of days to scan back

        Returns:
            Created BulkContentScanLog entry
        """
        scan_log = BulkContentScanLog(
            community_server_id=community_server_id,
            initiated_by_user_id=initiated_by_user_id,
            scan_window_days=scan_window_days,
            status=BulkScanStatus.PENDING,
        )

        self.session.add(scan_log)
        await self.session.commit()
        await self.session.refresh(scan_log)

        logger.info(
            "Bulk content scan initiated",
            extra={
                "scan_id": str(scan_log.id),
                "community_server_id": str(community_server_id),
                "initiated_by_user_id": str(initiated_by_user_id),
                "scan_window_days": scan_window_days,
            },
        )

        return scan_log

    async def process_messages(
        self,
        scan_id: UUID,
        messages: BulkScanMessage | Sequence[BulkScanMessage],
        platform_id: str,
        scan_types: Sequence[ScanType] = DEFAULT_SCAN_TYPES,
    ) -> list[FlaggedMessage]:
        """Process one or more messages through specified scan types.

        Args:
            scan_id: UUID of the scan
            messages: Single BulkScanMessage OR sequence of messages
            platform_id: Platform-specific ID for embedding service
            scan_types: Sequence of ScanType to run (default: all)

        Returns:
            List of FlaggedMessage for messages that matched any scanner
        """
        if isinstance(messages, BulkScanMessage):
            messages = [messages]

        flagged: list[FlaggedMessage] = []

        for msg in messages:
            if not msg.content or len(msg.content.strip()) < 10:
                continue

            for scan_type in scan_types:
                result = await self._run_scanner(scan_id, msg, platform_id, scan_type)
                if result:
                    flagged.append(result)
                    break

        return flagged

    async def _run_scanner(
        self,
        scan_id: UUID,
        message: BulkScanMessage,
        platform_id: str,
        scan_type: ScanType,
    ) -> FlaggedMessage | None:
        """Run a specific scanner on a message."""
        match scan_type:
            case ScanType.SIMILARITY:
                return await self._similarity_scan(scan_id, message, platform_id)
            case _:
                logger.warning(f"Unknown scan type: {scan_type}")
                return None

    async def _similarity_scan(
        self,
        scan_id: UUID,
        message: BulkScanMessage,
        platform_id: str,
    ) -> FlaggedMessage | None:
        """Run similarity search on a message."""
        try:
            search_response = await self.embedding_service.similarity_search(
                db=self.session,
                query_text=message.content,
                community_server_id=platform_id,
                dataset_tags=[],
                similarity_threshold=settings.SIMILARITY_SEARCH_DEFAULT_THRESHOLD,
                rrf_score_threshold=0.1,
                limit=1,
            )

            if search_response.matches:
                best_match = search_response.matches[0]
                return self._build_flagged_message(message, best_match, ScanType.SIMILARITY)

        except Exception as e:
            logger.warning(
                "Error in similarity scan",
                extra={"scan_id": str(scan_id), "error": str(e)},
            )

        return None

    def _build_flagged_message(
        self,
        message: BulkScanMessage,
        match: Any,
        scan_type: ScanType,
    ) -> FlaggedMessage:
        """Build FlaggedMessage from a match result."""
        return FlaggedMessage(
            message_id=message.message_id,
            channel_id=message.channel_id,
            content=message.content,
            author_id=message.author_id,
            timestamp=message.timestamp,
            match_score=match.similarity_score,
            matched_claim=match.content or match.title or "",
            matched_source=match.source_url or "",
            scan_type=scan_type,
        )

    async def append_flagged_result(
        self,
        scan_id: UUID,
        flagged_message: FlaggedMessage,
    ) -> None:
        """Append a single flagged result to Redis list."""
        redis_key = _get_redis_results_key(scan_id)
        await self.redis_client.lpush(redis_key, flagged_message.model_dump_json())
        await self.redis_client.expire(redis_key, REDIS_TTL_SECONDS)

    async def complete_scan(
        self,
        scan_id: UUID,
        messages_scanned: int,
        messages_flagged: int,
        status: BulkScanStatus = BulkScanStatus.COMPLETED,
    ) -> None:
        """Update scan log with completion data.

        Uses row-level locking (SELECT ... FOR UPDATE) to prevent race conditions
        when concurrent calls attempt to complete the same scan.

        Args:
            scan_id: UUID of the scan to complete
            messages_scanned: Total messages scanned
            messages_flagged: Number of messages flagged
            status: Final status (default: BulkScanStatus.COMPLETED)
        """
        stmt = select(BulkContentScanLog).where(BulkContentScanLog.id == scan_id).with_for_update()
        result = await self.session.execute(stmt)
        scan_log = result.scalar_one_or_none()

        if scan_log:
            scan_log.completed_at = datetime.now(UTC)
            scan_log.messages_scanned = messages_scanned
            scan_log.messages_flagged = messages_flagged
            scan_log.status = status
            await self.session.commit()

            logger.info(
                "Bulk content scan completed",
                extra={
                    "scan_id": str(scan_id),
                    "messages_scanned": messages_scanned,
                    "messages_flagged": messages_flagged,
                    "status": status,
                },
            )

    async def get_scan(self, scan_id: UUID) -> BulkContentScanLog | None:
        """Get scan log by ID.

        Args:
            scan_id: UUID of the scan

        Returns:
            BulkContentScanLog or None if not found
        """
        return await self.session.get(BulkContentScanLog, scan_id)

    async def store_flagged_results(
        self,
        scan_id: UUID,
        flagged_messages: list[FlaggedMessage],
    ) -> None:
        """Store flagged results in Redis list for later retrieval.

        Args:
            scan_id: UUID of the scan
            flagged_messages: List of flagged messages to store
        """
        redis_key = _get_redis_results_key(scan_id)

        for msg in flagged_messages:
            await self.redis_client.lpush(redis_key, msg.model_dump_json())
        if flagged_messages:
            await self.redis_client.expire(redis_key, REDIS_TTL_SECONDS)

        logger.debug(
            "Stored flagged results for bulk scan",
            extra={
                "scan_id": str(scan_id),
                "flagged_count": len(flagged_messages),
            },
        )

    async def get_flagged_results(self, scan_id: UUID) -> list[FlaggedMessage]:
        """Get flagged results from Redis list.

        Args:
            scan_id: UUID of the scan

        Returns:
            List of FlaggedMessage objects
        """
        redis_key = _get_redis_results_key(scan_id)

        raw_messages = await self.redis_client.lrange(redis_key, 0, -1)
        results = []
        for raw_msg in raw_messages:
            msg_str = raw_msg.decode() if isinstance(raw_msg, bytes) else raw_msg
            results.append(FlaggedMessage.model_validate_json(msg_str))
        return results
