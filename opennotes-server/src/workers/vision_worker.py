"""
Vision description worker using hybrid NATS→TaskIQ pattern.

NATS events trigger TaskIQ tasks for vision processing. This provides:
- Cross-service event routing via NATS JetStream
- Retries, result storage, and tracing via TaskIQ
- Self-contained workers that create their own connections

See ADR-004: NATS vs TaskIQ Usage Boundaries
"""

import logging
from datetime import UTC, datetime

from prometheus_client import Counter, Histogram

from src.config import settings
from src.events.schemas import EventType, VisionDescriptionRequestedEvent
from src.events.subscriber import event_subscriber
from src.tasks.content_monitoring_tasks import process_vision_description_task

logger = logging.getLogger(__name__)

vision_events_dispatched_total = Counter(
    "vision_events_dispatched_total",
    "Total number of vision description events dispatched to TaskIQ",
    ["status"],
)

vision_dispatch_lag_seconds = Histogram(
    "vision_dispatch_lag_seconds",
    "Lag between event creation and dispatch to TaskIQ",
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0],
)


class VisionDescriptionHandler:
    """
    Event handler that dispatches vision description requests to TaskIQ.

    This handler:
    1. Receives NATS events from the event subscriber
    2. Dispatches work to TaskIQ for reliable execution
    3. TaskIQ handles retries, result storage, and tracing
    """

    def __init__(self) -> None:
        self.subscriber = event_subscriber

    async def handle_vision_event(self, event: VisionDescriptionRequestedEvent) -> None:
        """Dispatch vision description request to TaskIQ task."""
        now = datetime.now(UTC)
        lag = (now - event.timestamp).total_seconds()
        vision_dispatch_lag_seconds.observe(lag)

        logger.info(
            f"Dispatching vision event {event.event_id} to TaskIQ",
            extra={
                "event_id": event.event_id,
                "message_archive_id": event.message_archive_id,
                "lag_seconds": f"{lag:.2f}",
            },
        )

        try:
            await process_vision_description_task.kiq(
                message_archive_id=event.message_archive_id,
                image_url=event.image_url,
                community_server_id=event.community_server_id,
                db_url=settings.DATABASE_URL,
            )

            vision_events_dispatched_total.labels(status="dispatched").inc()
            logger.debug(
                f"Vision event {event.event_id} dispatched to TaskIQ",
                extra={
                    "event_id": event.event_id,
                    "message_archive_id": event.message_archive_id,
                },
            )

        except Exception as e:
            vision_events_dispatched_total.labels(status="dispatch_error").inc()
            logger.error(
                f"Failed to dispatch vision event {event.event_id} to TaskIQ: {e}",
                extra={
                    "event_id": event.event_id,
                    "message_archive_id": event.message_archive_id,
                    "error_type": type(e).__name__,
                },
                exc_info=True,
            )
            raise

    def register(self) -> None:
        """Register the vision description event handler with the subscriber."""
        logger.info("Registering vision description event handler (TaskIQ dispatch)")
        self.subscriber.register_handler(
            EventType.VISION_DESCRIPTION_REQUESTED,
            self.handle_vision_event,
        )
        logger.info("Vision description event handler registered")
