"""
Audit log worker using hybrid NATS→TaskIQ pattern.

NATS events trigger TaskIQ tasks for audit log persistence. This provides:
- Cross-service event routing via NATS JetStream
- Retries, result storage, and tracing via TaskIQ
- Self-contained workers that create their own connections

See ADR-004: NATS vs TaskIQ Usage Boundaries
"""

import asyncio
import logging
import signal
from collections.abc import Callable
from datetime import UTC, datetime

from prometheus_client import Counter, Histogram

from src.config import settings
from src.events.schemas import AuditLogCreatedEvent, EventType
from src.events.subscriber import event_subscriber
from src.tasks.content_monitoring_tasks import persist_audit_log_task

logger = logging.getLogger(__name__)

audit_events_dispatched_total = Counter(
    "audit_events_dispatched_total",
    "Total number of audit events dispatched to TaskIQ",
    ["status"],
)

audit_dispatch_lag_seconds = Histogram(
    "audit_dispatch_lag_seconds",
    "Lag between event creation and dispatch to TaskIQ",
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0],
)


class AuditWorker:
    """
    Audit worker that dispatches audit log events to TaskIQ.

    This worker:
    1. Receives NATS events from the event subscriber
    2. Dispatches work to TaskIQ for reliable execution
    3. TaskIQ handles retries, result storage, and tracing
    """

    def __init__(self) -> None:
        self.subscriber = event_subscriber
        self.running = False
        self.shutdown_event = asyncio.Event()

    async def handle_audit_event(self, event: AuditLogCreatedEvent) -> None:
        """Dispatch audit log event to TaskIQ task."""
        now = datetime.now(UTC)
        lag = (now - event.created_at).total_seconds()
        audit_dispatch_lag_seconds.observe(lag)

        logger.debug(f"Dispatching audit event {event.event_id} to TaskIQ (lag: {lag:.2f}s)")

        try:
            await persist_audit_log_task.kiq(
                user_id=str(event.user_id) if event.user_id else None,
                community_server_id=None,
                action=event.action,
                resource=event.resource,
                resource_id=event.resource_id,
                details={"raw": event.details} if event.details else None,
                ip_address=event.ip_address,
                user_agent=event.user_agent,
                db_url=settings.DATABASE_URL,
                created_at=event.created_at.isoformat(),
            )

            audit_events_dispatched_total.labels(status="dispatched").inc()
            logger.debug(f"Audit event {event.event_id} dispatched to TaskIQ")

        except Exception as e:
            audit_events_dispatched_total.labels(status="dispatch_error").inc()
            logger.error(
                f"Failed to dispatch audit event {event.event_id} to TaskIQ: {e}",
                exc_info=True,
            )
            raise

    async def start(self) -> None:
        logger.info("Starting audit worker (TaskIQ dispatch mode)...")
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
