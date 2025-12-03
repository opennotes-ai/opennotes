import logging
from datetime import UTC, datetime
from uuid import UUID

from prometheus_client import Counter, Histogram
from sqlalchemy.exc import SQLAlchemyError

from src.database import get_session_maker
from src.events.schemas import EventType, VisionDescriptionRequestedEvent
from src.events.subscriber import event_subscriber
from src.notes.message_archive_models import MessageArchive
from src.services.vision_service import VisionService

logger = logging.getLogger(__name__)

vision_events_processed_total = Counter(
    "vision_events_processed_total",
    "Total number of vision description events processed",
    ["status"],
)

vision_processing_duration_seconds = Histogram(
    "vision_processing_duration_seconds",
    "Time taken to process vision description events",
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 15.0, 30.0, 60.0],
)

vision_processing_lag_seconds = Histogram(
    "vision_processing_lag_seconds",
    "Lag between event creation and processing",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0],
)

vision_api_failures_total = Counter(
    "vision_api_failures_total",
    "Total number of vision API call failures",
)


class VisionDescriptionHandler:
    """
    Event handler for processing vision description requests asynchronously.
    This handler processes images in the background without blocking the HTTP request.
    """

    def __init__(self, vision_service: VisionService) -> None:
        self.vision_service = vision_service
        self.subscriber = event_subscriber

    async def handle_vision_event(self, event: VisionDescriptionRequestedEvent) -> None:
        """Process vision description request event."""
        start_time = datetime.now(UTC)

        try:
            now = datetime.now(UTC)
            lag = (now - event.timestamp).total_seconds()
            vision_processing_lag_seconds.observe(lag)

            logger.info(
                f"Processing vision description event {event.event_id} for message archive {event.message_archive_id}",
                extra={
                    "event_id": event.event_id,
                    "message_archive_id": event.message_archive_id,
                    "lag_seconds": f"{lag:.2f}",
                },
            )

            async with get_session_maker()() as session:
                message_archive = await session.get(MessageArchive, UUID(event.message_archive_id))
                if not message_archive:
                    logger.warning(
                        f"Message archive {event.message_archive_id} not found for vision event {event.event_id}"
                    )
                    vision_events_processed_total.labels(status="not_found").inc()
                    return

                if message_archive.image_description:
                    logger.debug(
                        f"Message archive {event.message_archive_id} already has description, skipping"
                    )
                    vision_events_processed_total.labels(status="already_processed").inc()
                    return

                try:
                    description = await self.vision_service.describe_image(
                        db=session,
                        image_url=event.image_url,
                        community_server_id=event.community_server_id,
                        detail="auto",
                    )

                    message_archive.image_description = description
                    await session.commit()

                    processing_time = (datetime.now(UTC) - start_time).total_seconds()
                    vision_processing_duration_seconds.observe(processing_time)
                    vision_events_processed_total.labels(status="success").inc()

                    logger.info(
                        f"Successfully generated vision description for message archive {event.message_archive_id}",
                        extra={
                            "event_id": event.event_id,
                            "message_archive_id": event.message_archive_id,
                            "processing_time_seconds": f"{processing_time:.2f}",
                            "description_length": len(description),
                        },
                    )

                except Exception as e:
                    logger.error(
                        f"Vision API error for event {event.event_id}: {e}",
                        extra={
                            "event_id": event.event_id,
                            "message_archive_id": event.message_archive_id,
                            "error_type": type(e).__name__,
                        },
                        exc_info=True,
                    )
                    vision_api_failures_total.inc()
                    vision_events_processed_total.labels(status="api_error").inc()

        except SQLAlchemyError as e:
            logger.error(
                f"Database error processing vision event {event.event_id}: {e}",
                extra={
                    "event_id": event.event_id,
                    "message_archive_id": event.message_archive_id,
                },
                exc_info=True,
            )
            vision_events_processed_total.labels(status="db_error").inc()
        except Exception as e:
            logger.error(
                f"Unexpected error processing vision event {event.event_id}: {e}",
                extra={
                    "event_id": event.event_id,
                    "message_archive_id": event.message_archive_id,
                },
                exc_info=True,
            )
            vision_events_processed_total.labels(status="error").inc()

    def register(self) -> None:
        """Register the vision description event handler with the subscriber."""
        logger.info("Registering vision description event handler")
        self.subscriber.register_handler(
            EventType.VISION_DESCRIPTION_REQUESTED,
            self.handle_vision_event,
        )
        logger.info("Vision description event handler registered")
