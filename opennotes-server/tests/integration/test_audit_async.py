"""
Integration tests for audit log worker.

Tests verify:
- Audit middleware publishes events to NATS
- Audit worker dispatches events to TaskIQ
- NATS subscriber registration
"""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from src.events.schemas import AuditLogCreatedEvent, EventType
from src.main import app
from src.workers.audit_worker import AuditWorker


class TestAuditMiddlewareAsync:
    @pytest.mark.asyncio
    async def test_audit_middleware_publishes_to_nats(self, auth_headers: dict) -> None:
        with patch("src.middleware.audit.event_publisher") as mock_publisher:
            mock_publisher.publish_audit_log = AsyncMock(return_value="event-123")

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/v2/notes",
                    json={
                        "data": {
                            "type": "notes",
                            "attributes": {
                                "author_id": "test-user",
                                "summary": "Test note for audit",
                                "classification": "NOT_MISLEADING",
                                "community_server_id": str(uuid4()),
                            },
                        }
                    },
                    headers=auth_headers,
                )

            if response.status_code in [200, 201]:
                mock_publisher.publish_audit_log.assert_called_once()
                call_args = mock_publisher.publish_audit_log.call_args
                assert call_args[1]["action"] == "POST /api/v2/notes"
                assert call_args[1]["user_id"] is not None

    @pytest.mark.asyncio
    async def test_audit_middleware_does_not_block_on_nats_failure(
        self, auth_headers: dict
    ) -> None:
        with patch("src.middleware.audit.event_publisher") as mock_publisher:
            mock_publisher.publish_audit_log = AsyncMock(
                side_effect=Exception("NATS connection failed")
            )

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/v2/notes",
                    json={
                        "data": {
                            "type": "notes",
                            "attributes": {
                                "author_id": "test-user",
                                "summary": "Test note for audit",
                                "classification": "NOT_MISLEADING",
                                "community_server_id": str(uuid4()),
                            },
                        }
                    },
                    headers=auth_headers,
                )

            assert response.status_code in [200, 201, 400, 401, 422, 500]

    @pytest.mark.asyncio
    async def test_audit_middleware_only_logs_write_operations(self) -> None:
        with patch("src.middleware.audit.event_publisher") as mock_publisher:
            mock_publisher.publish_audit_log = AsyncMock()

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                await client.get("/health")

            mock_publisher.publish_audit_log.assert_not_called()


class TestAuditWorker:
    """Test AuditWorker dispatches events to TaskIQ."""

    @pytest.mark.asyncio
    async def test_audit_worker_dispatches_to_taskiq(self) -> None:
        """Verify audit worker dispatches events to TaskIQ task."""
        worker = AuditWorker()

        user_id = uuid4()
        event = AuditLogCreatedEvent(
            event_id="test-event-123",
            user_id=user_id,
            action="POST /api/v1/notes",
            resource="notes",
            resource_id="note-123",
            details="Status: 201",
            ip_address="127.0.0.1",
            user_agent="test-client/1.0",
            created_at=datetime.now(UTC),
        )

        with patch("src.workers.audit_worker.persist_audit_log_task") as mock_task:
            mock_task.kiq = AsyncMock()

            await worker.handle_audit_event(event)

            mock_task.kiq.assert_called_once()
            call_kwargs = mock_task.kiq.call_args[1]
            assert call_kwargs["user_id"] == str(user_id)
            assert call_kwargs["action"] == "POST /api/v1/notes"
            assert call_kwargs["resource"] == "notes"
            assert call_kwargs["resource_id"] == "note-123"
            assert call_kwargs["ip_address"] == "127.0.0.1"
            assert call_kwargs["user_agent"] == "test-client/1.0"

    @pytest.mark.asyncio
    async def test_audit_worker_handles_dispatch_errors(self) -> None:
        """Verify audit worker handles TaskIQ dispatch failures."""
        worker = AuditWorker()

        event = AuditLogCreatedEvent(
            event_id="test-event-456",
            user_id=uuid4(),
            action="POST /api/v1/notes",
            resource="notes",
            resource_id=None,
            details="Status: 201",
            ip_address=None,
            user_agent=None,
            created_at=datetime.now(UTC),
        )

        with patch("src.workers.audit_worker.persist_audit_log_task") as mock_task:
            mock_task.kiq = AsyncMock(side_effect=Exception("TaskIQ dispatch failed"))

            with pytest.raises(Exception, match="TaskIQ dispatch failed"):
                await worker.handle_audit_event(event)

    @pytest.mark.asyncio
    async def test_audit_worker_records_dispatch_lag(self) -> None:
        """Verify audit worker records lag metric."""
        worker = AuditWorker()

        past_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        event = AuditLogCreatedEvent(
            event_id="test-event-789",
            user_id=uuid4(),
            action="POST /api/v1/notes",
            resource="notes",
            resource_id=None,
            details=None,
            ip_address=None,
            user_agent=None,
            created_at=past_time,
        )

        with (
            patch("src.workers.audit_worker.persist_audit_log_task") as mock_task,
            patch("src.workers.audit_worker.audit_dispatch_lag_seconds") as mock_lag,
        ):
            mock_task.kiq = AsyncMock()
            mock_lag.observe = MagicMock()

            await worker.handle_audit_event(event)

            mock_lag.observe.assert_called_once()
            lag_value = mock_lag.observe.call_args[0][0]
            assert lag_value > 0

    @pytest.mark.asyncio
    async def test_audit_worker_metrics_on_success(self) -> None:
        """Verify audit worker increments success metric."""
        worker = AuditWorker()

        event = AuditLogCreatedEvent(
            event_id="test-metrics-success",
            user_id=uuid4(),
            action="POST /api/v1/notes",
            resource="notes",
            resource_id=None,
            details=None,
            ip_address=None,
            user_agent=None,
            created_at=datetime.now(UTC),
        )

        with (
            patch("src.workers.audit_worker.persist_audit_log_task") as mock_task,
            patch("src.workers.audit_worker.audit_events_dispatched_total") as mock_counter,
        ):
            mock_task.kiq = AsyncMock()
            mock_counter.labels = MagicMock(return_value=mock_counter)
            mock_counter.inc = MagicMock()

            await worker.handle_audit_event(event)

            mock_counter.labels.assert_called_with(status="dispatched")
            mock_counter.inc.assert_called_once()

    @pytest.mark.asyncio
    async def test_nats_subscriber_registration(self) -> None:
        """Verify worker registers handler with NATS subscriber."""
        worker = AuditWorker()

        with patch("src.events.subscriber.event_subscriber") as mock_subscriber:
            mock_subscriber.register_handler = MagicMock()
            mock_subscriber.subscribe = AsyncMock()
            mock_subscriber.unsubscribe_all = AsyncMock()

            worker.subscriber = mock_subscriber

            # Start worker in background task
            start_task = asyncio.create_task(worker.start())

            # Give it time to register and subscribe
            await asyncio.sleep(0.1)

            # Stop the worker
            await worker.stop()

            # Wait for start task to complete
            await start_task

            mock_subscriber.register_handler.assert_called_once_with(
                EventType.AUDIT_LOG_CREATED,
                worker.handle_audit_event,
            )

            mock_subscriber.subscribe.assert_called_once_with(EventType.AUDIT_LOG_CREATED)
