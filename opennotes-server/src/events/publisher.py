import logging
import secrets
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC as UTC_TZ
from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from src.events.nats_client import NATSClientManager

from nats.errors import Error as NATSError
from opentelemetry import propagate, trace
from opentelemetry.semconv._incubating.attributes.messaging_attributes import (
    MESSAGING_OPERATION_TYPE,
)
from opentelemetry.semconv.trace import SpanAttributes
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
    def __init__(self, nats: "NATSClientManager | None" = None) -> None:
        """Initialize EventPublisher with optional NATS client.

        Args:
            nats: Optional NATSClientManager instance. If not provided, uses the
                  global nats_client singleton. Worker tasks should provide their
                  own connected NATSClientManager via create_worker_event_publisher().
        """
        from src.events.nats_client import NATSClientManager  # noqa: PLC0415

        self.nats: NATSClientManager = nats if nats is not None else nats_client
        self._tracer = trace.get_tracer(__name__)

    def _get_subject(self, event_type: EventType) -> str:
        event_name = event_type.value.replace(".", "_")
        return f"{settings.NATS_STREAM_NAME}.{event_name}"

    def _inject_trace_context(self, headers: dict[str, str]) -> dict[str, str]:
        """Inject W3C Trace Context and Baggage into NATS message headers."""
        carrier: dict[str, str] = {}
        propagate.inject(carrier)

        for key in ("traceparent", "tracestate", "baggage"):
            if key in carrier:
                headers[key] = carrier[key]

        return headers

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

        with self._tracer.start_as_current_span(
            f"nats.publish.{event.event_type.value}",
            kind=trace.SpanKind.PRODUCER,
        ) as span:
            # Inject trace context INSIDE the span so traceparent includes producer span ID
            default_headers = self._inject_trace_context(default_headers)

            span.set_attribute(SpanAttributes.MESSAGING_SYSTEM, "nats")
            span.set_attribute(SpanAttributes.MESSAGING_DESTINATION_NAME, subject)
            span.set_attribute(SpanAttributes.MESSAGING_MESSAGE_ID, event.event_id)
            span.set_attribute(MESSAGING_OPERATION_TYPE, "send")

            try:
                result = await self._publish_with_retries(subject, data, default_headers, event)
                span.set_status(trace.StatusCode.OK)
                return result
            except Exception as e:
                error_type = e.__class__.__name__
                instance_id = InstanceMetadata.get_instance_id()
                nats_events_failed_total.labels(
                    event_type=event.event_type.value,
                    error_type=error_type,
                    instance_id=instance_id,
                ).inc()
                logger.error(
                    f"Failed to publish event {event.event_id} of type {event.event_type.value}: {e}",
                    extra={"event_id": event.event_id, "error_type": error_type},
                )
                span.set_status(trace.StatusCode.ERROR, str(e))
                span.record_exception(e)
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
        community_server_id: str,
        content: str,
        scan_type: str,
        fact_check_item_id: str | None = None,
        similarity_score: float | None = None,
        dataset_name: str | None = None,
        moderation_metadata: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        event = RequestAutoCreatedEvent(
            event_id=secrets.token_urlsafe(16),
            request_id=request_id,
            platform_message_id=platform_message_id,
            scan_type=scan_type,  # type: ignore[arg-type]
            fact_check_item_id=fact_check_item_id,
            community_server_id=community_server_id,
            content=content,
            similarity_score=similarity_score,
            dataset_name=dataset_name,
            moderation_metadata=moderation_metadata,
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


@asynccontextmanager
async def create_worker_event_publisher() -> AsyncGenerator[EventPublisher, None]:
    """Create an EventPublisher with its own NATS connection for worker tasks.

    This context manager creates a dedicated NATS client connection for use in
    TaskIQ worker tasks. The global event_publisher singleton uses the nats_client
    singleton which is connected during API server startup, but worker processes
    don't run the API server's lifespan and therefore have an unconnected client.

    Usage:
        async with create_worker_event_publisher() as publisher:
            await publisher.publish_event(my_event)

    The NATS connection is automatically closed when the context manager exits.
    """
    from src.events.nats_client import NATSClientManager  # noqa: PLC0415

    client = NATSClientManager()
    await client.connect()
    try:
        yield EventPublisher(nats=client)
    finally:
        await client.disconnect()
