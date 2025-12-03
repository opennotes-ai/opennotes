import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from nats.aio.msg import Msg

from src.config import settings
from src.events.nats_client import Subscription, nats_client
from src.events.schemas import (
    AuditLogCreatedEvent,
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
        }
        return mapping[event_type]

    async def _message_handler(
        self,
        event_type: EventType,
        msg: Msg,
    ) -> None:
        is_jetstream = False
        delivery_count = 1

        try:
            event_class = self._get_event_class(event_type)
            # Use model_validate_json to handle JSON directly, which properly deserializes
            # datetime and UUID strings even with strict=True
            event = event_class.model_validate_json(msg.data)  # type: ignore[attr-defined]

            # Check if this is a JetStream message or a core NATS message
            try:
                metadata = msg.metadata
                is_jetstream = True
                delivery_count = metadata.num_delivered if metadata else 1
            except Exception:
                # This is a core NATS message, not a JetStream message
                # Core NATS doesn't support ack/nak, so we'll just process it
                pass

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

            if is_jetstream:
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
            if is_jetstream:
                await msg.nak()
        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
            if is_jetstream:
                await msg.nak()

    async def subscribe_all(self) -> None:
        for event_type in EventType:
            await self.subscribe(event_type)

    async def subscribe(self, event_type: EventType) -> None:
        subject = self._get_subject(event_type)
        queue = f"{settings.NATS_CONSUMER_NAME}_{event_type.value}"

        async def callback(msg: Msg) -> None:
            await self._message_handler(event_type, msg)

        # Try JetStream first for persistence, fall back to core NATS if it times out
        try:
            # Use ephemeral consumers - durable consumers have timeout issues in nats-py
            # See: https://github.com/nats-io/nats.py/issues/437
            # Add timeout to prevent subscribe() from hanging indefinitely during startup
            # JetStream consumer creation can be slow or timeout under concurrent load
            subscription = await asyncio.wait_for(
                self.nats.subscribe(
                    subject=subject,
                    queue=queue,
                    callback=callback,
                    durable=None,  # Ephemeral consumer
                    use_jetstream=True,
                ),
                timeout=15.0,  # 15 second timeout for JetStream subscription
            )
            self.subscriptions.append(subscription)
            logger.info(
                f"Subscribed to {subject} with JetStream ephemeral consumer (queue: {queue})"
            )
        except TimeoutError:
            logger.warning(
                f"JetStream subscription timed out for {subject} after 15 seconds. "
                "Falling back to core NATS subscription (no persistence)."
            )
            try:
                # Fall back to core NATS subscription (no JetStream persistence)
                # This is less reliable but works during development/startup
                subscription = await self.nats.subscribe(
                    subject=subject,
                    queue=queue,
                    callback=callback,
                    use_jetstream=False,
                )
                self.subscriptions.append(subscription)
                logger.info(f"Subscribed to {subject} with core NATS (queue: {queue})")
            except Exception as core_error:
                logger.error(
                    f"Failed to subscribe to {subject} (both JetStream and core NATS): {core_error}"
                )
                raise
        except Exception as jetstream_error:
            logger.warning(
                f"JetStream subscription failed for {subject}: {jetstream_error}. "
                "Falling back to core NATS subscription (no persistence)."
            )
            try:
                # Fall back to core NATS subscription (no JetStream persistence)
                # This is less reliable but works during development/startup
                subscription = await self.nats.subscribe(
                    subject=subject,
                    queue=queue,
                    callback=callback,
                    use_jetstream=False,
                )
                self.subscriptions.append(subscription)
                logger.info(f"Subscribed to {subject} with core NATS (queue: {queue})")
            except Exception as core_error:
                logger.error(
                    f"Failed to subscribe to {subject} (both JetStream and core NATS): {core_error}"
                )
                raise

    async def unsubscribe_all(self) -> None:
        for subscription in self.subscriptions:
            try:
                await subscription.unsubscribe()
            except Exception as e:
                logger.error(f"Error unsubscribing: {e}")

        self.subscriptions.clear()
        logger.info("Unsubscribed from all subjects")


event_subscriber = EventSubscriber()
