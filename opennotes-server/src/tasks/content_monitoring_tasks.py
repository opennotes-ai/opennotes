"""
TaskIQ tasks for content monitoring operations.

These tasks handle background processing of:
- AI note generation (LLM-powered fact-check notes)
- Vision description processing (image description via LLM)
- Audit log persistence (database writes)

Bulk scan batch processing and finalization have been migrated to DBOS workflows.
See src/dbos_workflows/content_scan_workflow.py for the durable execution replacement.

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
"""

import json
import logging
import time
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
from src.users import PLACEHOLDER_USER_ID

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
                        CommunityServer.platform_community_server_id == community_server_id
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
                    author_id=PLACEHOLDER_USER_ID,
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
