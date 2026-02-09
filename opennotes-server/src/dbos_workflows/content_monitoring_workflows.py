"""DBOS workflows for content monitoring tasks.

Replaces NATS->TaskIQ content monitoring tasks with direct DBOS execution.
Architecture: intra-server calls -> DBOS workflows/steps (no NATS event layer).

Workflows:
    ai_note_generation_workflow: Generate AI note for fact-check match or moderation flag
    vision_description_workflow: Generate image description via LLM vision API

Steps:
    persist_audit_log_step: Persist audit log entry to database (wrapped by _audit_log_wrapper_workflow)
"""

from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from dbos import DBOS
from opentelemetry import trace
from opentelemetry.trace import StatusCode
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.monitoring.instance import InstanceMetadata
from src.monitoring.metrics import (
    ai_note_generation_duration_seconds,
    ai_notes_generated_total,
)
from src.utils.async_compat import run_sync

logger = logging.getLogger(__name__)
_tracer = trace.get_tracer(__name__)

AI_NOTE_GENERATION_WORKFLOW_NAME = "ai_note_generation_workflow"
VISION_DESCRIPTION_WORKFLOW_NAME = "vision_description_workflow"
AUDIT_LOG_WORKFLOW_NAME = "_audit_log_wrapper_workflow"


def _retry_llm_call(func):
    return retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((TimeoutError, ConnectionError, OSError)),
        reraise=True,
    )(func)


@DBOS.step()
def generate_ai_note_step(
    community_server_id: str,
    request_id: str,
    content: str,
    scan_type: str,
    fact_check_item_id: str | None = None,
    similarity_score: float | None = None,
    moderation_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    async def _generate() -> dict[str, Any]:
        from sqlalchemy import select
        from sqlalchemy.ext.asyncio import async_sessionmaker

        from src.config import get_settings
        from src.fact_checking.models import FactCheckItem
        from src.llm_config.models import CommunityServer
        from src.llm_config.providers.base import LLMMessage
        from src.notes.models import Note
        from src.tasks.content_monitoring_tasks import (
            _build_fact_check_prompt,
            _build_general_explanation_prompt,
            _create_db_engine,
            _get_llm_service,
        )
        from src.users import PLACEHOLDER_USER_ID
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

            engine = _create_db_engine(settings.DATABASE_URL)
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
                            select(FactCheckItem).where(
                                FactCheckItem.id == UUID(fact_check_item_id)
                            )
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

                    @_retry_llm_call
                    async def _call_llm():
                        return await llm_service.complete(
                            db=session,
                            messages=messages,
                            community_server_id=community_server_uuid,
                            provider="openai",
                            model=settings.AI_NOTE_WRITER_MODEL,
                            max_tokens=500,
                            temperature=0.7,
                        )

                    response = await _call_llm()

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

    return run_sync(_generate())


@DBOS.workflow()
def ai_note_generation_workflow(
    community_server_id: str,
    request_id: str,
    content: str,
    scan_type: str,
    fact_check_item_id: str | None = None,
    similarity_score: float | None = None,
    moderation_metadata_json: str | None = None,
) -> dict[str, Any]:
    moderation_metadata = json.loads(moderation_metadata_json) if moderation_metadata_json else None

    return generate_ai_note_step(
        community_server_id=community_server_id,
        request_id=request_id,
        content=content,
        scan_type=scan_type,
        fact_check_item_id=fact_check_item_id,
        similarity_score=similarity_score,
        moderation_metadata=moderation_metadata,
    )


@DBOS.step()
def generate_vision_description_step(
    message_archive_id: str,
    image_url: str,
    community_server_id: str,
) -> dict[str, Any]:
    async def _generate() -> dict[str, Any]:
        from sqlalchemy.ext.asyncio import async_sessionmaker

        from src.config import get_settings
        from src.notes.message_archive_models import MessageArchive
        from src.services.vision_service import VisionService
        from src.tasks.content_monitoring_tasks import _create_db_engine, _get_llm_service

        archive_uuid = UUID(message_archive_id)

        with _tracer.start_as_current_span("content.vision_description") as span:
            span.set_attribute("task.message_archive_id", message_archive_id)
            span.set_attribute("task.community_server_id", community_server_id)
            span.set_attribute("task.component", "content_monitoring")

            settings = get_settings()
            engine = _create_db_engine(settings.DATABASE_URL)
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

                    @_retry_llm_call
                    async def _call_vision():
                        return await vision_service.describe_image(
                            db=session,
                            image_url=image_url,
                            community_server_id=community_server_id,
                            detail="auto",
                        )

                    description = await _call_vision()

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

    return run_sync(_generate())


@DBOS.workflow()
def vision_description_workflow(
    message_archive_id: str,
    image_url: str,
    community_server_id: str,
) -> dict[str, Any]:
    return generate_vision_description_step(
        message_archive_id=message_archive_id,
        image_url=image_url,
        community_server_id=community_server_id,
    )


@DBOS.step()
def persist_audit_log_step(
    user_id: str | None,
    action: str,
    resource: str,
    resource_id: str | None,
    details: str | None,
    ip_address: str | None,
    user_agent: str | None,
    created_at_iso: str | None = None,
) -> dict[str, Any]:
    async def _persist() -> dict[str, Any]:
        from sqlalchemy.ext.asyncio import async_sessionmaker

        from src.config import get_settings
        from src.tasks.content_monitoring_tasks import _create_db_engine
        from src.users.models import AuditLog

        with _tracer.start_as_current_span("content.audit_log") as span:
            span.set_attribute("task.action", action)
            span.set_attribute("task.resource", resource)
            span.set_attribute("task.component", "content_monitoring")
            if user_id:
                span.set_attribute("task.user_id", user_id)

            settings = get_settings()
            engine = _create_db_engine(settings.DATABASE_URL)
            async_session = async_sessionmaker(engine, expire_on_commit=False)

            try:
                async with async_session() as session:
                    audit_log = AuditLog(
                        user_id=UUID(user_id) if user_id else None,
                        action=action,
                        resource=resource,
                        resource_id=resource_id,
                        details=details,
                        ip_address=ip_address,
                        user_agent=user_agent,
                        created_at=datetime.fromisoformat(created_at_iso)
                        if created_at_iso
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

    return run_sync(_persist())


@DBOS.workflow()
def _audit_log_wrapper_workflow(
    user_id: str | None,
    action: str,
    resource: str,
    resource_id: str | None,
    details: str | None,
    ip_address: str | None,
    user_agent: str | None,
    created_at_iso: str | None,
) -> dict[str, Any]:
    return persist_audit_log_step(
        user_id=user_id,
        action=action,
        resource=resource,
        resource_id=resource_id,
        details=details,
        ip_address=ip_address,
        user_agent=user_agent,
        created_at_iso=created_at_iso,
    )


def start_ai_note_workflow(
    community_server_id: str,
    request_id: str,
    content: str,
    scan_type: str,
    fact_check_item_id: str | None = None,
    similarity_score: float | None = None,
    moderation_metadata: dict[str, Any] | None = None,
) -> None:
    from src.dbos_workflows.config import get_dbos_client

    moderation_metadata_json = json.dumps(moderation_metadata) if moderation_metadata else None

    client = get_dbos_client()
    client.start_workflow(
        ai_note_generation_workflow,
        community_server_id,
        request_id,
        content,
        scan_type,
        fact_check_item_id,
        similarity_score,
        moderation_metadata_json,
    )

    logger.info(
        "Enqueued AI note generation workflow",
        extra={
            "request_id": request_id,
            "scan_type": scan_type,
            "community_server_id": community_server_id,
        },
    )


def call_persist_audit_log(
    user_id: str | None,
    action: str,
    resource: str,
    resource_id: str | None = None,
    details: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    created_at_iso: str | None = None,
) -> None:
    from src.dbos_workflows.config import get_dbos_client

    client = get_dbos_client()
    client.start_workflow(
        _audit_log_wrapper_workflow,
        user_id,
        action,
        resource,
        resource_id,
        details,
        ip_address,
        user_agent,
        created_at_iso,
    )
