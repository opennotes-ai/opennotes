"""Service layer for Bulk Content Scan operations."""

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.bulk_content_scan.models import BulkContentScanLog
from src.bulk_content_scan.schemas import FlaggedMessage
from src.config import settings
from src.fact_checking.embedding_service import EmbeddingService
from src.monitoring import get_logger

logger = get_logger(__name__)

REDIS_KEY_PREFIX = "bulk_scan"
REDIS_MESSAGES_KEY = f"{REDIS_KEY_PREFIX}:messages"
REDIS_RESULTS_KEY = f"{REDIS_KEY_PREFIX}:results"
REDIS_TTL_SECONDS = 86400  # 24 hours


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
            status="pending",
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

    async def collect_messages(
        self,
        scan_id: UUID,
        messages: list[dict[str, Any]],
    ) -> None:
        """Collect messages during scan iteration and store in Redis.

        Args:
            scan_id: UUID of the scan these messages belong to
            messages: List of message dicts with message_id, channel_id, content, author_id, timestamp
        """
        redis_key = f"{REDIS_MESSAGES_KEY}:{scan_id}"

        for msg in messages:
            await self.redis_client.lpush(redis_key, json.dumps(msg))

        await self.redis_client.expire(redis_key, REDIS_TTL_SECONDS)

        logger.debug(
            "Collected messages for bulk scan",
            extra={
                "scan_id": str(scan_id),
                "message_count": len(messages),
            },
        )

    async def process_collected_messages(
        self,
        scan_id: UUID,
        community_server_id: UUID,  # noqa: ARG002 - kept for API consistency
        platform_id: str,
    ) -> list[FlaggedMessage]:
        """Run similarity search on all collected messages.

        Args:
            scan_id: UUID of the scan to process
            community_server_id: UUID of the community server
            platform_id: Platform-specific ID (e.g., Discord guild ID) for embedding service

        Returns:
            List of flagged messages with match information
        """
        redis_key = f"{REDIS_MESSAGES_KEY}:{scan_id}"

        raw_messages = await self.redis_client.lrange(redis_key, 0, -1)
        messages = [json.loads(msg) for msg in raw_messages]

        logger.info(
            "Processing collected messages for bulk scan",
            extra={
                "scan_id": str(scan_id),
                "message_count": len(messages),
            },
        )

        flagged: list[FlaggedMessage] = []

        for msg in messages:
            content = msg.get("content", "")
            if not content or len(content.strip()) < 10:
                continue

            try:
                search_response = await self.embedding_service.similarity_search(
                    db=self.session,
                    query_text=content,
                    community_server_id=platform_id,
                    dataset_tags=[],  # Search all datasets
                    similarity_threshold=settings.SIMILARITY_SEARCH_DEFAULT_THRESHOLD,
                    rrf_score_threshold=0.1,
                    limit=1,
                )

                if search_response.matches:
                    best_match = search_response.matches[0]

                    timestamp_str = msg.get("timestamp", "")
                    if isinstance(timestamp_str, str):
                        timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                    else:
                        timestamp = timestamp_str

                    flagged.append(
                        FlaggedMessage(
                            message_id=msg["message_id"],
                            channel_id=msg["channel_id"],
                            content=content,
                            author_id=msg["author_id"],
                            timestamp=timestamp,
                            match_score=best_match.similarity_score,
                            matched_claim=best_match.content or best_match.title or "",
                            matched_source=best_match.source_url or "",
                        )
                    )

            except Exception as e:
                logger.warning(
                    "Error processing message for bulk scan",
                    extra={
                        "scan_id": str(scan_id),
                        "message_id": msg.get("message_id"),
                        "error": str(e),
                    },
                )
                continue

        logger.info(
            "Bulk scan processing completed",
            extra={
                "scan_id": str(scan_id),
                "messages_processed": len(messages),
                "messages_flagged": len(flagged),
            },
        )

        return flagged

    async def complete_scan(
        self,
        scan_id: UUID,
        messages_scanned: int,
        messages_flagged: int,
        status: str = "completed",
    ) -> None:
        """Update scan log with completion data.

        Args:
            scan_id: UUID of the scan to complete
            messages_scanned: Total messages scanned
            messages_flagged: Number of messages flagged
            status: Final status (default: "completed")
        """
        scan_log = await self.session.get(BulkContentScanLog, scan_id)

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

        redis_key = f"{REDIS_MESSAGES_KEY}:{scan_id}"
        await self.redis_client.delete(redis_key)

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
        """Store flagged results in Redis for later retrieval.

        Args:
            scan_id: UUID of the scan
            flagged_messages: List of flagged messages to store
        """
        redis_key = f"{REDIS_RESULTS_KEY}:{scan_id}"

        serialized = json.dumps([msg.model_dump(mode="json") for msg in flagged_messages])
        await self.redis_client.set(redis_key, serialized, ex=REDIS_TTL_SECONDS)

        logger.debug(
            "Stored flagged results for bulk scan",
            extra={
                "scan_id": str(scan_id),
                "flagged_count": len(flagged_messages),
            },
        )

    async def get_flagged_results(self, scan_id: UUID) -> list[FlaggedMessage]:
        """Get flagged results from Redis.

        Args:
            scan_id: UUID of the scan

        Returns:
            List of FlaggedMessage objects
        """
        redis_key = f"{REDIS_RESULTS_KEY}:{scan_id}"

        data = await self.redis_client.get(redis_key)
        if not data:
            return []

        if isinstance(data, bytes):
            data = data.decode()

        raw_messages = json.loads(data)
        return [FlaggedMessage.model_validate(msg) for msg in raw_messages]
