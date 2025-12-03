import logging
import secrets
import time
from datetime import UTC as UTC_TZ
from datetime import datetime
from typing import Any
from uuid import UUID

from nats.errors import Error as NATSError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.config import settings
from src.events.nats_client import nats_client
from src.events.schemas import (
    AuditLogCreatedEvent,
    BaseEvent,
    EventType,
    NoteCreatedEvent,
    NoteRatedEvent,
    NoteRequestCreatedEvent,
    NoteScoreUpdatedEvent,
    RequestAutoCreatedEvent,
    UserRegisteredEvent,
    VisionDescriptionRequestedEvent,
    WebhookReceivedEvent,
)
from src.monitoring.instance import InstanceMetadata
from src.monitoring.metrics import (
    nats_duplicate_events_total,
    nats_events_failed_total,
    nats_events_published_total,
    nats_publish_duration_seconds,
)

logger = logging.getLogger(__name__)


class EventPublisher:
    def __init__(self) -> None:
        self.nats = nats_client

    def _get_subject(self, event_type: EventType) -> str:
        event_name = event_type.value.replace(".", "_")
        return f"{settings.NATS_STREAM_NAME}.{event_name}"

    @retry(
        stop=stop_after_attempt(settings.NATS_PUBLISH_MAX_RETRIES),
        wait=wait_exponential(
            multiplier=1,
            min=settings.NATS_PUBLISH_RETRY_MIN_WAIT,
            max=settings.NATS_PUBLISH_RETRY_MAX_WAIT,
        ),
        retry=retry_if_exception_type((NATSError, TimeoutError)),
        reraise=True,
    )
    async def _publish_with_retries(
        self,
        subject: str,
        data: bytes,
        headers: dict[str, str],
        event: BaseEvent,
    ) -> str:
        """Internal method that handles the actual NATS publish with retries."""
        start_time = time.time()
        ack = await self.nats.publish(subject, data, headers=headers)
        duration = time.time() - start_time
        instance_id = InstanceMetadata.get_instance_id()

        nats_publish_duration_seconds.labels(
            event_type=event.event_type.value, instance_id=instance_id
        ).observe(duration)

        nats_events_published_total.labels(
            event_type=event.event_type.value, stream=ack.stream, instance_id=instance_id
        ).inc()

        if ack.duplicate:
            nats_duplicate_events_total.labels(
                event_type=event.event_type.value, stream=ack.stream, instance_id=instance_id
            ).inc()
            logger.warning(
                f"Duplicate event detected: {event.event_id} (stream: {ack.stream}, seq: {ack.seq})"
            )

        logger.info(
            f"Published event {event.event_id} of type {event.event_type.value} to subject {subject} "
            f"(stream: {ack.stream}, seq: {ack.seq}, duplicate: {ack.duplicate})"
        )
        return event.event_id

    async def publish_event(
        self,
        event: BaseEvent,
        headers: dict[str, str] | None = None,
    ) -> str:
        if not event.event_id:
            event = event.model_copy(update={"event_id": secrets.token_urlsafe(16)})

        subject = self._get_subject(event.event_type)
        data = event.model_dump_json().encode()

        default_headers = {
            "event-id": event.event_id,
            "event-type": event.event_type.value,
            "version": event.version,
            "Msg-Id": event.event_id,
        }

        correlation_id = headers.get("correlation_id") if headers else None
        if correlation_id:
            default_headers["X-Correlation-Id"] = correlation_id
        else:
            default_headers["X-Correlation-Id"] = event.event_id

        if headers:
            default_headers.update(headers)

        try:
            return await self._publish_with_retries(subject, data, default_headers, event)
        except Exception as e:
            # This except block only runs AFTER all retries are exhausted
            # Get the actual exception type name (e.g., "Error" for nats.errors.Error)
            error_type = e.__class__.__name__
            instance_id = InstanceMetadata.get_instance_id()
            nats_events_failed_total.labels(
                event_type=event.event_type.value, error_type=error_type, instance_id=instance_id
            ).inc()
            logger.error(
                f"Failed to publish event {event.event_id} of type {event.event_type.value}: {e}",
                extra={"event_id": event.event_id, "error_type": error_type},
            )
            raise

    async def publish_note_created(
        self,
        note_id: "UUID",
        author_id: str,
        platform_message_id: str | None,
        summary: str,
        classification: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        event = NoteCreatedEvent(
            event_id=secrets.token_urlsafe(16),
            note_id=note_id,
            author_id=author_id,
            platform_message_id=platform_message_id,
            summary=summary,
            classification=classification,  # type: ignore[arg-type]
            metadata=metadata or {},
        )
        return await self.publish_event(event)

    async def publish_note_rated(
        self,
        note_id: "UUID",
        rater_id: str,
        helpfulness_level: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        event = NoteRatedEvent(
            event_id=secrets.token_urlsafe(16),
            note_id=note_id,
            rater_id=rater_id,
            helpfulness_level=helpfulness_level,  # type: ignore[arg-type]
            metadata=metadata or {},
        )
        return await self.publish_event(event)

    async def publish_user_registered(
        self,
        user_id: "UUID",
        username: str,
        email: str | None,
        registration_source: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        event = UserRegisteredEvent(
            event_id=secrets.token_urlsafe(16),
            user_id=user_id,
            username=username,
            email=email,
            registration_source=registration_source,
            metadata=metadata or {},
        )
        return await self.publish_event(event)

    async def publish_webhook_received(
        self,
        webhook_id: str,
        community_server_id: str | None,
        channel_id: str | None,
        user_id: str,
        interaction_type: int,
        command_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        event = WebhookReceivedEvent(
            event_id=secrets.token_urlsafe(16),
            webhook_id=webhook_id,
            community_server_id=community_server_id,
            channel_id=channel_id,
            user_id=user_id,
            interaction_type=interaction_type,
            command_name=command_name,
            metadata=metadata or {},
        )
        return await self.publish_event(event)

    async def publish_note_score_updated(
        self,
        note_id: "UUID",
        score: float,
        confidence: str,
        algorithm: str,
        rating_count: int,
        tier: int,
        tier_name: str,
        original_message_id: str | None = None,
        channel_id: str | None = None,
        community_server_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        event = NoteScoreUpdatedEvent(
            event_id=secrets.token_urlsafe(16),
            note_id=note_id,
            score=score,
            confidence=confidence,  # type: ignore[arg-type]
            algorithm=algorithm,
            rating_count=rating_count,
            tier=tier,
            tier_name=tier_name,
            original_message_id=original_message_id,
            channel_id=channel_id,
            community_server_id=community_server_id,
            metadata=metadata or {},
        )
        return await self.publish_event(event)

    async def publish_note_request_created(
        self,
        request_id: str,
        platform_message_id: str | None,
        requested_by: str,
        status: str,
        priority: str,
        similarity_score: float | None = None,
        dataset_name: str | None = None,
        dataset_item_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        event = NoteRequestCreatedEvent(
            event_id=secrets.token_urlsafe(16),
            request_id=request_id,
            platform_message_id=platform_message_id,
            requested_by=requested_by,
            status=status,
            priority=priority,
            similarity_score=similarity_score,
            dataset_name=dataset_name,
            dataset_item_id=dataset_item_id,
            metadata=metadata or {},
        )
        return await self.publish_event(event)

    async def publish_request_auto_created(
        self,
        request_id: str,
        platform_message_id: str | None,
        fact_check_item_id: str,
        community_server_id: str,
        content: str,
        similarity_score: float,
        dataset_name: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        event = RequestAutoCreatedEvent(
            event_id=secrets.token_urlsafe(16),
            request_id=request_id,
            platform_message_id=platform_message_id,
            fact_check_item_id=fact_check_item_id,
            community_server_id=community_server_id,
            content=content,
            similarity_score=similarity_score,
            dataset_name=dataset_name,
            metadata=metadata or {},
        )
        return await self.publish_event(event)

    async def publish_vision_description_requested(
        self,
        message_archive_id: str,
        image_url: str,
        community_server_id: str,
        request_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        event = VisionDescriptionRequestedEvent(
            event_id=secrets.token_urlsafe(16),
            message_archive_id=message_archive_id,
            image_url=image_url,
            community_server_id=community_server_id,
            request_id=request_id,
            metadata=metadata or {},
        )
        return await self.publish_event(event)

    async def publish_audit_log(
        self,
        user_id: "UUID | None",
        action: str,
        resource: str,
        resource_id: str | None = None,
        details: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        created_at: Any = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        event = AuditLogCreatedEvent(
            event_id=secrets.token_urlsafe(16),
            user_id=user_id,
            action=action,
            resource=resource,
            resource_id=resource_id,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent,
            created_at=created_at if isinstance(created_at, datetime) else datetime.now(UTC_TZ),
            metadata=metadata or {},
        )
        return await self.publish_event(event)


event_publisher = EventPublisher()
