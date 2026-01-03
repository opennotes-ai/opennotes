"""
TaskIQ tasks for content monitoring operations.

These tasks handle background processing of:
- Bulk scan batch processing (message similarity analysis)
- Bulk scan finalization (results aggregation and publishing)
- AI note generation (LLM-powered fact-check notes)
- Vision description processing (image description via LLM)
- Audit log persistence (database writes)

Tasks are designed to be self-contained, creating their own database and Redis
connections to work reliably in distributed worker environments.

OpenTelemetry Integration:
- Tasks are instrumented with spans for tracing
- Exceptions are recorded on spans with proper error status
- Trace context is propagated via TaskIQ's OpenTelemetryMiddleware

Hybrid Pattern (NATS → TaskIQ):
- NATS events trigger these tasks for cross-service decoupling
- TaskIQ provides retries, result storage, and tracing
- See ADR-004: NATS vs TaskIQ Usage Boundaries

Architecture Overview:

    Discord Bot          API Server              TaskIQ Worker
        │                    │                        │
        │  BULK_SCAN_BATCH   │                        │
        │ ─────────────────> │                        │
        │                    │  process_bulk_scan_    │
        │                    │  batch_task.kiq()      │
        │                    │ ─────────────────────> │
        │                    │                        │ (process messages)
        │                    │                        │
        │ REQUEST_AUTO_      │                        │
        │ CREATED            │                        │
        │ ─────────────────> │                        │
        │                    │  generate_ai_note_     │
        │                    │  task.kiq()            │
        │                    │ ─────────────────────> │
        │                    │                        │ (generate note)

Example - NATS Handler dispatching to TaskIQ:

    async def _handle_message_batch(self, event: BulkScanMessageBatchEvent) -> None:
        from src.tasks.content_monitoring_tasks import process_bulk_scan_batch_task

        # NATS handler dispatches to TaskIQ - lightweight, fast ack
        await process_bulk_scan_batch_task.kiq(
            scan_id=str(event.scan_id),
            community_server_id=str(event.community_server_id),
            batch_number=event.batch_number,
            messages=[msg.model_dump() for msg in event.messages],
            db_url=settings.DATABASE_URL,
            redis_url=settings.REDIS_URL,
        )

Benefits:
- NATS ack happens quickly (after dispatch, not after processing)
- TaskIQ handles retries, result storage, and distributed tracing
- Workers can be scaled independently from API servers
- Task progress and results are observable via Redis result backend
"""

import json
import logging
import time
import uuid as uuid_module
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from opentelemetry import trace
from opentelemetry.trace import StatusCode
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.monitoring.instance import InstanceMetadata
from src.monitoring.metrics import (
    ai_note_generation_duration_seconds,
    ai_notes_generated_total,
)
from src.tasks.broker import register_task

if TYPE_CHECKING:
    from src.fact_checking.models import FactCheckItem

logger = logging.getLogger(__name__)
_tracer = trace.get_tracer(__name__)


def _create_db_engine(db_url: str) -> Any:
    """Create async database engine with pool settings."""
    from src.config import get_settings

    settings = get_settings()
    return create_async_engine(
        db_url,
        pool_pre_ping=True,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_POOL_MAX_OVERFLOW,
        pool_timeout=settings.DB_POOL_TIMEOUT,
        pool_recycle=settings.DB_POOL_RECYCLE,
    )


def _get_llm_service() -> Any:
    """Create LLMService with required dependencies."""
    from src.config import get_settings
    from src.llm_config.encryption import EncryptionService
    from src.llm_config.manager import LLMClientManager
    from src.llm_config.service import LLMService

    settings = get_settings()
    llm_client_manager = LLMClientManager(
        encryption_service=EncryptionService(settings.ENCRYPTION_MASTER_KEY)
    )
    return LLMService(client_manager=llm_client_manager)


async def _get_platform_id(session: Any, community_server_id: UUID) -> str | None:
    """Get platform ID from community server UUID."""
    from src.llm_config.models import CommunityServer

    result = await session.execute(
        select(CommunityServer.platform_id).where(CommunityServer.id == community_server_id)
    )
    return result.scalar_one_or_none()


@register_task(task_name="content:batch_scan", component="content_monitoring", task_type="batch")
async def process_bulk_scan_batch_task(
    scan_id: str,
    community_server_id: str,
    batch_number: int,
    messages: list[dict[str, Any]],
    db_url: str,
    redis_url: str,
) -> dict[str, Any]:
    """
    TaskIQ task to process bulk scan message batch.

    This task:
    1. Processes messages through similarity analysis
    2. Tracks flagged messages in Redis
    3. Updates processed count
    4. Triggers finalization if all batches complete

    Args:
        scan_id: UUID string of the scan
        community_server_id: UUID string of the community server
        batch_number: Batch number being processed
        messages: List of message dictionaries
        db_url: Database connection URL
        redis_url: Redis connection URL

    Returns:
        dict with status and messages_processed
    """
    from src.bulk_content_scan.schemas import BulkScanMessage, FlaggedMessage
    from src.bulk_content_scan.service import BulkContentScanService
    from src.cache.redis_client import RedisClient
    from src.fact_checking.embedding_service import EmbeddingService

    with _tracer.start_as_current_span("content.batch_scan") as span:
        span.set_attribute("task.scan_id", scan_id)
        span.set_attribute("task.community_server_id", community_server_id)
        span.set_attribute("task.batch_number", batch_number)
        span.set_attribute("task.component", "content_monitoring")
        span.set_attribute("task.message_count", len(messages))

        scan_uuid = UUID(scan_id)
        community_uuid = UUID(community_server_id)

        engine = _create_db_engine(db_url)
        async_session = async_sessionmaker(engine, expire_on_commit=False)
        redis_client = RedisClient()

        try:
            await redis_client.connect(redis_url)

            async with async_session() as session:
                platform_id = await _get_platform_id(session, community_uuid)
                if not platform_id:
                    error_msg = f"Platform ID not found for community server {community_server_id}"
                    span.set_status(StatusCode.ERROR, error_msg)
                    logger.error(error_msg, extra={"scan_id": scan_id})
                    return {"status": "error", "error": error_msg}

                llm_service = _get_llm_service()
                embedding_service = EmbeddingService(llm_service)
                service = BulkContentScanService(
                    session=session,
                    embedding_service=embedding_service,
                    redis_client=redis_client.client,  # type: ignore[arg-type]
                    llm_service=llm_service,
                )

                typed_messages = [BulkScanMessage.model_validate(msg) for msg in messages]
                flagged: list[FlaggedMessage] = []

                for msg in typed_messages:
                    try:
                        msg_flagged = await service.process_messages(
                            scan_id=scan_uuid,
                            messages=[msg],
                            community_server_platform_id=platform_id,
                        )
                        flagged.extend(msg_flagged)
                    except Exception as e:
                        logger.warning(
                            "Error processing message in batch",
                            extra={
                                "scan_id": scan_id,
                                "message_id": msg.message_id,
                                "error": str(e),
                            },
                        )
                        await service.record_error(
                            scan_id=scan_uuid,
                            error_type=type(e).__name__,
                            error_message=str(e),
                            message_id=msg.message_id,
                            batch_number=batch_number,
                        )

                await service.increment_processed_count(scan_uuid, len(typed_messages))
                processed_count = await service.get_processed_count(scan_uuid)

                for msg in flagged:
                    await service.append_flagged_result(scan_uuid, msg)

                logger.info(
                    "Batch processed",
                    extra={
                        "scan_id": scan_id,
                        "batch_number": batch_number,
                        "messages_processed": len(typed_messages),
                        "messages_flagged": len(flagged),
                        "total_processed": processed_count,
                    },
                )

                transmitted, transmitted_messages = await service.get_all_batches_transmitted(
                    scan_uuid
                )
                if (
                    transmitted
                    and transmitted_messages is not None
                    and processed_count >= transmitted_messages
                ):
                    should_dispatch = await service.try_set_finalize_dispatched(scan_uuid)
                    if should_dispatch:
                        logger.info(
                            "Batch handler dispatching finalization",
                            extra={
                                "scan_id": scan_id,
                                "processed_count": processed_count,
                                "messages_scanned": transmitted_messages,
                            },
                        )
                        await finalize_bulk_scan_task.kiq(
                            scan_id=scan_id,
                            community_server_id=community_server_id,
                            messages_scanned=transmitted_messages,
                            db_url=db_url,
                            redis_url=redis_url,
                        )
                    else:
                        logger.info(
                            "Batch handler skipping finalization (already dispatched)",
                            extra={
                                "scan_id": scan_id,
                                "processed_count": processed_count,
                                "messages_scanned": transmitted_messages,
                            },
                        )

            span.set_attribute("task.messages_processed", len(typed_messages))
            span.set_attribute("task.messages_flagged", len(flagged))

            return {
                "status": "completed",
                "messages_processed": len(typed_messages),
                "messages_flagged": len(flagged),
            }

        except Exception as e:
            error_msg = str(e)
            span.record_exception(e)
            span.set_status(StatusCode.ERROR, error_msg)
            logger.error(
                "Failed to process bulk scan batch",
                extra={"scan_id": scan_id, "error": error_msg},
                exc_info=True,
            )
            raise
        finally:
            await redis_client.disconnect()
            await engine.dispose()


@register_task(
    task_name="content:finalize_scan", component="content_monitoring", task_type="finalize"
)
async def finalize_bulk_scan_task(
    scan_id: str,
    community_server_id: str,
    messages_scanned: int,
    db_url: str,
    redis_url: str,
) -> dict[str, Any]:
    """
    TaskIQ task to finalize bulk scan and publish results.

    This task:
    1. Retrieves flagged results from Redis
    2. Aggregates error summary
    3. Marks scan as complete in database
    4. Publishes results event

    Args:
        scan_id: UUID string of the scan
        community_server_id: UUID string of the community server
        messages_scanned: Total messages scanned
        db_url: Database connection URL
        redis_url: Redis connection URL

    Returns:
        dict with status and results summary
    """
    from src.bulk_content_scan.nats_handler import BulkScanResultsPublisher
    from src.bulk_content_scan.schemas import BulkScanStatus
    from src.bulk_content_scan.service import BulkContentScanService
    from src.cache.redis_client import RedisClient
    from src.events.publisher import event_publisher
    from src.events.schemas import (
        BulkScanProcessingFinishedEvent,
        ScanErrorInfo,
        ScanErrorSummary,
    )
    from src.fact_checking.embedding_service import EmbeddingService

    with _tracer.start_as_current_span("content.finalize_scan") as span:
        span.set_attribute("task.scan_id", scan_id)
        span.set_attribute("task.community_server_id", community_server_id)
        span.set_attribute("task.messages_scanned", messages_scanned)
        span.set_attribute("task.component", "content_monitoring")

        scan_uuid = UUID(scan_id)
        community_uuid = UUID(community_server_id)

        engine = _create_db_engine(db_url)
        async_session = async_sessionmaker(engine, expire_on_commit=False)
        redis_client = RedisClient()

        try:
            await redis_client.connect(redis_url)

            async with async_session() as session:
                llm_service = _get_llm_service()
                embedding_service = EmbeddingService(llm_service)
                service = BulkContentScanService(
                    session=session,
                    embedding_service=embedding_service,
                    redis_client=redis_client.client,  # type: ignore[arg-type]
                    llm_service=llm_service,
                )

                flagged = await service.get_flagged_results(scan_uuid)
                error_summary_data = await service.get_error_summary(scan_uuid)
                processed_count = await service.get_processed_count(scan_uuid)

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
                            "scan_id": scan_id,
                            "messages_scanned": messages_scanned,
                            "total_errors": total_errors,
                        },
                    )

                await service.complete_scan(
                    scan_id=scan_uuid,
                    messages_scanned=messages_scanned,
                    messages_flagged=len(flagged),
                    status=status,
                )

                publisher = BulkScanResultsPublisher(redis_client.client)
                await publisher.publish(
                    scan_id=scan_uuid,
                    messages_scanned=messages_scanned,
                    messages_flagged=len(flagged),
                    flagged_messages=flagged,
                    error_summary=error_summary,
                )

                processing_finished_event = BulkScanProcessingFinishedEvent(
                    event_id=f"evt_{uuid_module.uuid4().hex[:12]}",
                    scan_id=scan_uuid,
                    community_server_id=community_uuid,
                    messages_scanned=messages_scanned,
                    messages_flagged=len(flagged),
                )
                await event_publisher.publish_event(processing_finished_event)

                logger.info(
                    "Scan finalized",
                    extra={
                        "scan_id": scan_id,
                        "messages_scanned": messages_scanned,
                        "messages_flagged": len(flagged),
                        "status": status.value,
                        "total_errors": total_errors,
                    },
                )

            span.set_attribute("task.messages_flagged", len(flagged))
            span.set_attribute("task.status", status.value)

            return {
                "status": "completed",
                "messages_scanned": messages_scanned,
                "messages_flagged": len(flagged),
                "scan_status": status.value,
            }

        except Exception as e:
            error_msg = str(e)
            span.record_exception(e)
            span.set_status(StatusCode.ERROR, error_msg)
            logger.error(
                "Failed to finalize bulk scan",
                extra={"scan_id": scan_id, "error": error_msg},
                exc_info=True,
            )
            raise
        finally:
            await redis_client.disconnect()
            await engine.dispose()


@register_task(task_name="content:ai_note", component="content_monitoring", task_type="generation")
async def generate_ai_note_task(
    community_server_id: str,
    request_id: str,
    content: str,
    scan_type: str,
    db_url: str,
    fact_check_item_id: str | None = None,
    similarity_score: float | None = None,
    moderation_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    TaskIQ task to generate AI note for a fact-check match or moderation flag.

    This task:
    1. Checks rate limits
    2. For similarity scans: retrieves fact-check item and generates note with context
    3. For moderation scans: generates general explanation note
    4. Persists note to database

    Rate Limit Placement Decision:
        Rate limiting is checked inside this task rather than before dispatch.
        This is intentional for several reasons:

        1. The check runs BEFORE database connection is established, so no DB
           resources are wasted when rate limited.

        2. Centralizes rate limit logic with the task it protects, making the
           code easier to maintain.

        3. Keeps the NATS event handler thin ("lightweight, fast ack" pattern).

        4. Worker slot overhead is minimal compared to actual LLM/DB work, and
           rate limiting is typically rare (protection against abuse, not
           regular flow control).

    Args:
        community_server_id: Platform ID of the community server
        request_id: Request ID to attach note to
        content: Original message content
        scan_type: Type of scan ("similarity" or "openai_moderation")
        db_url: Database connection URL
        fact_check_item_id: UUID string of matched fact-check item (for similarity scans)
        similarity_score: Similarity score of the match (for similarity scans)
        moderation_metadata: OpenAI moderation results (for moderation scans), containing
            categories, scores, and flagged_categories

    Returns:
        dict with status and note_id if created
    """
    from src.config import get_settings
    from src.fact_checking.models import FactCheckItem
    from src.llm_config.models import CommunityServer
    from src.llm_config.providers.base import LLMMessage
    from src.notes.models import Note
    from src.webhooks.rate_limit import rate_limiter

    start_time = time.time()
    instance_id = InstanceMetadata.get_instance_id()

    with _tracer.start_as_current_span("content.ai_note") as span:
        span.set_attribute("task.community_server_id", community_server_id)
        span.set_attribute("task.request_id", request_id)
        span.set_attribute("task.scan_type", scan_type)
        if fact_check_item_id:
            span.set_attribute("task.fact_check_item_id", fact_check_item_id)
        if similarity_score is not None:
            span.set_attribute("task.similarity_score", similarity_score)
        if moderation_metadata:
            span.set_attribute("task.has_moderation_metadata", True)
        span.set_attribute("task.component", "content_monitoring")

        settings = get_settings()

        if not settings.AI_NOTE_WRITING_ENABLED:
            logger.info("AI note writing disabled globally")
            return {"status": "disabled"}

        rate_limit_key = f"ai_note_writer:{community_server_id}"
        allowed, retry_after = await rate_limiter.check_rate_limit(
            community_server_id=rate_limit_key
        )
        if not allowed:
            logger.warning(
                f"Rate limit exceeded for AI note writing: {community_server_id}",
                extra={"retry_after": retry_after},
            )
            span.set_attribute("task.rate_limited", True)
            return {"status": "rate_limited", "retry_after": retry_after}

        engine = _create_db_engine(db_url)
        async_session = async_sessionmaker(engine, expire_on_commit=False)

        try:
            async with async_session() as session:
                result = await session.execute(
                    select(CommunityServer.id).where(
                        CommunityServer.platform_id == community_server_id
                    )
                )
                community_server_uuid = result.scalar_one_or_none()

                if not community_server_uuid:
                    error_msg = f"Community server not found: {community_server_id}"
                    span.set_status(StatusCode.ERROR, error_msg)
                    return {"status": "error", "error": error_msg}

                llm_service = _get_llm_service()
                fact_check_item: FactCheckItem | None = None
                dataset_name = "bulk_scan"

                if scan_type == "similarity" and fact_check_item_id:
                    result = await session.execute(
                        select(FactCheckItem).where(FactCheckItem.id == UUID(fact_check_item_id))
                    )
                    fact_check_item = result.scalar_one_or_none()

                    if not fact_check_item:
                        error_msg = f"Fact-check item not found: {fact_check_item_id}"
                        span.set_status(StatusCode.ERROR, error_msg)
                        return {"status": "error", "error": error_msg}

                    dataset_name = fact_check_item.dataset_name or "bulk_scan"
                    prompt = _build_fact_check_prompt(
                        content, fact_check_item, similarity_score or 0.0
                    )
                else:
                    prompt = _build_general_explanation_prompt(content, moderation_metadata)

                messages = [
                    LLMMessage(role="system", content=settings.AI_NOTE_WRITER_SYSTEM_PROMPT),
                    LLMMessage(role="user", content=prompt),
                ]

                response = await llm_service.complete(
                    db=session,
                    messages=messages,
                    community_server_id=community_server_uuid,
                    provider="openai",
                    model=settings.AI_NOTE_WRITER_MODEL,
                    max_tokens=500,
                    temperature=0.7,
                )

                note = Note(
                    request_id=request_id,
                    author_participant_id="ai-note-writer",
                    summary=response.content,
                    classification="NOT_MISLEADING",
                    status="NEEDS_MORE_RATINGS",
                    community_server_id=community_server_uuid,
                    ai_generated=True,
                    ai_provider=settings.AI_NOTE_WRITER_MODEL.split("/")[0]
                    if "/" in settings.AI_NOTE_WRITER_MODEL
                    else "openai",
                )

                session.add(note)
                await session.commit()
                await session.refresh(note)

                duration = time.time() - start_time
                ai_note_generation_duration_seconds.labels(
                    community_server_id=community_server_id,
                    instance_id=instance_id,
                ).observe(duration)

                ai_notes_generated_total.labels(
                    community_server_id=community_server_id,
                    dataset_name=dataset_name,
                    instance_id=instance_id,
                ).inc()

                logger.info(
                    "Generated AI note",
                    extra={
                        "note_id": str(note.id),
                        "request_id": request_id,
                        "scan_type": scan_type,
                        "fact_check_item_id": fact_check_item_id,
                        "duration_seconds": duration,
                    },
                )

                span.set_attribute("task.note_id", str(note.id))
                span.set_attribute("task.duration_seconds", duration)
                return {"status": "completed", "note_id": str(note.id)}

        except Exception as e:
            error_msg = str(e)
            span.record_exception(e)
            span.set_status(StatusCode.ERROR, error_msg)
            logger.error(
                "Failed to generate AI note",
                extra={
                    "request_id": request_id,
                    "scan_type": scan_type,
                    "fact_check_item_id": fact_check_item_id,
                    "error": error_msg,
                },
                exc_info=True,
            )
            raise
        finally:
            await engine.dispose()


def _build_fact_check_prompt(
    original_message: str,
    fact_check_item: "FactCheckItem",
    similarity_score: float,
) -> str:
    """Build prompt for fact-check note generation."""
    return f"""Original Message:
{original_message}

Fact-Check Information:
Title: {fact_check_item.title}
Rating: {fact_check_item.rating}
Summary: {fact_check_item.summary}
Content: {fact_check_item.content}
Source: {fact_check_item.source_url}

Match Confidence: {similarity_score:.2%}

Please write a concise, informative community note that:
1. Addresses the claim in the original message
2. Provides context from the fact-check information
3. Maintains a neutral, factual tone
4. Is clear and easy to understand
5. Is no more than 280 characters if possible

Community Note:"""


def _build_general_explanation_prompt(
    original_message: str,
    moderation_metadata: dict[str, Any] | None = None,
) -> str:
    """Build prompt for general explanation note generation.

    Args:
        original_message: Original message content
        moderation_metadata: Optional OpenAI moderation results containing:
            - categories: dict of category name to bool (whether flagged)
            - scores: dict of category name to float (confidence score 0-1)
            - flagged_categories: list of category names that were flagged

    Returns:
        Formatted prompt for LLM
    """
    prompt_parts = [f"Original Message:\n{original_message}"]

    if moderation_metadata:
        moderation_context = "\nContent Moderation Analysis:"
        flagged_categories = moderation_metadata.get("flagged_categories", [])
        scores = moderation_metadata.get("scores", {})

        if flagged_categories:
            moderation_context += f"\nFlagged Categories: {', '.join(flagged_categories)}"
            relevant_scores = {
                cat: f"{score:.2%}" for cat, score in scores.items() if cat in flagged_categories
            }
            if relevant_scores:
                moderation_context += f"\nConfidence Scores: {relevant_scores}"

        prompt_parts.append(moderation_context)

    prompt_parts.append("""
Please analyze this content and write a concise, informative community note that:
1. Explains the message content
2. Provides helpful context and clarification
3. Addresses any potential misunderstandings
4. Maintains a neutral, factual tone
5. Is clear and easy to understand
6. Is no more than 280 characters if possible

Focus on helping readers understand what the content is about, what context might be important, and any relevant information that would be helpful to know.

Community Note:""")

    return "\n".join(prompt_parts)


@register_task(
    task_name="content:vision_description", component="content_monitoring", task_type="vision"
)
async def process_vision_description_task(
    message_archive_id: str,
    image_url: str,
    community_server_id: str,
    db_url: str,
) -> dict[str, Any]:
    """
    TaskIQ task to generate image description using vision API.

    This task:
    1. Checks if image already has description (idempotency)
    2. Calls vision service to describe image
    3. Updates message archive with description

    Args:
        message_archive_id: UUID string of message archive
        image_url: URL of image to describe
        community_server_id: Platform ID for LLM credentials
        db_url: Database connection URL

    Returns:
        dict with status and description_length if generated
    """
    from src.notes.message_archive_models import MessageArchive
    from src.services.vision_service import VisionService

    with _tracer.start_as_current_span("content.vision_description") as span:
        span.set_attribute("task.message_archive_id", message_archive_id)
        span.set_attribute("task.community_server_id", community_server_id)
        span.set_attribute("task.component", "content_monitoring")

        archive_uuid = UUID(message_archive_id)

        engine = _create_db_engine(db_url)
        async_session = async_sessionmaker(engine, expire_on_commit=False)

        try:
            async with async_session() as session:
                message_archive = await session.get(MessageArchive, archive_uuid)

                if not message_archive:
                    logger.warning(
                        f"Message archive {message_archive_id} not found",
                        extra={"message_archive_id": message_archive_id},
                    )
                    span.set_attribute("task.not_found", True)
                    return {"status": "not_found"}

                if message_archive.image_description:
                    logger.debug(
                        f"Message archive {message_archive_id} already has description",
                        extra={"message_archive_id": message_archive_id},
                    )
                    span.set_attribute("task.already_processed", True)
                    return {"status": "already_processed"}

                llm_service = _get_llm_service()
                vision_service = VisionService(llm_service=llm_service)

                description = await vision_service.describe_image(
                    db=session,
                    image_url=image_url,
                    community_server_id=community_server_id,
                    detail="auto",
                )

                message_archive.image_description = description
                await session.commit()

                logger.info(
                    "Generated vision description",
                    extra={
                        "message_archive_id": message_archive_id,
                        "description_length": len(description),
                    },
                )

                span.set_attribute("task.description_length", len(description))
                return {"status": "completed", "description_length": len(description)}

        except Exception as e:
            error_msg = str(e)
            span.record_exception(e)
            span.set_status(StatusCode.ERROR, error_msg)
            logger.error(
                "Failed to generate vision description",
                extra={"message_archive_id": message_archive_id, "error": error_msg},
                exc_info=True,
            )
            raise
        finally:
            await engine.dispose()


@register_task(task_name="content:audit_log", component="content_monitoring", task_type="audit")
async def persist_audit_log_task(
    user_id: str | None,
    community_server_id: str | None,
    action: str,
    resource: str,
    resource_id: str | None,
    details: dict[str, Any] | None,
    ip_address: str | None,
    user_agent: str | None,
    db_url: str,
    created_at: str | None = None,
) -> dict[str, Any]:
    """
    TaskIQ task to persist audit log entry to database.

    This task:
    1. Creates AuditLog record
    2. Persists to database with retry support

    Args:
        user_id: UUID string of user (or None)
        community_server_id: UUID string of community server (or None)
        action: Action performed
        resource: Resource affected
        resource_id: Resource ID if applicable
        details: Additional details dict
        ip_address: Client IP address
        user_agent: Client user agent
        db_url: Database connection URL
        created_at: ISO timestamp when action occurred

    Returns:
        dict with status and audit_log_id
    """
    from src.users.models import AuditLog

    with _tracer.start_as_current_span("content.audit_log") as span:
        span.set_attribute("task.action", action)
        span.set_attribute("task.resource", resource)
        span.set_attribute("task.component", "content_monitoring")
        if user_id:
            span.set_attribute("task.user_id", user_id)

        engine = _create_db_engine(db_url)
        async_session = async_sessionmaker(engine, expire_on_commit=False)

        try:
            async with async_session() as session:
                audit_log = AuditLog(
                    user_id=UUID(user_id) if user_id else None,
                    action=action,
                    resource=resource,
                    resource_id=resource_id,
                    details=json.dumps(details) if details else None,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    created_at=datetime.fromisoformat(created_at)
                    if created_at
                    else datetime.now(UTC),
                )

                session.add(audit_log)
                await session.commit()
                await session.refresh(audit_log)

                logger.debug(
                    "Persisted audit log",
                    extra={
                        "audit_log_id": str(audit_log.id),
                        "action": action,
                        "resource": resource,
                    },
                )

                span.set_attribute("task.audit_log_id", str(audit_log.id))
                return {"status": "completed", "audit_log_id": str(audit_log.id)}

        except Exception as e:
            error_msg = str(e)
            span.record_exception(e)
            span.set_status(StatusCode.ERROR, error_msg)
            logger.error(
                "Failed to persist audit log",
                extra={"action": action, "resource": resource, "error": error_msg},
                exc_info=True,
            )
            raise
        finally:
            await engine.dispose()
