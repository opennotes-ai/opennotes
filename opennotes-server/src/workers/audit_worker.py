import asyncio
import logging
import signal
from collections.abc import Callable
from datetime import UTC, datetime

from prometheus_client import Counter, Histogram
from sqlalchemy.exc import SQLAlchemyError

from src.database import get_session_maker
from src.events.schemas import AuditLogCreatedEvent, EventType
from src.events.subscriber import event_subscriber
from src.users.models import AuditLog

logger = logging.getLogger(__name__)

audit_events_processed_total = Counter(
    "audit_events_processed_total",
    "Total number of audit events processed by worker",
    ["status"],
)

audit_processing_duration_seconds = Histogram(
    "audit_processing_duration_seconds",
    "Time taken to process audit events",
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
)

audit_processing_lag_seconds = Histogram(
    "audit_processing_lag_seconds",
    "Lag between event creation and processing",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0],
)

audit_db_write_failures_total = Counter(
    "audit_db_write_failures_total",
    "Total number of failed audit log database writes",
)


class AuditWorker:
    def __init__(self) -> None:
        self.subscriber = event_subscriber
        self.running = False
        self.shutdown_event = asyncio.Event()

    async def handle_audit_event(self, event: AuditLogCreatedEvent) -> None:
        start_time = datetime.now(UTC)

        try:
            now = datetime.now(UTC)
            lag = (now - event.created_at).total_seconds()
            audit_processing_lag_seconds.observe(lag)

            logger.debug(
                f"Processing audit event {event.event_id} for user {event.user_id} "
                f"(lag: {lag:.2f}s)"
            )

            async with get_session_maker()() as session:
                audit_log = AuditLog(
                    user_id=event.user_id,
                    action=event.action,
                    resource=event.resource,
                    resource_id=event.resource_id,
                    details=event.details,
                    ip_address=event.ip_address,
                    user_agent=event.user_agent,
                    created_at=event.created_at,
                )
                session.add(audit_log)
                await session.commit()

            processing_time = (datetime.now(UTC) - start_time).total_seconds()
            audit_processing_duration_seconds.observe(processing_time)
            audit_events_processed_total.labels(status="success").inc()

            logger.debug(
                f"Successfully processed audit event {event.event_id} in {processing_time:.3f}s"
            )

        except SQLAlchemyError as e:
            logger.error(
                f"Database error processing audit event {event.event_id}: {e}",
                exc_info=True,
            )
            audit_db_write_failures_total.inc()
            audit_events_processed_total.labels(status="db_error").inc()
            raise
        except Exception as e:
            logger.error(
                f"Unexpected error processing audit event {event.event_id}: {e}",
                exc_info=True,
            )
            audit_events_processed_total.labels(status="error").inc()
            raise

    async def start(self) -> None:
        logger.info("Starting audit worker...")
        self.running = True

        self.subscriber.register_handler(
            EventType.AUDIT_LOG_CREATED,
            self.handle_audit_event,
        )

        await self.subscriber.subscribe(EventType.AUDIT_LOG_CREATED)

        logger.info("Audit worker started and listening for events")

        await self.shutdown_event.wait()

    async def stop(self) -> None:
        logger.info("Stopping audit worker...")
        self.running = False
        self.shutdown_event.set()

        await self.subscriber.unsubscribe_all()

        logger.info("Audit worker stopped")

    def handle_signal(self, sig: int) -> None:
        logger.info(f"Received signal {sig}, initiating graceful shutdown...")
        task = asyncio.create_task(self.stop())
        task.add_done_callback(lambda _: None)


async def main() -> None:
    worker = AuditWorker()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):

        def make_handler(s: signal.Signals) -> Callable[[], None]:
            def handler() -> None:
                worker.handle_signal(s)

            return handler

        loop.add_signal_handler(sig, make_handler(sig))

    try:
        await worker.start()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    finally:
        await worker.stop()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    asyncio.run(main())
