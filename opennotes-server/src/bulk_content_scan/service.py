"""Service layer for Bulk Content Scan operations."""

import asyncio
import json
import time
import uuid as uuid_module
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, Literal, overload
from uuid import UUID

from pydantic import ValidationError
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.bulk_content_scan.flashpoint_service import FlashpointDetectionService
from src.bulk_content_scan.models import BulkContentScanLog
from src.bulk_content_scan.scan_types import DEFAULT_SCAN_TYPES, ScanType
from src.bulk_content_scan.schemas import (
    BulkScanMessage,
    BulkScanStatus,
    ConversationFlashpointMatch,
    FlaggedMessage,
    OpenAIModerationMatch,
    RelevanceCheckResult,
    RelevanceOutcome,
    ScanCandidate,
    SimilarityMatch,
)
from src.claim_relevance_check.prompt_optimization.prompts import get_optimized_prompts
from src.config import settings
from src.fact_checking.embedding_schemas import FactCheckMatch
from src.fact_checking.embedding_service import EmbeddingService
from src.llm_config.providers.base import LLMMessage
from src.llm_config.service import LLMService
from src.monitoring import get_logger
from src.monitoring.metrics import relevance_check_total

logger = get_logger(__name__)

REDIS_KEY_PREFIX = "bulk_scan"
REDIS_TTL_SECONDS = 86400  # 24 hours


def calculate_indeterminate_threshold(base_threshold: float) -> float:
    """Apply tighter threshold for indeterminate relevance check results.

    When the LLM relevance check returns INDETERMINATE (typically because the
    fact-check content triggered a content filter), we apply a stricter threshold
    to the similarity score before flagging the message.

    Formula: threshold + ((1 - threshold) / 2)

    This moves the threshold halfway between the original value and 1.0,
    requiring a higher similarity score to flag when relevance is uncertain.

    Examples:
        - 0.35 -> 0.675
        - 0.60 -> 0.80
        - 0.80 -> 0.90

    Args:
        base_threshold: The original similarity threshold (0.0 to 1.0)

    Returns:
        The tighter threshold for indeterminate cases
    """
    return base_threshold + ((1.0 - base_threshold) / 2.0)


def _get_redis_results_key(scan_id: UUID) -> str:
    """Get environment-prefixed Redis key for scan results.

    Format: {environment}:{prefix}:results:{scan_id}
    Example: production:bulk_scan:results:abc-123
    """
    return f"{settings.ENVIRONMENT}:{REDIS_KEY_PREFIX}:results:{scan_id}"


def _get_redis_errors_key(scan_id: UUID) -> str:
    """Get environment-prefixed Redis key for scan errors.

    Format: {environment}:{prefix}:errors:{scan_id}
    Example: production:bulk_scan:errors:abc-123
    """
    return f"{settings.ENVIRONMENT}:{REDIS_KEY_PREFIX}:errors:{scan_id}"


def _get_redis_error_counts_key(scan_id: UUID) -> str:
    """Get environment-prefixed Redis key for error type counts.

    Format: {environment}:{prefix}:error_counts:{scan_id}
    Example: production:bulk_scan:error_counts:abc-123
    """
    return f"{settings.ENVIRONMENT}:{REDIS_KEY_PREFIX}:error_counts:{scan_id}"


def _get_redis_skipped_count_key(scan_id: UUID) -> str:
    """Get environment-prefixed Redis key for skipped message count.

    Messages are skipped when they already have a note request associated
    with them (via platform_message_id).

    Format: {environment}:{prefix}:skipped:{scan_id}
    Example: production:bulk_scan:skipped:abc-123
    """
    return f"{settings.ENVIRONMENT}:{REDIS_KEY_PREFIX}:skipped:{scan_id}"


class BulkContentScanService:
    """Service for managing bulk content scans."""

    def __init__(
        self,
        session: AsyncSession,
        embedding_service: EmbeddingService,
        redis_client: Redis,
        moderation_service: Any | None = None,
        llm_service: LLMService | None = None,
        flashpoint_service: FlashpointDetectionService | None = None,
    ) -> None:
        """Initialize the service.

        Args:
            session: Database session for scan log operations
            embedding_service: Service for similarity search
            redis_client: Redis client for temporary message storage
            moderation_service: Optional OpenAI moderation service for content moderation
            llm_service: Optional LLM service for relevance checking
            flashpoint_service: Optional FlashpointDetectionService for conversation derailment detection
        """
        self.session = session
        self.embedding_service = embedding_service
        self.redis_client = redis_client
        self.moderation_service = moderation_service
        self.llm_service = llm_service
        self.flashpoint_service = flashpoint_service

    async def initiate_scan(
        self,
        community_server_id: UUID,
        initiated_by_user_id: UUID,
        scan_window_days: int,
        expected_messages: int | None = None,
    ) -> BulkContentScanLog:
        """Create a new scan log entry and return it.

        Args:
            community_server_id: UUID of the community server to scan
            initiated_by_user_id: UUID of the user who initiated the scan
            scan_window_days: Number of days to scan back
            expected_messages: Number of messages expected to be scanned.
                If 0, the scan is immediately marked as completed since there
                are no messages to process (e.g., all filtered out as bots/empty).

        Returns:
            Created BulkContentScanLog entry
        """
        if expected_messages == 0:
            scan_log = BulkContentScanLog(
                community_server_id=community_server_id,
                initiated_by_user_id=initiated_by_user_id,
                scan_window_days=scan_window_days,
                status=BulkScanStatus.COMPLETED,
                completed_at=datetime.now(UTC),
                messages_scanned=0,
                messages_flagged=0,
            )
        else:
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

    @overload
    async def process_messages(
        self,
        scan_id: UUID,
        messages: BulkScanMessage | Sequence[BulkScanMessage],
        community_server_platform_id: str,
        scan_types: Sequence[ScanType] = ...,
        collect_scores: Literal[False] = ...,
    ) -> list[FlaggedMessage]: ...

    @overload
    async def process_messages(
        self,
        scan_id: UUID,
        messages: BulkScanMessage | Sequence[BulkScanMessage],
        community_server_platform_id: str,
        scan_types: Sequence[ScanType] = ...,
        collect_scores: Literal[True] = ...,
    ) -> tuple[list[FlaggedMessage], list[dict]]: ...

    async def process_messages(  # noqa: PLR0912
        self,
        scan_id: UUID,
        messages: BulkScanMessage | Sequence[BulkScanMessage],
        community_server_platform_id: str,
        scan_types: Sequence[ScanType] = DEFAULT_SCAN_TYPES,
        collect_scores: bool = False,
    ) -> list[FlaggedMessage] | tuple[list[FlaggedMessage], list[dict]]:
        """Process one or more messages through specified scan types.

        Uses the candidate-based flow:
        1. Filter out messages that already have note requests (via platform_message_id)
        2. Generate candidates via _similarity_scan_candidate() / _moderation_scan_candidate()
        3. Pass ALL candidates through _filter_candidates_with_relevance()
        4. Return filtered FlaggedMessage list (and optionally score info)

        The filtering logic is IDENTICAL regardless of collect_scores setting.
        Debug mode only affects whether score information is collected and returned.

        Flashpoint detection runs independently of other scan types. Content scan types
        (similarity, moderation) use first-match-wins with break. Flashpoint always runs
        when enabled, so both a content match and a flashpoint match can be produced for
        the same message.

        Args:
            scan_id: UUID of the scan
            messages: Single BulkScanMessage OR sequence of messages
            community_server_platform_id: CommunityServer.platform_community_server_id (e.g., Discord guild ID)
            scan_types: Sequence of ScanType to run (default: all)
            collect_scores: If True, also collect and return score info for debug mode

        Returns:
            If collect_scores=False: List of FlaggedMessage
            If collect_scores=True: Tuple of (flagged_messages, all_scores)
        """
        if isinstance(messages, BulkScanMessage):
            messages = [messages]

        active_scan_types = list(scan_types)
        if (
            ScanType.CONVERSATION_FLASHPOINT in active_scan_types
            and not await self._is_flashpoint_enabled(community_server_platform_id)
        ):
            active_scan_types = [
                st for st in active_scan_types if st != ScanType.CONVERSATION_FLASHPOINT
            ]

        original_count = len(messages)

        platform_message_ids = [msg.message_id for msg in messages]
        existing_ids = await self.get_existing_request_message_ids(platform_message_ids)

        if existing_ids:
            messages = [msg for msg in messages if msg.message_id not in existing_ids]
            skipped_count = original_count - len(messages)
            await self.increment_skipped_count(scan_id, skipped_count)
            logger.info(
                "Skipped messages with existing note requests",
                extra={
                    "scan_id": str(scan_id),
                    "skipped_count": skipped_count,
                    "remaining_count": len(messages),
                },
            )

        candidates: list[ScanCandidate] = []
        all_scores: list[dict] = []

        needs_context = ScanType.CONVERSATION_FLASHPOINT in active_scan_types
        channel_context_map = self._build_channel_context_map(messages) if needs_context else {}
        message_id_index = (
            self._build_message_id_index(channel_context_map) if needs_context else None
        )

        for msg in messages:
            if not msg.content or len(msg.content.strip()) < 10:
                if collect_scores:
                    all_scores.append(self._build_empty_score_info(msg))
                continue

            context_messages = (
                self._get_context_for_message(msg, channel_context_map, message_id_index)
                if needs_context
                else None
            )

            candidate_found = False

            content_scan_types = [
                st for st in active_scan_types if st != ScanType.CONVERSATION_FLASHPOINT
            ]
            for scan_type in content_scan_types:
                candidate = await self._generate_candidate(
                    scan_id,
                    msg,
                    community_server_platform_id,
                    scan_type,
                    context_messages=context_messages,
                )
                if candidate:
                    candidates.append(candidate)
                    if collect_scores:
                        all_scores.append(self._build_score_info_from_candidate(candidate))
                    candidate_found = True
                    break

            if ScanType.CONVERSATION_FLASHPOINT in active_scan_types:
                fp_candidate = await self._generate_candidate(
                    scan_id,
                    msg,
                    community_server_platform_id,
                    ScanType.CONVERSATION_FLASHPOINT,
                    context_messages=context_messages,
                )
                if fp_candidate:
                    candidates.append(fp_candidate)
                    if collect_scores and not candidate_found:
                        all_scores.append(self._build_score_info_from_candidate(fp_candidate))
                    candidate_found = True

            if not candidate_found and collect_scores:
                all_scores.append(self._build_empty_score_info(msg))

        flagged = await self._filter_candidates_with_relevance(candidates, scan_id)

        if collect_scores:
            flagged_message_ids = {fm.message_id for fm in flagged}
            for score_info in all_scores:
                score_info["is_flagged"] = score_info["message_id"] in flagged_message_ids
            return flagged, all_scores

        return flagged

    async def process_messages_with_scores(
        self,
        scan_id: UUID,
        messages: BulkScanMessage | Sequence[BulkScanMessage],
        community_server_platform_id: str,
        scan_types: Sequence[ScanType] = DEFAULT_SCAN_TYPES,
    ) -> tuple[list[FlaggedMessage], list[dict]]:
        """Process messages and return both flagged results and all scores.

        DEPRECATED: Use process_messages(..., collect_scores=True) instead.
        This method exists for backward compatibility.

        Args:
            scan_id: UUID of the scan
            messages: Single BulkScanMessage OR sequence of messages
            community_server_platform_id: CommunityServer.platform_community_server_id
            scan_types: Sequence of ScanType to run (default: all)

        Returns:
            Tuple of (flagged_messages, all_scores)
        """
        return await self.process_messages(  # type: ignore[return-value]
            scan_id=scan_id,
            messages=messages,
            community_server_platform_id=community_server_platform_id,
            scan_types=scan_types,
            collect_scores=True,
        )

    async def _generate_candidate(
        self,
        scan_id: UUID,
        message: BulkScanMessage,
        community_server_platform_id: str,
        scan_type: ScanType,
        context_messages: list[BulkScanMessage] | None = None,
    ) -> ScanCandidate | None:
        """Generate a ScanCandidate using the appropriate scanner.

        This dispatches to _similarity_scan_candidate(), _moderation_scan_candidate(),
        or _flashpoint_scan_candidate() based on scan_type.

        Args:
            scan_id: UUID of the scan
            message: The message to scan
            community_server_platform_id: CommunityServer.platform_community_server_id
            scan_type: Type of scan to run
            context_messages: Previous messages in the channel for flashpoint detection

        Returns:
            ScanCandidate if match found, None otherwise
        """
        match scan_type:
            case ScanType.SIMILARITY:
                return await self._similarity_scan_candidate(
                    scan_id, message, community_server_platform_id
                )
            case ScanType.OPENAI_MODERATION:
                return await self._moderation_scan_candidate(scan_id, message)
            case ScanType.CONVERSATION_FLASHPOINT:
                return await self._flashpoint_scan_candidate(
                    scan_id, message, context_messages or []
                )
            case _:
                logger.warning(f"Unknown scan type: {scan_type}")
                return None

    def _build_score_info_from_candidate(self, candidate: ScanCandidate) -> dict:
        """Build score_info dict from a ScanCandidate for debug mode.

        Args:
            candidate: The ScanCandidate to extract score info from

        Returns:
            Dictionary with score info for debug output
        """
        score_info: dict = {
            "message_id": candidate.message.message_id,
            "channel_id": candidate.message.channel_id,
            "similarity_score": candidate.score,
            "is_flagged": False,
            "matched_claim": candidate.matched_content,
        }

        if candidate.scan_type == ScanType.OPENAI_MODERATION.value and isinstance(
            candidate.match_data, OpenAIModerationMatch
        ):
            score_info["moderation_flagged"] = True
            score_info["moderation_categories"] = candidate.match_data.categories
            score_info["moderation_scores"] = candidate.match_data.scores

        return score_info

    def _build_empty_score_info(self, message: BulkScanMessage) -> dict:
        """Build empty score info dict for messages that weren't candidates."""
        return {
            "message_id": message.message_id,
            "channel_id": message.channel_id,
            "similarity_score": 0.0,
            "is_flagged": False,
            "matched_claim": None,
        }

    def _build_channel_context_map(
        self, messages: Sequence[BulkScanMessage]
    ) -> dict[str, list[BulkScanMessage]]:
        """Build a map of channel_id -> sorted messages for context lookup.

        Args:
            messages: Sequence of messages to organize by channel

        Returns:
            Dictionary mapping channel_id to list of messages sorted by timestamp
        """
        channel_messages: dict[str, list[BulkScanMessage]] = {}
        for msg in messages:
            if msg.channel_id not in channel_messages:
                channel_messages[msg.channel_id] = []
            channel_messages[msg.channel_id].append(msg)

        for msgs in channel_messages.values():
            msgs.sort(key=lambda m: m.timestamp)

        return channel_messages

    def _get_context_for_message(
        self,
        message: BulkScanMessage,
        channel_context_map: dict[str, list[BulkScanMessage]],
        message_id_index: dict[str, dict[str, int]] | None = None,
    ) -> list[BulkScanMessage]:
        """Get previous messages in the same channel as context.

        Args:
            message: The message to get context for
            channel_context_map: Map of channel_id -> sorted messages
            message_id_index: Optional pre-built index of channel_id -> {message_id -> position}
                for O(1) lookup instead of linear scan

        Returns:
            List of messages that occurred before this message in the same channel
        """
        channel_msgs = channel_context_map.get(message.channel_id, [])
        if message_id_index is not None:
            channel_index = message_id_index.get(message.channel_id, {})
            msg_index = channel_index.get(message.message_id, -1)
        else:
            msg_index = next(
                (i for i, m in enumerate(channel_msgs) if m.message_id == message.message_id),
                -1,
            )
        return channel_msgs[:msg_index] if msg_index > 0 else []

    def _build_message_id_index(
        self,
        channel_context_map: dict[str, list[BulkScanMessage]],
    ) -> dict[str, dict[str, int]]:
        """Pre-build a message_id-to-index dict for O(1) context lookup.

        Instead of doing a linear scan per message (O(n^2) per batch),
        this builds the index once so _get_context_for_message can do O(1) lookups.

        Args:
            channel_context_map: Map of channel_id -> sorted messages

        Returns:
            Dict mapping channel_id -> {message_id -> position_index}
        """
        index: dict[str, dict[str, int]] = {}
        for channel_id, msgs in channel_context_map.items():
            index[channel_id] = {m.message_id: i for i, m in enumerate(msgs)}
        return index

    async def _is_flashpoint_enabled(self, community_server_platform_id: str) -> bool:
        """Check if flashpoint detection is enabled for the community server.

        Args:
            community_server_platform_id: The platform-specific community ID (e.g., Discord guild ID)

        Returns:
            True if flashpoint detection is enabled, False otherwise
        """
        from src.llm_config.models import CommunityServer  # noqa: PLC0415

        try:
            result = await self.session.execute(
                select(CommunityServer.flashpoint_detection_enabled).where(
                    CommunityServer.platform_community_server_id == community_server_platform_id
                )
            )
            enabled = result.scalar_one_or_none()
            return bool(enabled)
        except Exception:
            logger.warning(
                "Failed to check flashpoint_detection_enabled, defaulting to disabled",
                extra={"community_server_platform_id": community_server_platform_id},
                exc_info=True,
            )
            return False

    async def _run_scanner_with_score(
        self,
        scan_id: UUID,
        message: BulkScanMessage,
        community_server_platform_id: str,
        scan_type: ScanType,
        context_messages: list[BulkScanMessage] | None = None,
    ) -> tuple[FlaggedMessage | None, dict]:
        """Run scanner and return both the flagged result and score info."""
        match scan_type:
            case ScanType.SIMILARITY:
                return await self._similarity_scan_with_score(
                    scan_id, message, community_server_platform_id
                )
            case ScanType.OPENAI_MODERATION:
                return await self._openai_moderation_scan_with_score(scan_id, message)
            case ScanType.CONVERSATION_FLASHPOINT:
                candidate = await self._flashpoint_scan_candidate(
                    scan_id, message, context_messages or []
                )
                if candidate:
                    flagged_msg = FlaggedMessage(
                        message_id=message.message_id,
                        channel_id=message.channel_id,
                        content=message.content,
                        author_id=message.author_id,
                        timestamp=message.timestamp,
                        matches=[candidate.match_data],
                    )
                    return flagged_msg, self._build_score_info_from_candidate(candidate)
                return None, self._build_empty_score_info(message)
            case _:
                logger.warning(f"Unknown scan type: {scan_type}")
                return None, {
                    "message_id": message.message_id,
                    "channel_id": message.channel_id,
                    "similarity_score": 0.0,
                    "is_flagged": False,
                    "matched_claim": None,
                }

    async def _similarity_scan_with_score(
        self,
        scan_id: UUID,
        message: BulkScanMessage,
        community_server_platform_id: str,
    ) -> tuple[FlaggedMessage | None, dict]:
        """Run similarity search and return both flagged result and score info."""
        return await self._similarity_scan(  # type: ignore[return-value]
            scan_id, message, community_server_platform_id, include_score=True
        )

    async def _run_scanner(
        self,
        scan_id: UUID,
        message: BulkScanMessage,
        community_server_platform_id: str,
        scan_type: ScanType,
        context_messages: list[BulkScanMessage] | None = None,
    ) -> FlaggedMessage | None:
        """Run a specific scanner on a message."""
        match scan_type:
            case ScanType.SIMILARITY:
                return await self._similarity_scan(  # type: ignore[return-value]
                    scan_id, message, community_server_platform_id
                )
            case ScanType.OPENAI_MODERATION:
                return await self._openai_moderation_scan(scan_id, message)
            case ScanType.CONVERSATION_FLASHPOINT:
                candidate = await self._flashpoint_scan_candidate(
                    scan_id, message, context_messages or []
                )
                if candidate:
                    return FlaggedMessage(
                        message_id=message.message_id,
                        channel_id=message.channel_id,
                        content=message.content,
                        author_id=message.author_id,
                        timestamp=message.timestamp,
                        matches=[candidate.match_data],
                    )
                return None
            case _:
                logger.warning(f"Unknown scan type: {scan_type}")
                return None

    async def _similarity_scan(
        self,
        scan_id: UUID,
        message: BulkScanMessage,
        community_server_platform_id: str,
        include_score: bool = False,
    ) -> FlaggedMessage | None | tuple[FlaggedMessage | None, dict]:
        """Run similarity search on a message.

        Args:
            scan_id: The scan ID for logging
            message: The message to scan
            community_server_platform_id: The community server ID
            include_score: If True, returns tuple of (flagged_msg, score_info)

        Returns:
            If include_score=False: FlaggedMessage | None
            If include_score=True: tuple[FlaggedMessage | None, dict]
        """
        threshold = settings.SIMILARITY_SEARCH_DEFAULT_THRESHOLD
        indeterminate_threshold = calculate_indeterminate_threshold(threshold)

        score_info: dict | None = None
        if include_score:
            score_info = {
                "message_id": message.message_id,
                "channel_id": message.channel_id,
                "similarity_score": 0.0,
                "is_flagged": False,
                "matched_claim": None,
            }

        try:
            search_response = await self.embedding_service.similarity_search(
                db=self.session,
                query_text=message.content,
                community_server_id=community_server_platform_id,
                dataset_tags=[],
                similarity_threshold=0.0 if include_score else threshold,
                score_threshold=0.0 if include_score else 0.1,
                limit=1,
            )

            if search_response.matches:
                best_match = search_response.matches[0]

                if include_score and score_info is not None:
                    score_info["similarity_score"] = best_match.similarity_score
                    score_info["matched_claim"] = best_match.content or best_match.title or ""

                if not include_score or best_match.similarity_score >= threshold:
                    outcome, reasoning = await self._check_relevance_with_llm(
                        original_message=message.content,
                        matched_content=best_match.content or best_match.title or "",
                        matched_source=best_match.source_url,
                    )

                    should_flag = self._evaluate_relevance_outcome(
                        outcome=outcome,
                        reasoning=reasoning,
                        similarity_score=best_match.similarity_score,
                        threshold=threshold,
                        indeterminate_threshold=indeterminate_threshold,
                        message_id=message.message_id,
                        scan_id=scan_id,
                    )

                    if should_flag:
                        try:
                            flagged_msg = self._build_flagged_message(message, best_match)
                            if include_score and score_info is not None:
                                score_info["is_flagged"] = True
                                return flagged_msg, score_info
                            return flagged_msg
                        except Exception as build_error:
                            logger.error(
                                "Failed to build flagged message",
                                extra={
                                    "scan_id": str(scan_id),
                                    "message_id": message.message_id,
                                    "error": str(build_error),
                                    "similarity_score": best_match.similarity_score,
                                },
                            )

                    logger.info(
                        "Skipping flag due to relevance check",
                        extra={
                            "message_id": message.message_id,
                            "reasoning": reasoning,
                            "relevance_outcome": outcome.value,
                            "similarity_score": best_match.similarity_score,
                        },
                    )

        except Exception as e:
            logger.warning(
                "Error in similarity scan",
                extra={"scan_id": str(scan_id), "error": str(e)},
            )

        if include_score and score_info is not None:
            return None, score_info
        return None

    def _evaluate_relevance_outcome(
        self,
        outcome: RelevanceOutcome,
        reasoning: str,
        similarity_score: float,
        threshold: float,
        indeterminate_threshold: float,
        message_id: str,
        scan_id: UUID,
    ) -> bool:
        """Evaluate relevance outcome and emit metrics. Returns True if should flag."""
        if outcome == RelevanceOutcome.RELEVANT:
            relevance_check_total.labels(
                outcome="candidate_relevant",
                decision="flagged",
                instance_id=settings.INSTANCE_ID,
            ).inc()
            return True

        if outcome == RelevanceOutcome.INDETERMINATE:
            if similarity_score >= indeterminate_threshold:
                logger.info(
                    "Relevance check indeterminate, applying tighter threshold",
                    extra={
                        "original_threshold": threshold,
                        "adjusted_threshold": indeterminate_threshold,
                        "reason": "content_filter_on_fact_check",
                        "message_id": message_id,
                        "scan_id": str(scan_id),
                        "score": similarity_score,
                        "reasoning": reasoning,
                    },
                )
                relevance_check_total.labels(
                    outcome="indeterminate",
                    decision="tighter_threshold_passed",
                    instance_id=settings.INSTANCE_ID,
                ).inc()
                return True

            logger.info(
                "Relevance check indeterminate, filtered by tighter threshold",
                extra={
                    "original_threshold": threshold,
                    "adjusted_threshold": indeterminate_threshold,
                    "reason": "content_filter_on_fact_check",
                    "message_id": message_id,
                    "scan_id": str(scan_id),
                    "score": similarity_score,
                    "reasoning": reasoning,
                },
            )
            relevance_check_total.labels(
                outcome="indeterminate",
                decision="tighter_threshold_filtered",
                instance_id=settings.INSTANCE_ID,
            ).inc()
            return False

        if outcome == RelevanceOutcome.CONTENT_FILTERED:
            relevance_check_total.labels(
                outcome="content_filter",
                decision="user_message_flagged",
                instance_id=settings.INSTANCE_ID,
            ).inc()
            return False

        if outcome == RelevanceOutcome.NOT_RELEVANT:
            relevance_check_total.labels(
                outcome="candidate_not_relevant",
                decision="filtered",
                instance_id=settings.INSTANCE_ID,
            ).inc()

        return False

    async def _openai_moderation_scan(
        self,
        scan_id: UUID,
        message: BulkScanMessage,
    ) -> FlaggedMessage | None:
        """Run OpenAI moderation on a message."""
        if not self.moderation_service:
            logger.warning(
                "Moderation service not configured",
                extra={"scan_id": str(scan_id)},
            )
            return None

        try:
            if message.attachment_urls:
                moderation_result = await self.moderation_service.moderate_multimodal(
                    text=message.content,
                    image_urls=message.attachment_urls,
                )
            else:
                moderation_result = await self.moderation_service.moderate_text(message.content)

            if moderation_result.flagged:
                return self._build_moderation_flagged_message(message, moderation_result)

        except Exception as e:
            logger.warning(
                "Error in OpenAI moderation scan",
                extra={"scan_id": str(scan_id), "error": str(e)},
            )

        return None

    async def _openai_moderation_scan_with_score(
        self,
        scan_id: UUID,
        message: BulkScanMessage,
    ) -> tuple[FlaggedMessage | None, dict]:
        """Run OpenAI moderation and return both flagged result and score info."""
        score_info: dict = {
            "message_id": message.message_id,
            "channel_id": message.channel_id,
            "similarity_score": 0.0,
            "is_flagged": False,
            "matched_claim": None,
            "moderation_flagged": None,
            "moderation_categories": None,
            "moderation_scores": None,
        }

        if not self.moderation_service:
            logger.warning(
                "Moderation service not configured",
                extra={"scan_id": str(scan_id)},
            )
            return None, score_info

        try:
            if message.attachment_urls:
                moderation_result = await self.moderation_service.moderate_multimodal(
                    text=message.content,
                    image_urls=message.attachment_urls,
                )
            else:
                moderation_result = await self.moderation_service.moderate_text(message.content)

            score_info["similarity_score"] = moderation_result.max_score
            score_info["matched_claim"] = ", ".join(moderation_result.flagged_categories)
            score_info["moderation_flagged"] = moderation_result.flagged
            score_info["moderation_categories"] = moderation_result.categories
            score_info["moderation_scores"] = moderation_result.scores

            if moderation_result.flagged:
                try:
                    flagged_msg = self._build_moderation_flagged_message(message, moderation_result)
                    score_info["is_flagged"] = True
                    return flagged_msg, score_info
                except Exception as build_error:
                    logger.error(
                        "Failed to build moderation flagged message",
                        extra={
                            "scan_id": str(scan_id),
                            "message_id": message.message_id,
                            "error": str(build_error),
                        },
                    )

        except Exception as e:
            logger.warning(
                "Error in OpenAI moderation scan with score",
                extra={"scan_id": str(scan_id), "error": str(e)},
            )

        return None, score_info

    def _build_moderation_flagged_message(
        self,
        message: BulkScanMessage,
        moderation_result: Any,
    ) -> FlaggedMessage:
        """Build FlaggedMessage from a moderation result."""
        moderation_match = OpenAIModerationMatch(
            max_score=moderation_result.max_score,
            categories=moderation_result.categories,
            scores=moderation_result.scores,
            flagged_categories=moderation_result.flagged_categories,
        )
        return FlaggedMessage(
            message_id=message.message_id,
            channel_id=message.channel_id,
            content=message.content,
            author_id=message.author_id,
            timestamp=message.timestamp,
            matches=[moderation_match],
        )

    def _build_flagged_message(
        self,
        message: BulkScanMessage,
        match: FactCheckMatch,
    ) -> FlaggedMessage:
        """Build FlaggedMessage from a similarity match result."""
        similarity_match = SimilarityMatch(
            score=match.similarity_score,
            matched_claim=match.content or match.title or "",
            matched_source=match.source_url or "",
            fact_check_item_id=match.id,
        )
        return FlaggedMessage(
            message_id=message.message_id,
            channel_id=message.channel_id,
            content=message.content,
            author_id=message.author_id,
            timestamp=message.timestamp,
            matches=[similarity_match],
        )

    async def _similarity_scan_candidate(
        self,
        scan_id: UUID,
        message: BulkScanMessage,
        community_server_platform_id: str,
    ) -> ScanCandidate | None:
        """Run similarity search and return a ScanCandidate without relevance filtering.

        This method produces candidates for the unified relevance filter.
        It does NOT run the LLM relevance check inline.

        Args:
            scan_id: UUID of the scan
            message: The message to scan
            community_server_platform_id: CommunityServer.platform_community_server_id

        Returns:
            ScanCandidate if a match was found, None otherwise
        """
        try:
            search_response = await self.embedding_service.similarity_search(
                db=self.session,
                query_text=message.content,
                community_server_id=community_server_platform_id,
                dataset_tags=[],
                similarity_threshold=settings.SIMILARITY_SEARCH_DEFAULT_THRESHOLD,
                score_threshold=0.1,
                limit=1,
            )

            if search_response.matches:
                best_match = search_response.matches[0]
                matched_content = best_match.content or best_match.title or ""

                similarity_match = SimilarityMatch(
                    score=best_match.similarity_score,
                    matched_claim=matched_content,
                    matched_source=best_match.source_url or "",
                    fact_check_item_id=best_match.id,
                )

                return ScanCandidate(
                    message=message,
                    scan_type=ScanType.SIMILARITY.value,
                    match_data=similarity_match,
                    score=best_match.similarity_score,
                    matched_content=matched_content,
                    matched_source=best_match.source_url,
                )

        except Exception as e:
            logger.warning(
                "Error in similarity scan candidate",
                extra={"scan_id": str(scan_id), "error": str(e)},
            )

        return None

    async def _moderation_scan_candidate(
        self,
        scan_id: UUID,
        message: BulkScanMessage,
    ) -> ScanCandidate | None:
        """Run OpenAI moderation and return a ScanCandidate without relevance filtering.

        This method produces candidates for the unified relevance filter.

        Args:
            scan_id: UUID of the scan
            message: The message to scan

        Returns:
            ScanCandidate if content was flagged, None otherwise
        """
        if not self.moderation_service:
            logger.warning(
                "Moderation service not configured",
                extra={"scan_id": str(scan_id)},
            )
            return None

        try:
            if message.attachment_urls:
                moderation_result = await self.moderation_service.moderate_multimodal(
                    text=message.content,
                    image_urls=message.attachment_urls,
                )
            else:
                moderation_result = await self.moderation_service.moderate_text(message.content)

            if moderation_result.flagged:
                moderation_match = OpenAIModerationMatch(
                    max_score=moderation_result.max_score,
                    categories=moderation_result.categories,
                    scores=moderation_result.scores,
                    flagged_categories=moderation_result.flagged_categories,
                )

                matched_content = ", ".join(moderation_result.flagged_categories)

                return ScanCandidate(
                    message=message,
                    scan_type=ScanType.OPENAI_MODERATION.value,
                    match_data=moderation_match,
                    score=moderation_result.max_score,
                    matched_content=matched_content,
                    matched_source=None,
                )

        except Exception as e:
            logger.warning(
                "Error in moderation scan candidate",
                extra={"scan_id": str(scan_id), "error": str(e)},
            )

        return None

    async def _flashpoint_scan_candidate(
        self,
        scan_id: UUID,
        message: BulkScanMessage,
        context_messages: list[BulkScanMessage],
    ) -> ScanCandidate | None:
        """Run flashpoint detection and return a ScanCandidate.

        Detects early warning signs that a conversation may derail into conflict
        using a DSPy-optimized prompt trained on the Conversations Gone Awry corpus.

        Args:
            scan_id: UUID of the scan
            message: The message to analyze
            context_messages: Previous messages in the channel (time-ordered)

        Returns:
            ScanCandidate if flashpoint detected, None otherwise
        """
        if not self.flashpoint_service:
            logger.debug(
                "Flashpoint service not configured",
                extra={"scan_id": str(scan_id)},
            )
            return None

        try:
            match = await self.flashpoint_service.detect_flashpoint(
                message=message,
                context_messages=context_messages,
            )

            if match is None:
                return None

            return ScanCandidate(
                message=message,
                scan_type=ScanType.CONVERSATION_FLASHPOINT.value,
                match_data=match,
                score=match.confidence,
                matched_content=match.reasoning,
                matched_source=None,
            )

        except Exception as e:
            logger.warning(
                "Error in flashpoint scan candidate",
                extra={"scan_id": str(scan_id), "error": str(e)},
            )

        return None

    async def _filter_candidates_with_relevance(
        self,
        candidates: list[ScanCandidate],
        scan_id: UUID,
    ) -> list[FlaggedMessage]:
        """Filter ALL candidates through the unified LLM relevance check.

        This is the unified post-processing step that runs relevance checking
        on ALL candidates regardless of scan type.

        For INDETERMINATE outcomes (when fact-check content triggers content filter),
        applies a tighter threshold: new_threshold = threshold + ((1-threshold)/2).
        This allows high-confidence matches to still be flagged even when the LLM
        cannot definitively determine relevance.

        Args:
            candidates: List of ScanCandidate from all scan types
            scan_id: UUID of the scan for logging

        Returns:
            List of FlaggedMessage for candidates that pass relevance check
        """
        flagged: list[FlaggedMessage] = []
        base_threshold = settings.SIMILARITY_SEARCH_DEFAULT_THRESHOLD
        indeterminate_threshold = calculate_indeterminate_threshold(base_threshold)

        for candidate in candidates:
            logger.info(
                "Scan produced candidate",
                extra={
                    "scan_id": str(scan_id),
                    "message_id": candidate.message.message_id,
                    "scan_type": candidate.scan_type,
                    "score": candidate.score,
                },
            )

            if candidate.scan_type == ScanType.CONVERSATION_FLASHPOINT.value:
                should_flag = True
                reasoning = "Flashpoint candidates bypass relevance filter"
                outcome = RelevanceOutcome.RELEVANT
            else:
                outcome, reasoning = await self._check_relevance_with_llm(
                    original_message=candidate.message.content,
                    matched_content=candidate.matched_content,
                    matched_source=candidate.matched_source,
                )

                should_flag = self._evaluate_relevance_outcome(
                    outcome=outcome,
                    reasoning=reasoning,
                    similarity_score=candidate.score,
                    threshold=base_threshold,
                    indeterminate_threshold=indeterminate_threshold,
                    message_id=candidate.message.message_id,
                    scan_id=scan_id,
                )

            if should_flag:
                try:
                    flagged_msg = FlaggedMessage(
                        message_id=candidate.message.message_id,
                        channel_id=candidate.message.channel_id,
                        content=candidate.message.content,
                        author_id=candidate.message.author_id,
                        timestamp=candidate.message.timestamp,
                        matches=[candidate.match_data],
                    )
                    flagged.append(flagged_msg)
                except Exception as build_error:
                    logger.error(
                        "Failed to build flagged message from candidate",
                        extra={
                            "scan_id": str(scan_id),
                            "message_id": candidate.message.message_id,
                            "error": str(build_error),
                        },
                    )
            elif outcome not in (RelevanceOutcome.RELEVANT, RelevanceOutcome.INDETERMINATE):
                logger.info(
                    "Candidate filtered by relevance check",
                    extra={
                        "scan_id": str(scan_id),
                        "message_id": candidate.message.message_id,
                        "reasoning": reasoning,
                        "relevance_outcome": outcome.value,
                        "score": candidate.score,
                    },
                )

        logger.info(
            "Relevance filtering complete",
            extra={
                "scan_id": str(scan_id),
                "candidates_count": len(candidates),
                "flagged_count": len(flagged),
                "filter_ratio": len(flagged) / len(candidates) if candidates else 0,
            },
        )

        return flagged

    async def _check_relevance_with_llm(  # noqa: PLR0911
        self,
        original_message: str,
        matched_content: str,
        matched_source: str | None,
    ) -> tuple[RelevanceOutcome, str]:
        """Check if the matched content is relevant to the original message using LLM.

        Detects content filter responses and retries without fact-check content
        to distinguish between problematic user messages and problematic fact-checks.

        Args:
            original_message: The user's original message
            matched_content: The matched fact-check content
            matched_source: Optional source URL

        Returns:
            Tuple of (RelevanceOutcome, reasoning):
            - RELEVANT: Match is relevant, should flag
            - NOT_RELEVANT: Match not relevant, don't flag
            - INDETERMINATE: Couldn't determine relevance (timeout, validation error,
              general error, or fact-check triggered filter). Returns INDETERMINATE
              so the tighter threshold is applied, filtering low-confidence matches.
            - CONTENT_FILTERED: User message itself triggered filter
        """
        if not settings.RELEVANCE_CHECK_ENABLED:
            relevance_check_total.labels(
                outcome="disabled", decision="skipped", instance_id=settings.INSTANCE_ID
            ).inc()
            return (RelevanceOutcome.RELEVANT, "Relevance check disabled")

        if not self.llm_service:
            logger.warning("LLM service not configured for relevance check")
            relevance_check_total.labels(
                outcome="not_configured", decision="fail_open", instance_id=settings.INSTANCE_ID
            ).inc()
            return (RelevanceOutcome.RELEVANT, "LLM service not configured")

        start_time = time.monotonic()

        try:
            if settings.RELEVANCE_CHECK_USE_OPTIMIZED_PROMPT:
                system_prompt, user_prompt = get_optimized_prompts(
                    message=original_message,
                    fact_check_title=matched_content[:100],
                    fact_check_content=matched_content,
                    source_url=matched_source,
                )
            else:
                source_info = f"\nSource: {matched_source}" if matched_source else ""

                system_prompt = """You are a relevance checker. Determine if a reference can meaningfully fact-check or provide context for a SPECIFIC CLAIM in the user's message.

IMPORTANT: The message must contain a verifiable claim or assertion. Simple mentions of people, topics, or questions are NOT claims.

Examples:
- "how about biden" → No claim, just a name mention → NOT RELEVANT (confidence: 0.99)
- "or donald trump" → No claim, just a name → NOT RELEVANT (confidence: 0.99)
- "Biden was a Confederate soldier" → Specific false claim → RELEVANT (confidence: 0.95)
- "Trump's sons shot endangered animals" → Verifiable claim → RELEVANT (confidence: 0.90)
- "What about the vaccine?" → Question, not a claim → NOT RELEVANT (confidence: 0.98)
- "The vaccine causes autism" → Specific claim that can be fact-checked → RELEVANT (confidence: 0.92)

Respond with JSON: {"is_relevant": true/false, "reasoning": "brief explanation", "confidence": 0.0-1.0}"""

                user_prompt = f"""User message: {original_message}

Reference: {matched_content}{source_info}

Step 1: Does the user message contain a specific claim or assertion (not just a topic mention or question)?
Step 2: If YES to step 1, can this reference fact-check or verify that specific claim?
Step 3: How confident are you in this assessment? (0.0 = uncertain, 1.0 = certain)

Only answer RELEVANT if BOTH steps are YES. Include your confidence score in the response."""

            messages = [
                LLMMessage(role="system", content=system_prompt),
                LLMMessage(role="user", content=user_prompt),
            ]

            response = await asyncio.wait_for(
                self.llm_service.complete(
                    db=self.session,
                    messages=messages,
                    community_server_id=None,
                    provider=settings.RELEVANCE_CHECK_PROVIDER,
                    model=settings.RELEVANCE_CHECK_MODEL,
                    max_tokens=settings.RELEVANCE_CHECK_MAX_TOKENS,
                    temperature=0.0,
                    response_format=RelevanceCheckResult,
                ),
                timeout=settings.RELEVANCE_CHECK_TIMEOUT,
            )

            if response.finish_reason == "content_filter":
                latency_ms = (time.monotonic() - start_time) * 1000
                logger.warning(
                    "Content filter triggered during relevance check, retrying without fact-check",
                    extra={
                        "original_message_length": len(original_message),
                        "matched_content_length": len(matched_content),
                        "latency_ms": round(latency_ms, 2),
                    },
                )
                return await self._retry_without_fact_check(original_message, start_time)

            result = RelevanceCheckResult.model_validate_json(response.content)

            latency_ms = (time.monotonic() - start_time) * 1000
            logger.info(
                "Relevance check completed",
                extra={
                    "relevance_check_passed": result.is_relevant,
                    "relevance_reasoning": result.reasoning,
                    "relevance_confidence": result.confidence,
                    "latency_ms": round(latency_ms, 2),
                },
            )

            if not result.is_relevant:
                logger.debug(
                    "Content filtered by relevance check",
                    extra={
                        "outcome": "not_relevant",
                        "reasoning": result.reasoning,
                        "confidence": result.confidence,
                        "latency_ms": round(latency_ms, 2),
                    },
                )

            decision = "flagged" if result.is_relevant else "filtered"
            relevance_check_total.labels(
                outcome="success", decision=decision, instance_id=settings.INSTANCE_ID
            ).inc()

            outcome = (
                RelevanceOutcome.RELEVANT if result.is_relevant else RelevanceOutcome.NOT_RELEVANT
            )
            return (outcome, result.reasoning)

        except TimeoutError:
            latency_ms = (time.monotonic() - start_time) * 1000
            logger.warning(
                "Relevance check timed out, returning indeterminate for tighter threshold",
                extra={
                    "timeout_seconds": settings.RELEVANCE_CHECK_TIMEOUT,
                    "latency_ms": round(latency_ms, 2),
                },
            )
            relevance_check_total.labels(
                outcome="timeout",
                decision="fail_open_indeterminate",
                instance_id=settings.INSTANCE_ID,
            ).inc()
            return (
                RelevanceOutcome.INDETERMINATE,
                f"Relevance check timed out after {settings.RELEVANCE_CHECK_TIMEOUT}s",
            )

        except ValidationError as e:
            latency_ms = (time.monotonic() - start_time) * 1000
            logger.warning(
                "Relevance check JSON validation failed, returning indeterminate for tighter threshold",
                extra={
                    "validation_error": str(e),
                    "latency_ms": round(latency_ms, 2),
                },
            )
            relevance_check_total.labels(
                outcome="validation_error",
                decision="fail_open_indeterminate",
                instance_id=settings.INSTANCE_ID,
            ).inc()
            return (
                RelevanceOutcome.INDETERMINATE,
                f"Relevance check validation failed: {e}",
            )

        except Exception as e:
            latency_ms = (time.monotonic() - start_time) * 1000
            logger.warning(
                "Relevance check failed, returning indeterminate for tighter threshold",
                extra={
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "latency_ms": round(latency_ms, 2),
                },
            )
            relevance_check_total.labels(
                outcome="error",
                decision="fail_open_indeterminate",
                instance_id=settings.INSTANCE_ID,
            ).inc()
            return (
                RelevanceOutcome.INDETERMINATE,
                f"Relevance check failed: {e}",
            )

    async def _retry_without_fact_check(
        self,
        original_message: str,
        start_time: float,
    ) -> tuple[RelevanceOutcome, str]:
        """Retry relevance check with only the user message to isolate content filter source.

        Called when the initial relevance check triggers a content filter. By retrying
        with only the user's message (no fact-check content), we can determine:
        - If retry also triggers filter: user's message contains problematic content
        - If retry succeeds: fact-check content was the problem, treat as indeterminate

        Args:
            original_message: The user's original message (without fact-check content)
            start_time: Start time of the original check for latency tracking

        Returns:
            Tuple of (RelevanceOutcome, reasoning):
            - CONTENT_FILTERED: User message itself triggers content filter
            - INDETERMINATE: Fact-check content was the issue, can't determine relevance
        """
        if not self.llm_service:
            return (
                RelevanceOutcome.INDETERMINATE,
                "LLM service not configured for retry",
            )

        simplified_system_prompt = """Analyze this message for factual claims.
Respond with JSON: {"has_claims": true/false, "reasoning": "brief explanation"}"""

        messages = [
            LLMMessage(role="system", content=simplified_system_prompt),
            LLMMessage(role="user", content=original_message),
        ]

        try:
            response = await asyncio.wait_for(
                self.llm_service.complete(
                    db=self.session,
                    messages=messages,
                    community_server_id=None,
                    provider=settings.RELEVANCE_CHECK_PROVIDER,
                    model=settings.RELEVANCE_CHECK_MODEL,
                    max_tokens=settings.RELEVANCE_CHECK_MAX_TOKENS,
                    temperature=0.0,
                ),
                timeout=settings.RELEVANCE_CHECK_TIMEOUT,
            )

            latency_ms = (time.monotonic() - start_time) * 1000

            if response.finish_reason == "content_filter":
                logger.warning(
                    "Content filter triggered on user message alone",
                    extra={
                        "message_length": len(original_message),
                        "latency_ms": round(latency_ms, 2),
                    },
                )
                relevance_check_total.labels(
                    outcome="content_filter",
                    decision="message_filtered",
                    instance_id=settings.INSTANCE_ID,
                ).inc()
                return (
                    RelevanceOutcome.CONTENT_FILTERED,
                    "Message content triggered safety filter",
                )

            if response.finish_reason == "stop":
                log_level = "info"
                log_message = "Retry succeeded - fact-check content triggered original filter"
                metric_outcome = "content_filter"
                reasoning = "Fact-check content triggered safety filter; relevance indeterminate"
            elif response.finish_reason == "length":
                log_level = "warning"
                log_message = "Retry response truncated (max_tokens reached)"
                metric_outcome = "content_filter_retry_truncated"
                reasoning = "Retry response truncated; relevance indeterminate"
            else:
                log_level = "warning"
                log_message = "Unexpected finish_reason in retry response"
                metric_outcome = "content_filter_retry_unexpected"
                reasoning = (
                    f"Unexpected finish_reason: {response.finish_reason}; relevance indeterminate"
                )

            log_fn = logger.info if log_level == "info" else logger.warning
            log_fn(
                log_message,
                extra={
                    "message_length": len(original_message),
                    "latency_ms": round(latency_ms, 2),
                    "finish_reason": response.finish_reason,
                },
            )
            relevance_check_total.labels(
                outcome=metric_outcome,
                decision="factcheck_filtered"
                if response.finish_reason == "stop"
                else "indeterminate",
                instance_id=settings.INSTANCE_ID,
            ).inc()
            return (RelevanceOutcome.INDETERMINATE, reasoning)

        except TimeoutError:
            latency_ms = (time.monotonic() - start_time) * 1000
            logger.warning(
                "Retry timed out, treating as indeterminate",
                extra={
                    "timeout_seconds": settings.RELEVANCE_CHECK_TIMEOUT,
                    "latency_ms": round(latency_ms, 2),
                },
            )
            relevance_check_total.labels(
                outcome="content_filter_retry_timeout",
                decision="indeterminate",
                instance_id=settings.INSTANCE_ID,
            ).inc()
            return (
                RelevanceOutcome.INDETERMINATE,
                f"Retry timed out after {settings.RELEVANCE_CHECK_TIMEOUT}s",
            )

        except Exception as e:
            latency_ms = (time.monotonic() - start_time) * 1000
            logger.warning(
                "Retry failed, treating as indeterminate",
                extra={
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "latency_ms": round(latency_ms, 2),
                },
            )
            relevance_check_total.labels(
                outcome="content_filter_retry_error",
                decision="indeterminate",
                instance_id=settings.INSTANCE_ID,
            ).inc()
            return (
                RelevanceOutcome.INDETERMINATE,
                f"Retry failed: {e}",
            )

    async def append_flagged_result(
        self,
        scan_id: UUID,
        flagged_message: FlaggedMessage,
    ) -> None:
        """Append a single flagged result to Redis list."""
        redis_key = _get_redis_results_key(scan_id)
        await self.redis_client.lpush(redis_key, flagged_message.model_dump_json())  # type: ignore[misc]
        await self.redis_client.expire(redis_key, REDIS_TTL_SECONDS)  # type: ignore[misc]

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
            await self.redis_client.lpush(redis_key, msg.model_dump_json())  # type: ignore[misc]
        if flagged_messages:
            await self.redis_client.expire(redis_key, REDIS_TTL_SECONDS)  # type: ignore[misc]

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

        raw_messages = await self.redis_client.lrange(redis_key, 0, -1)  # type: ignore[misc]
        results = []
        for raw_msg in raw_messages:
            msg_str = raw_msg.decode() if isinstance(raw_msg, bytes) else raw_msg
            results.append(FlaggedMessage.model_validate_json(msg_str))
        return results

    async def record_error(
        self,
        scan_id: UUID,
        error_type: str,
        error_message: str,
        message_id: str | None = None,
        batch_number: int | None = None,
    ) -> None:
        """Record a processing error in Redis.

        Args:
            scan_id: UUID of the scan
            error_type: Type of error (e.g., 'TypeError')
            error_message: Error message details
            message_id: Message ID that caused the error (optional)
            batch_number: Batch number where error occurred (optional)
        """
        errors_key = _get_redis_errors_key(scan_id)
        counts_key = _get_redis_error_counts_key(scan_id)

        error_info = {
            "error_type": error_type,
            "message_id": message_id,
            "batch_number": batch_number,
            "error_message": error_message[:500],
        }

        await self.redis_client.lpush(errors_key, json.dumps(error_info))  # type: ignore[misc]
        await self.redis_client.hincrby(counts_key, error_type, 1)  # type: ignore[misc]

        await self.redis_client.expire(errors_key, REDIS_TTL_SECONDS)  # type: ignore[misc]
        await self.redis_client.expire(counts_key, REDIS_TTL_SECONDS)  # type: ignore[misc]

        logger.debug(
            "Recorded scan error",
            extra={
                "scan_id": str(scan_id),
                "error_type": error_type,
                "message_id": message_id,
                "batch_number": batch_number,
            },
        )

    async def increment_skipped_count(self, scan_id: UUID, count: int = 1) -> None:
        """Increment the count of skipped messages.

        Messages are skipped when they already have a note request associated
        with them (via platform_message_id).

        Args:
            scan_id: UUID of the scan
            count: Number of messages skipped
        """
        skipped_key = _get_redis_skipped_count_key(scan_id)
        await self.redis_client.incrby(skipped_key, count)  # type: ignore[misc]
        await self.redis_client.expire(skipped_key, REDIS_TTL_SECONDS)  # type: ignore[misc]

    async def get_skipped_count(self, scan_id: UUID) -> int:
        """Get the count of skipped messages.

        Args:
            scan_id: UUID of the scan

        Returns:
            Number of skipped messages (those with existing note requests)
        """
        skipped_key = _get_redis_skipped_count_key(scan_id)
        count = await self.redis_client.get(skipped_key)
        if count is None:
            return 0
        return int(count.decode() if isinstance(count, bytes) else count)

    async def get_existing_request_message_ids(
        self,
        platform_message_ids: list[str],
    ) -> set[str]:
        """Get set of platform_message_ids that already have note requests.

        This is used to filter out messages that already have requests before
        processing them in bulk content scanning, preventing duplicate requests.

        Args:
            platform_message_ids: List of platform message IDs to check. For optimal
                performance, batch sizes should stay under 1000 to avoid PostgreSQL
                IN clause performance degradation.

        Returns:
            Set of platform_message_ids that already have associated requests.
            Returns empty set on database errors (fail-open to avoid blocking scans).
        """
        if not platform_message_ids:
            return set()

        from src.notes.message_archive_models import MessageArchive  # noqa: PLC0415
        from src.notes.models import Request  # noqa: PLC0415

        try:
            stmt = (
                select(MessageArchive.platform_message_id)
                .distinct()
                .join(Request, Request.message_archive_id == MessageArchive.id)
                .where(MessageArchive.platform_message_id.in_(platform_message_ids))
            )

            result = await self.session.execute(stmt)
            existing_ids = {row[0] for row in result.fetchall() if row[0] is not None}

            if existing_ids:
                logger.info(
                    "Found messages with existing note requests",
                    extra={
                        "checked_count": len(platform_message_ids),
                        "existing_count": len(existing_ids),
                    },
                )

            return existing_ids
        except Exception:
            logger.warning(
                "Failed to check for existing note requests, processing all messages",
                extra={"checked_count": len(platform_message_ids)},
                exc_info=True,
            )
            return set()

    async def get_error_summary(self, scan_id: UUID) -> dict:
        """Get error summary from Redis.

        Args:
            scan_id: UUID of the scan

        Returns:
            Dictionary with error summary containing:
            - total_errors: Total count of errors
            - error_types: Dict mapping error type to count
            - sample_errors: List of sample error info dicts (up to 5)
        """
        errors_key = _get_redis_errors_key(scan_id)
        counts_key = _get_redis_error_counts_key(scan_id)

        error_counts = await self.redis_client.hgetall(counts_key)  # type: ignore[misc]
        error_types: dict[str, int] = {}
        total_errors = 0

        for error_type, count in error_counts.items():
            type_str = error_type.decode() if isinstance(error_type, bytes) else error_type
            count_int = int(count.decode() if isinstance(count, bytes) else count)
            error_types[type_str] = count_int
            total_errors += count_int

        raw_errors = await self.redis_client.lrange(errors_key, 0, 4)  # type: ignore[misc]
        sample_errors = []
        for raw_error in raw_errors:
            error_str = raw_error.decode() if isinstance(raw_error, bytes) else raw_error
            sample_errors.append(json.loads(error_str))

        return {
            "total_errors": total_errors,
            "error_types": error_types,
            "sample_errors": sample_errors,
        }


async def create_note_requests_from_flagged_messages(  # noqa: PLR0912
    message_ids: list[str],
    scan_id: UUID,
    session: AsyncSession,
    user_id: UUID,
    community_server_id: UUID,
    flagged_messages: list[FlaggedMessage],
    generate_ai_notes: bool = False,
) -> list[str]:
    """Create note requests for flagged messages from a bulk content scan.

    This is a shared function used by both the REST API and JSON:API routers
    to create Request entries in the database for selected flagged messages.

    Args:
        message_ids: List of Discord message IDs to create requests for
        scan_id: UUID of the scan these messages came from
        session: Database session
        user_id: UUID of the user making the request
        community_server_id: UUID of the community server
        flagged_messages: List of FlaggedMessage objects from the scan results
        generate_ai_notes: Whether to generate AI draft notes (default: False)

    Returns:
        List of created request IDs (string request_id values)
    """
    from src.events.publisher import event_publisher  # noqa: PLC0415
    from src.llm_config.models import CommunityServer  # noqa: PLC0415
    from src.notes.request_service import RequestService  # noqa: PLC0415

    logger.info(
        "Creating note requests from bulk scan",
        extra={
            "scan_id": str(scan_id),
            "message_count": len(message_ids),
            "user_id": str(user_id),
            "community_server_id": str(community_server_id),
            "generate_ai_notes": generate_ai_notes,
        },
    )

    platform_id: str | None = None
    if generate_ai_notes:
        result = await session.execute(
            select(CommunityServer.platform_community_server_id).where(
                CommunityServer.id == community_server_id
            )
        )
        platform_id = result.scalar_one_or_none()
        if not platform_id:
            logger.warning(
                "Community server platform_id not found, AI note generation will be skipped",
                extra={"community_server_id": str(community_server_id)},
            )
            generate_ai_notes = False

    flagged_by_message_id = {msg.message_id: msg for msg in flagged_messages}

    created_ids: list[str] = []
    for msg_id in message_ids:
        flagged_msg = flagged_by_message_id.get(msg_id)
        if not flagged_msg:
            logger.warning(
                "Message ID not found in flagged results",
                extra={
                    "message_id": msg_id,
                    "scan_id": str(scan_id),
                },
            )
            continue

        request_id = f"bulkscan_{scan_id.hex[:8]}_{uuid_module.uuid4().hex[:8]}"

        match_score = 0.0
        matched_claim = ""
        matched_source = ""
        first_match = None
        if flagged_msg.matches:
            first_match = flagged_msg.matches[0]
            if isinstance(first_match, SimilarityMatch):
                match_score = first_match.score
                matched_claim = first_match.matched_claim
                matched_source = first_match.matched_source
            elif isinstance(first_match, OpenAIModerationMatch):
                match_score = first_match.max_score
                matched_claim = ", ".join(first_match.flagged_categories)
                matched_source = ""
            elif isinstance(first_match, ConversationFlashpointMatch):
                match_score = first_match.confidence
                matched_claim = first_match.reasoning
                matched_source = ""

        try:
            request = await RequestService.create_from_message(
                db=session,
                request_id=request_id,
                content=flagged_msg.content,
                community_server_id=community_server_id,
                requested_by=str(user_id),
                platform_message_id=flagged_msg.message_id,
                platform_channel_id=flagged_msg.channel_id,
                platform_author_id=flagged_msg.author_id,
                platform_timestamp=flagged_msg.timestamp,
                similarity_score=match_score,
                dataset_name="bulk_scan",
                status="PENDING",
                priority="normal",
                reason=f"Flagged by bulk scan {scan_id}",
                request_metadata={
                    "scan_id": str(scan_id),
                    "matched_claim": matched_claim,
                    "matched_source": matched_source,
                    "match_score": match_score,
                    "generate_ai_notes": generate_ai_notes,
                },
            )

            created_ids.append(request.request_id)

            logger.debug(
                "Created note request from bulk scan",
                extra={
                    "request_id": request.request_id,
                    "message_id": msg_id,
                    "scan_id": str(scan_id),
                    "match_score": match_score,
                },
            )

            if generate_ai_notes and first_match and platform_id:
                try:
                    if isinstance(first_match, SimilarityMatch) and first_match.fact_check_item_id:
                        await event_publisher.publish_request_auto_created(
                            request_id=request.request_id,
                            platform_message_id=flagged_msg.message_id,
                            community_server_id=platform_id,
                            content=flagged_msg.content,
                            scan_type="similarity",
                            fact_check_item_id=str(first_match.fact_check_item_id)
                            if first_match.fact_check_item_id
                            else None,
                            similarity_score=first_match.score,
                            dataset_name=first_match.matched_source or "bulk_scan",
                        )
                    elif isinstance(first_match, OpenAIModerationMatch):
                        await event_publisher.publish_request_auto_created(
                            request_id=request.request_id,
                            platform_message_id=flagged_msg.message_id,
                            community_server_id=platform_id,
                            content=flagged_msg.content,
                            scan_type="openai_moderation",
                            moderation_metadata={
                                "categories": first_match.categories,
                                "scores": first_match.scores,
                                "flagged_categories": first_match.flagged_categories,
                            },
                        )
                    elif isinstance(first_match, ConversationFlashpointMatch):
                        await event_publisher.publish_request_auto_created(
                            request_id=request.request_id,
                            platform_message_id=flagged_msg.message_id,
                            community_server_id=platform_id,
                            content=flagged_msg.content,
                            scan_type="conversation_flashpoint",
                            metadata={
                                "confidence": first_match.confidence,
                                "reasoning": first_match.reasoning,
                                "context_messages": first_match.context_messages,
                            },
                        )
                    logger.info(
                        "Published REQUEST_AUTO_CREATED event for AI note generation",
                        extra={
                            "request_id": request.request_id,
                            "scan_type": first_match.scan_type,
                        },
                    )
                except Exception as pub_error:
                    logger.error(
                        "Failed to publish REQUEST_AUTO_CREATED event",
                        extra={
                            "request_id": request.request_id,
                            "error": str(pub_error),
                        },
                    )

        except Exception as e:
            logger.error(
                "Failed to create note request",
                extra={
                    "message_id": msg_id,
                    "scan_id": str(scan_id),
                    "error": str(e),
                },
            )
            continue

    await session.commit()

    logger.info(
        "Note requests created from bulk scan",
        extra={
            "scan_id": str(scan_id),
            "requested_count": len(message_ids),
            "created_count": len(created_ids),
            "user_id": str(user_id),
        },
    )

    return created_ids
