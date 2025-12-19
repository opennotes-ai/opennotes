import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from nats.aio.msg import Msg

from src.config import settings
from src.events.nats_client import Subscription, nats_client
from src.events.schemas import (
    AuditLogCreatedEvent,
    BulkScanCompletedEvent,
    BulkScanMessageBatchEvent,
    EventType,
    NoteCreatedEvent,
    NoteRatedEvent,
    NoteScoreUpdatedEvent,
    RequestAutoCreatedEvent,
    UserRegisteredEvent,
    VisionDescriptionRequestedEvent,
    WebhookReceivedEvent,
)

logger = logging.getLogger(__name__)


EventHandler = Callable[[Any], Awaitable[None]]


class EventSubscriber:
    def __init__(self) -> None:
        self.nats = nats_client
        self.handlers: dict[EventType, list[EventHandler]] = {
            EventType.NOTE_CREATED: [],
            EventType.NOTE_RATED: [],
            EventType.NOTE_SCORE_UPDATED: [],
            EventType.REQUEST_AUTO_CREATED: [],
            EventType.USER_REGISTERED: [],
            EventType.VISION_DESCRIPTION_REQUESTED: [],
            EventType.WEBHOOK_RECEIVED: [],
            EventType.AUDIT_LOG_CREATED: [],
            EventType.BULK_SCAN_MESSAGE_BATCH: [],
            EventType.BULK_SCAN_COMPLETED: [],
        }
        self.subscriptions: list[Subscription] = []

    def register_handler(
        self,
        event_type: EventType,
        handler: EventHandler,
    ) -> None:
        self.handlers[event_type].append(handler)
        logger.info(f"Registered handler for event type: {event_type.value}")

    def _get_subject(self, event_type: EventType) -> str:
        event_name = event_type.value.replace(".", "_")
        return f"{settings.NATS_STREAM_NAME}.{event_name}"

    def _get_event_class(self, event_type: EventType) -> type:
        mapping = {
            EventType.NOTE_CREATED: NoteCreatedEvent,
            EventType.NOTE_RATED: NoteRatedEvent,
            EventType.NOTE_SCORE_UPDATED: NoteScoreUpdatedEvent,
            EventType.REQUEST_AUTO_CREATED: RequestAutoCreatedEvent,
            EventType.USER_REGISTERED: UserRegisteredEvent,
            EventType.VISION_DESCRIPTION_REQUESTED: VisionDescriptionRequestedEvent,
            EventType.WEBHOOK_RECEIVED: WebhookReceivedEvent,
            EventType.AUDIT_LOG_CREATED: AuditLogCreatedEvent,
            EventType.BULK_SCAN_MESSAGE_BATCH: BulkScanMessageBatchEvent,
            EventType.BULK_SCAN_COMPLETED: BulkScanCompletedEvent,
        }
        return mapping[event_type]

    async def _message_handler(
        self,
        event_type: EventType,
        msg: Msg,
    ) -> None:
        try:
            event_class = self._get_event_class(event_type)
            event = event_class.model_validate_json(msg.data)  # type: ignore[attr-defined]

            metadata = msg.metadata
            delivery_count = metadata.num_delivered if metadata else 1

            logger.info(
                f"Received event {event.event_id} of type {event_type.value} "
                f"(delivery attempt {delivery_count})"
            )

            handlers = self.handlers.get(event_type, [])

            handler_tasks = [
                asyncio.wait_for(
                    handler(event),
                    timeout=settings.NATS_HANDLER_TIMEOUT,
                )
                for handler in handlers
            ]

            results = await asyncio.gather(*handler_tasks, return_exceptions=True)

            failed = False
            for i, result in enumerate(results):
                if isinstance(result, asyncio.TimeoutError):
                    logger.error(
                        f"Handler {i} timeout for event {event.event_id} after "
                        f"{settings.NATS_HANDLER_TIMEOUT}s"
                    )
                    failed = True
                elif isinstance(result, Exception):
                    logger.error(
                        f"Handler {i} failed for event {event.event_id}: {result}",
                        exc_info=result,
                    )
                    failed = True

            if failed:
                await msg.nak()
                logger.warning(
                    f"Negative acknowledged event {event.event_id} due to handler failure "
                    f"(attempt {delivery_count})"
                )
            else:
                await msg.ack()
                logger.debug(f"Acknowledged event {event.event_id}")

        except TimeoutError:
            logger.error("Handler timeout for event processing")
            await msg.nak()
        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
            await msg.nak()

    async def subscribe_all(self) -> None:
        for event_type in EventType:
            await self.subscribe(event_type)

    async def subscribe(self, event_type: EventType) -> None:
        subject = self._get_subject(event_type)

        async def callback(msg: Msg) -> None:
            await self._message_handler(event_type, msg)

        subscription = await self.nats.subscribe(
            subject=subject,
            callback=callback,
        )
        self.subscriptions.append(subscription)
        logger.info(f"Subscribed to {subject} with JetStream durable consumer")

    async def unsubscribe_all(self) -> None:
        for subscription in self.subscriptions:
            try:
                await subscription.unsubscribe()
            except Exception as e:
                logger.error(f"Error unsubscribing: {e}")

        self.subscriptions.clear()
        logger.info("Unsubscribed from all subjects")


event_subscriber = EventSubscriber()
