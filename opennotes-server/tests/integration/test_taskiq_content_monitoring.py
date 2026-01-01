"""
Integration tests for TaskIQ content monitoring tasks.

Task: task-910 - Migrate content monitoring system to TaskIQ

These tests verify:
- AC #9: Integration tests exist for TaskIQ task execution
- Task registration and broker configuration
- Task dispatch patterns
- OpenTelemetry tracing integration

Note: These tests focus on broker and task registration without importing
the full application modules to avoid torch/litellm import chain issues.
Full end-to-end testing is done via staging environment.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


class TestTaskRegistration:
    """Test that all content monitoring tasks are properly registered."""

    def test_all_content_monitoring_tasks_registered(self):
        """Verify all 5 content monitoring tasks are registered with broker."""
        from src.tasks.broker import _all_registered_tasks

        expected_tasks = [
            "content:batch_scan",
            "content:finalize_scan",
            "content:ai_note",
            "content:vision_description",
            "content:audit_log",
        ]

        for task_name in expected_tasks:
            assert task_name in _all_registered_tasks, f"Task {task_name} not registered"

    def test_task_labels_include_component(self):
        """All content monitoring tasks have component label."""
        from src.tasks.broker import _all_registered_tasks

        content_tasks = [name for name in _all_registered_tasks if name.startswith("content:")]

        for task_name in content_tasks:
            _, labels = _all_registered_tasks[task_name]
            assert labels.get("component") == "content_monitoring", (
                f"Task {task_name} missing component label"
            )

    def test_task_labels_include_task_type(self):
        """All content monitoring tasks have task_type label."""
        from src.tasks.broker import _all_registered_tasks

        expected_types = {
            "content:batch_scan": "batch",
            "content:finalize_scan": "finalize",
            "content:ai_note": "generation",
            "content:vision_description": "vision",
            "content:audit_log": "audit",
        }

        for task_name, expected_type in expected_types.items():
            _, labels = _all_registered_tasks[task_name]
            assert labels.get("task_type") == expected_type, (
                f"Task {task_name} has wrong task_type: {labels.get('task_type')}"
            )


class TestTaskIQBrokerConfiguration:
    """Test TaskIQ broker configuration."""

    def test_broker_has_opentelemetry_middleware(self):
        """Verify broker is configured with OpenTelemetry middleware."""
        from src.tasks.broker import get_broker

        broker = get_broker()
        middleware_types = [type(m).__name__ for m in broker.middlewares]

        # Check for SafeOpenTelemetryMiddleware (our wrapper around OpenTelemetryMiddleware)
        assert "SafeOpenTelemetryMiddleware" in middleware_types, (
            f"SafeOpenTelemetryMiddleware not configured on broker. Found: {middleware_types}"
        )

    def test_broker_has_retry_middleware(self):
        """Verify broker is configured with retry middleware."""
        from src.tasks.broker import get_broker

        broker = get_broker()
        middleware_types = [type(m).__name__ for m in broker.middlewares]

        assert "SimpleRetryMiddleware" in middleware_types, (
            "SimpleRetryMiddleware not configured on broker"
        )


class TestDualCompletionTrigger:
    """Test dual completion trigger pattern for bulk scan."""

    @pytest.mark.asyncio
    async def test_batch_task_triggers_finalize_when_complete(self):
        """Verify batch task triggers finalize task when all batches processed."""
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=lambda: "platform123")
        )
        mock_session.commit = AsyncMock()

        mock_session_maker = MagicMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_service = MagicMock()
        mock_service.process_messages = AsyncMock(return_value=[])
        mock_service.increment_processed_count = AsyncMock()
        mock_service.get_processed_count = AsyncMock(return_value=100)
        mock_service.get_all_batches_transmitted = AsyncMock(return_value=(True, 100))
        mock_service.append_flagged_result = AsyncMock()
        mock_service.try_set_finalize_dispatched = AsyncMock(return_value=True)

        mock_redis = AsyncMock()
        mock_redis.connect = AsyncMock()
        mock_redis.disconnect = AsyncMock()
        mock_redis.client = MagicMock()

        settings = MagicMock()
        settings.DB_POOL_SIZE = 5
        settings.DB_POOL_MAX_OVERFLOW = 10
        settings.DB_POOL_TIMEOUT = 30
        settings.DB_POOL_RECYCLE = 1800

        with (
            patch("src.tasks.content_monitoring_tasks.create_async_engine") as mock_engine,
            patch(
                "src.tasks.content_monitoring_tasks.async_sessionmaker",
                return_value=mock_session_maker,
            ),
            patch("src.cache.redis_client.RedisClient", return_value=mock_redis),
            patch(
                "src.bulk_content_scan.service.BulkContentScanService",
                return_value=mock_service,
            ),
            patch("src.fact_checking.embedding_service.EmbeddingService"),
            patch("src.tasks.content_monitoring_tasks._get_llm_service"),
            patch("src.config.get_settings", return_value=settings),
            patch("src.tasks.content_monitoring_tasks.finalize_bulk_scan_task") as mock_finalize,
        ):
            mock_engine.return_value = MagicMock()
            mock_engine.return_value.dispose = AsyncMock()
            mock_finalize.kiq = AsyncMock()

            from src.tasks.content_monitoring_tasks import process_bulk_scan_batch_task

            await process_bulk_scan_batch_task(
                scan_id=str(uuid4()),
                community_server_id=str(uuid4()),
                batch_number=10,
                messages=[],
                db_url="postgresql+asyncpg://test:test@localhost/test",
                redis_url="redis://localhost:6379",
            )

            mock_finalize.kiq.assert_called_once()

    @pytest.mark.asyncio
    async def test_batch_task_does_not_trigger_when_incomplete(self):
        """Verify batch task doesn't trigger finalize when batches remain."""
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=lambda: "platform123")
        )
        mock_session.commit = AsyncMock()

        mock_session_maker = MagicMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_service = MagicMock()
        mock_service.process_messages = AsyncMock(return_value=[])
        mock_service.increment_processed_count = AsyncMock()
        mock_service.get_processed_count = AsyncMock(return_value=50)
        mock_service.get_all_batches_transmitted = AsyncMock(return_value=(False, None))
        mock_service.append_flagged_result = AsyncMock()

        mock_redis = AsyncMock()
        mock_redis.connect = AsyncMock()
        mock_redis.disconnect = AsyncMock()
        mock_redis.client = MagicMock()

        settings = MagicMock()
        settings.DB_POOL_SIZE = 5
        settings.DB_POOL_MAX_OVERFLOW = 10
        settings.DB_POOL_TIMEOUT = 30
        settings.DB_POOL_RECYCLE = 1800

        with (
            patch("src.tasks.content_monitoring_tasks.create_async_engine") as mock_engine,
            patch(
                "src.tasks.content_monitoring_tasks.async_sessionmaker",
                return_value=mock_session_maker,
            ),
            patch("src.cache.redis_client.RedisClient", return_value=mock_redis),
            patch(
                "src.bulk_content_scan.service.BulkContentScanService",
                return_value=mock_service,
            ),
            patch("src.fact_checking.embedding_service.EmbeddingService"),
            patch("src.tasks.content_monitoring_tasks._get_llm_service"),
            patch("src.config.get_settings", return_value=settings),
            patch("src.tasks.content_monitoring_tasks.finalize_bulk_scan_task") as mock_finalize,
        ):
            mock_engine.return_value = MagicMock()
            mock_engine.return_value.dispose = AsyncMock()
            mock_finalize.kiq = AsyncMock()

            from src.tasks.content_monitoring_tasks import process_bulk_scan_batch_task

            await process_bulk_scan_batch_task(
                scan_id=str(uuid4()),
                community_server_id=str(uuid4()),
                batch_number=5,
                messages=[],
                db_url="postgresql+asyncpg://test:test@localhost/test",
                redis_url="redis://localhost:6379",
            )

            mock_finalize.kiq.assert_not_called()


class TestTaskDispatchPattern:
    """Test NATS → TaskIQ dispatch pattern works correctly."""

    @pytest.mark.asyncio
    async def test_task_receives_correct_parameters(self):
        """Verify task receives all required parameters from dispatcher."""
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=lambda: "platform123")
        )
        mock_session.commit = AsyncMock()

        mock_session_maker = MagicMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_service = MagicMock()
        mock_service.process_messages = AsyncMock(return_value=[])
        mock_service.increment_processed_count = AsyncMock()
        mock_service.get_processed_count = AsyncMock(return_value=2)
        mock_service.get_all_batches_transmitted = AsyncMock(return_value=(False, None))
        mock_service.append_flagged_result = AsyncMock()

        mock_redis = AsyncMock()
        mock_redis.connect = AsyncMock()
        mock_redis.disconnect = AsyncMock()
        mock_redis.client = MagicMock()

        settings = MagicMock()
        settings.DB_POOL_SIZE = 5
        settings.DB_POOL_MAX_OVERFLOW = 10
        settings.DB_POOL_TIMEOUT = 30
        settings.DB_POOL_RECYCLE = 1800

        scan_id = str(uuid4())
        community_server_id = str(uuid4())
        batch_number = 5
        db_url = "postgresql+asyncpg://test:test@localhost/test"
        redis_url = "redis://localhost:6379"

        with (
            patch("src.tasks.content_monitoring_tasks.create_async_engine") as mock_engine,
            patch(
                "src.tasks.content_monitoring_tasks.async_sessionmaker",
                return_value=mock_session_maker,
            ),
            patch("src.cache.redis_client.RedisClient", return_value=mock_redis),
            patch(
                "src.bulk_content_scan.service.BulkContentScanService",
                return_value=mock_service,
            ),
            patch("src.fact_checking.embedding_service.EmbeddingService"),
            patch("src.tasks.content_monitoring_tasks._get_llm_service"),
            patch("src.config.get_settings", return_value=settings),
        ):
            mock_engine.return_value = MagicMock()
            mock_engine.return_value.dispose = AsyncMock()

            from src.tasks.content_monitoring_tasks import process_bulk_scan_batch_task

            result = await process_bulk_scan_batch_task(
                scan_id=scan_id,
                community_server_id=community_server_id,
                batch_number=batch_number,
                messages=[],
                db_url=db_url,
                redis_url=redis_url,
            )

            assert result["status"] == "completed"
            mock_redis.connect.assert_called_once_with(redis_url)

    @pytest.mark.asyncio
    async def test_task_cleanup_on_success(self):
        """Verify task cleans up resources on successful completion."""
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=lambda: "platform123")
        )
        mock_session.commit = AsyncMock()

        mock_session_maker = MagicMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_service = MagicMock()
        mock_service.process_messages = AsyncMock(return_value=[])
        mock_service.increment_processed_count = AsyncMock()
        mock_service.get_processed_count = AsyncMock(return_value=1)
        mock_service.get_all_batches_transmitted = AsyncMock(return_value=(False, None))
        mock_service.append_flagged_result = AsyncMock()

        mock_redis = AsyncMock()
        mock_redis.connect = AsyncMock()
        mock_redis.disconnect = AsyncMock()
        mock_redis.client = MagicMock()

        mock_engine_instance = MagicMock()
        mock_engine_instance.dispose = AsyncMock()

        settings = MagicMock()
        settings.DB_POOL_SIZE = 5
        settings.DB_POOL_MAX_OVERFLOW = 10
        settings.DB_POOL_TIMEOUT = 30
        settings.DB_POOL_RECYCLE = 1800

        with (
            patch("src.tasks.content_monitoring_tasks.create_async_engine") as mock_engine,
            patch(
                "src.tasks.content_monitoring_tasks.async_sessionmaker",
                return_value=mock_session_maker,
            ),
            patch("src.cache.redis_client.RedisClient", return_value=mock_redis),
            patch(
                "src.bulk_content_scan.service.BulkContentScanService",
                return_value=mock_service,
            ),
            patch("src.fact_checking.embedding_service.EmbeddingService"),
            patch("src.tasks.content_monitoring_tasks._get_llm_service"),
            patch("src.config.get_settings", return_value=settings),
        ):
            mock_engine.return_value = mock_engine_instance

            from src.tasks.content_monitoring_tasks import process_bulk_scan_batch_task

            await process_bulk_scan_batch_task(
                scan_id=str(uuid4()),
                community_server_id=str(uuid4()),
                batch_number=1,
                messages=[],
                db_url="postgresql+asyncpg://test:test@localhost/test",
                redis_url="redis://localhost:6379",
            )

            mock_redis.disconnect.assert_called_once()
            mock_engine_instance.dispose.assert_called_once()
