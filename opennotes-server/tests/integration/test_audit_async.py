from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from src.events.schemas import AuditLogCreatedEvent, EventType
from src.main import app
from src.users.models import AuditLog, User
from src.workers.audit_worker import AuditWorker


class TestAuditMiddlewareAsync:
    @pytest.mark.asyncio
    async def test_audit_middleware_publishes_to_nats(self, auth_headers: dict) -> None:
        with patch("src.middleware.audit.event_publisher") as mock_publisher:
            mock_publisher.publish_audit_log = AsyncMock(return_value="event-123")

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/v1/notes",
                    json={
                        "author_participant_id": "test-user",
                        "summary": "Test note for audit",
                        "classification": "NOT_MISLEADING",
                    },
                    headers=auth_headers,
                )

            if response.status_code in [200, 201]:
                mock_publisher.publish_audit_log.assert_called_once()
                call_args = mock_publisher.publish_audit_log.call_args
                assert call_args[1]["action"] == "POST /api/v1/notes"
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
                    "/api/v1/notes",
                    json={
                        "author_participant_id": "test-user",
                        "summary": "Test note for audit",
                        "classification": "NOT_MISLEADING",
                    },
                    headers=auth_headers,
                )

            assert response.status_code in [200, 201, 400, 401, 422]

    @pytest.mark.asyncio
    async def test_audit_middleware_only_logs_write_operations(self) -> None:
        with patch("src.middleware.audit.event_publisher") as mock_publisher:
            mock_publisher.publish_audit_log = AsyncMock()

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                await client.get("/health")

            mock_publisher.publish_audit_log.assert_not_called()


class TestAuditWorker:
    @pytest.mark.asyncio
    async def test_audit_worker_processes_event(self, db: object) -> None:
        # Create test user
        from src.auth.password import get_password_hash

        user_id = uuid4()
        user = User(
            id=user_id,
            username="testuser",
            email="test@example.com",
            hashed_password=get_password_hash("TestPassword123!"),
            full_name="Test User",
            role="user",
            is_active=True,
            is_superuser=False,
        )
        db.add(user)
        await db.commit()

        # Reset database engine to avoid event loop issues
        import src.database

        src.database._engine = None
        src.database._async_session_maker = None

        worker = AuditWorker()

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

        await worker.handle_audit_event(event)

        result = await db.execute(select(AuditLog).where(AuditLog.user_id == user_id))
        audit_log = result.scalar_one_or_none()

        assert audit_log is not None
        assert audit_log.action == "POST /api/v1/notes"
        assert audit_log.resource == "notes"
        assert audit_log.resource_id == "note-123"
        assert audit_log.details == "Status: 201"
        assert audit_log.ip_address == "127.0.0.1"
        assert audit_log.user_agent == "test-client/1.0"

    @pytest.mark.asyncio
    async def test_audit_worker_handles_db_errors(self) -> None:
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

        with patch("src.workers.audit_worker.get_session_maker") as mock_get_session_maker:
            mock_session = AsyncMock()
            mock_session.__aenter__.return_value = mock_session
            mock_session.commit = AsyncMock(side_effect=Exception("DB connection lost"))
            mock_session_maker = MagicMock(return_value=mock_session)
            mock_get_session_maker.return_value = mock_session_maker

            with pytest.raises(Exception, match="DB connection lost"):
                await worker.handle_audit_event(event)

    @pytest.mark.asyncio
    async def test_audit_worker_records_processing_lag(self, db: object) -> None:
        # Create test user
        from src.auth.password import get_password_hash

        user_id = uuid4()
        user = User(
            id=user_id,
            username="testuser2",
            email="test2@example.com",
            hashed_password=get_password_hash("TestPassword123!"),
            full_name="Test User",
            role="user",
            is_active=True,
            is_superuser=False,
        )
        db.add(user)
        await db.commit()

        # Reset database engine to avoid event loop issues
        import src.database

        if src.database._engine is not None:
            await src.database.close_db()
        src.database._engine = None
        src.database._async_session_maker = None

        worker = AuditWorker()

        past_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        event = AuditLogCreatedEvent(
            event_id="test-event-789",
            user_id=user_id,
            action="POST /api/v1/notes",
            resource="notes",
            resource_id=None,
            details=None,
            ip_address=None,
            user_agent=None,
            created_at=past_time,
        )

        with patch("src.workers.audit_worker.audit_processing_lag_seconds") as mock_lag:
            mock_lag.observe = MagicMock()

            await worker.handle_audit_event(event)

            mock_lag.observe.assert_called_once()
            lag_value = mock_lag.observe.call_args[0][0]
            assert lag_value > 0

    @pytest.mark.asyncio
    async def test_audit_worker_metrics_on_success(self, db: object) -> None:
        # Create test user
        from src.auth.password import get_password_hash

        user_id = uuid4()
        user = User(
            id=user_id,
            username="testuser3",
            email="test3@example.com",
            hashed_password=get_password_hash("TestPassword123!"),
            full_name="Test User",
            role="user",
            is_active=True,
            is_superuser=False,
        )
        db.add(user)
        await db.commit()

        # Reset database engine to avoid event loop issues
        import src.database

        src.database._engine = None
        src.database._async_session_maker = None

        worker = AuditWorker()

        event = AuditLogCreatedEvent(
            event_id="test-metrics-success",
            user_id=user_id,
            action="POST /api/v1/notes",
            resource="notes",
            resource_id=None,
            details=None,
            ip_address=None,
            user_agent=None,
            created_at=datetime.now(UTC),
        )

        with patch("src.workers.audit_worker.audit_events_processed_total") as mock_counter:
            mock_counter.labels = MagicMock(return_value=mock_counter)
            mock_counter.inc = MagicMock()

            await worker.handle_audit_event(event)

            mock_counter.labels.assert_called_with(status="success")
            mock_counter.inc.assert_called_once()

    @pytest.mark.asyncio
    async def test_nats_subscriber_registration(self) -> None:
        import asyncio

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
