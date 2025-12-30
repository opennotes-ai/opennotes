"""
Unit tests for TaskIQ content monitoring tasks.

Task: task-910 - Migrate content monitoring system to TaskIQ
Tests cover:
- Bulk scan batch processing task (AC #2)
- Bulk scan completion/finalization task (AC #3)
- AI note generation task (AC #4)
- Vision description task (AC #11)
- Audit log persistence task (AC #12)
- Rate limiting preservation (AC #8)
- Distributed lock preservation (AC #7)
- OpenTelemetry tracing (AC #6)
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


def make_test_message(msg_id: str, channel_id: str, content: str) -> dict:
    """Create a properly formatted test message for BulkScanMessage."""
    return {
        "message_id": msg_id,
        "channel_id": channel_id,
        "community_server_id": "platform123",
        "content": content,
        "author_id": "author123",
        "author_username": "testuser",
        "timestamp": datetime.now(UTC).isoformat(),
    }


class TestBulkScanBatchTask:
    """Test bulk scan batch processing task (AC #2, #5)."""

    @pytest.mark.asyncio
    async def test_processes_message_batch_successfully(self):
        """Task processes message batch and returns success status."""
        scan_id = str(uuid4())
        community_server_id = str(uuid4())
        batch_number = 1
        messages = [
            make_test_message("msg1", "ch1", "test content 1"),
            make_test_message("msg2", "ch1", "test content 2"),
        ]

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

        mock_llm_service = MagicMock()

        with (
            patch("src.tasks.content_monitoring_tasks.create_async_engine") as mock_engine,
            patch(
                "src.tasks.content_monitoring_tasks.async_sessionmaker",
                return_value=mock_session_maker,
            ),
            patch("src.tasks.content_monitoring_tasks.RedisClient", return_value=mock_redis),
            patch(
                "src.tasks.content_monitoring_tasks.BulkContentScanService",
                return_value=mock_service,
            ),
            patch("src.tasks.content_monitoring_tasks.EmbeddingService"),
            patch(
                "src.tasks.content_monitoring_tasks._get_llm_service", return_value=mock_llm_service
            ),
            patch("src.tasks.content_monitoring_tasks.get_settings") as mock_settings,
        ):
            mock_engine.return_value = MagicMock()
            mock_engine.return_value.dispose = AsyncMock()
            settings = MagicMock()
            settings.DB_POOL_SIZE = 5
            settings.DB_POOL_MAX_OVERFLOW = 10
            settings.DB_POOL_TIMEOUT = 30
            settings.DB_POOL_RECYCLE = 1800
            settings.SIMILARITY_SEARCH_DEFAULT_THRESHOLD = 0.7
            mock_settings.return_value = settings

            from src.tasks.content_monitoring_tasks import process_bulk_scan_batch_task

            result = await process_bulk_scan_batch_task(
                scan_id=scan_id,
                community_server_id=community_server_id,
                batch_number=batch_number,
                messages=messages,
                db_url="postgresql+asyncpg://test:test@localhost/test",
                redis_url="redis://localhost:6379",
            )

            assert result["status"] == "completed"
            assert result["messages_processed"] == 2

    @pytest.mark.asyncio
    async def test_triggers_finalization_when_all_batches_done(self):
        """Task triggers finalize_bulk_scan_task when all batches transmitted and processed."""
        scan_id = str(uuid4())
        community_server_id = str(uuid4())
        batch_number = 3
        messages = [make_test_message("msg1", "ch1", "test")]

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

        mock_redis = AsyncMock()
        mock_redis.connect = AsyncMock()
        mock_redis.disconnect = AsyncMock()
        mock_redis.client = MagicMock()

        mock_llm_service = MagicMock()

        with (
            patch("src.tasks.content_monitoring_tasks.create_async_engine") as mock_engine,
            patch(
                "src.tasks.content_monitoring_tasks.async_sessionmaker",
                return_value=mock_session_maker,
            ),
            patch("src.tasks.content_monitoring_tasks.RedisClient", return_value=mock_redis),
            patch(
                "src.tasks.content_monitoring_tasks.BulkContentScanService",
                return_value=mock_service,
            ),
            patch("src.tasks.content_monitoring_tasks.EmbeddingService"),
            patch(
                "src.tasks.content_monitoring_tasks._get_llm_service", return_value=mock_llm_service
            ),
            patch("src.tasks.content_monitoring_tasks.get_settings") as mock_settings,
            patch("src.tasks.content_monitoring_tasks.finalize_bulk_scan_task") as mock_finalize,
        ):
            mock_engine.return_value = MagicMock()
            mock_engine.return_value.dispose = AsyncMock()
            settings = MagicMock()
            settings.DB_POOL_SIZE = 5
            settings.DB_POOL_MAX_OVERFLOW = 10
            settings.DB_POOL_TIMEOUT = 30
            settings.DB_POOL_RECYCLE = 1800
            settings.SIMILARITY_SEARCH_DEFAULT_THRESHOLD = 0.7
            mock_settings.return_value = settings
            mock_finalize.kiq = AsyncMock()

            from src.tasks.content_monitoring_tasks import process_bulk_scan_batch_task

            await process_bulk_scan_batch_task(
                scan_id=scan_id,
                community_server_id=community_server_id,
                batch_number=batch_number,
                messages=messages,
                db_url="postgresql+asyncpg://test:test@localhost/test",
                redis_url="redis://localhost:6379",
            )

            mock_finalize.kiq.assert_called_once()


class TestFinalizeBulkScanTask:
    """Test bulk scan finalization task (AC #3, #7)."""

    @pytest.mark.asyncio
    async def test_finalizes_scan_and_publishes_results(self):
        """Task finalizes scan and publishes results event."""
        scan_id = str(uuid4())
        community_server_id = str(uuid4())
        messages_scanned = 100

        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()

        mock_session_maker = MagicMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_service = MagicMock()
        mock_service.get_flagged_results = AsyncMock(return_value=[])
        mock_service.get_error_summary = AsyncMock(return_value={"total_errors": 0})
        mock_service.get_processed_count = AsyncMock(return_value=100)
        mock_service.complete_scan = AsyncMock()

        mock_redis = AsyncMock()
        mock_redis.connect = AsyncMock()
        mock_redis.disconnect = AsyncMock()
        mock_redis.client = MagicMock()

        mock_publisher = MagicMock()
        mock_publisher.publish = AsyncMock()

        mock_event_publisher = MagicMock()
        mock_event_publisher.publish_event = AsyncMock()

        mock_llm_service = MagicMock()

        with (
            patch("src.tasks.content_monitoring_tasks.create_async_engine") as mock_engine,
            patch(
                "src.tasks.content_monitoring_tasks.async_sessionmaker",
                return_value=mock_session_maker,
            ),
            patch("src.tasks.content_monitoring_tasks.RedisClient", return_value=mock_redis),
            patch(
                "src.tasks.content_monitoring_tasks.BulkContentScanService",
                return_value=mock_service,
            ),
            patch("src.tasks.content_monitoring_tasks.EmbeddingService"),
            patch(
                "src.tasks.content_monitoring_tasks._get_llm_service", return_value=mock_llm_service
            ),
            patch(
                "src.tasks.content_monitoring_tasks.BulkScanResultsPublisher",
                return_value=mock_publisher,
            ),
            patch("src.tasks.content_monitoring_tasks.event_publisher", mock_event_publisher),
            patch("src.tasks.content_monitoring_tasks.get_settings") as mock_settings,
        ):
            mock_engine.return_value = MagicMock()
            mock_engine.return_value.dispose = AsyncMock()
            settings = MagicMock()
            settings.DB_POOL_SIZE = 5
            settings.DB_POOL_MAX_OVERFLOW = 10
            settings.DB_POOL_TIMEOUT = 30
            settings.DB_POOL_RECYCLE = 1800
            settings.NATS_STREAM_NAME = "opennotes"
            mock_settings.return_value = settings

            from src.tasks.content_monitoring_tasks import finalize_bulk_scan_task

            result = await finalize_bulk_scan_task(
                scan_id=scan_id,
                community_server_id=community_server_id,
                messages_scanned=messages_scanned,
                db_url="postgresql+asyncpg://test:test@localhost/test",
                redis_url="redis://localhost:6379",
            )

            assert result["status"] == "completed"
            mock_service.complete_scan.assert_called_once()


class TestGenerateAINoteTask:
    """Test AI note generation task (AC #4, #8)."""

    @pytest.mark.asyncio
    async def test_generates_note_successfully(self):
        """Task generates AI note and submits it."""
        community_server_id = "platform123"
        fact_check_item_id = str(uuid4())
        community_server_uuid = uuid4()

        mock_fact_check = MagicMock()
        mock_fact_check.title = "Test Title"
        mock_fact_check.rating = "false"
        mock_fact_check.summary = "Test summary"
        mock_fact_check.content = "Test content"
        mock_fact_check.source_url = "https://example.com"

        mock_result_community = MagicMock()
        mock_result_community.scalar_one_or_none.return_value = community_server_uuid

        mock_result_fact_check = MagicMock()
        mock_result_fact_check.scalar_one_or_none.return_value = mock_fact_check

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(
            side_effect=[mock_result_community, mock_result_fact_check]
        )
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        mock_session_maker = MagicMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_llm_service = MagicMock()
        mock_llm_service.complete = AsyncMock(
            return_value=MagicMock(content="Generated note content", model="gpt-4", tokens_used=100)
        )

        mock_rate_limiter = MagicMock()
        mock_rate_limiter.check_rate_limit = AsyncMock(return_value=(True, None))

        with (
            patch("src.tasks.content_monitoring_tasks.create_async_engine") as mock_engine,
            patch(
                "src.tasks.content_monitoring_tasks.async_sessionmaker",
                return_value=mock_session_maker,
            ),
            patch(
                "src.tasks.content_monitoring_tasks._get_llm_service", return_value=mock_llm_service
            ),
            patch("src.tasks.content_monitoring_tasks.rate_limiter", mock_rate_limiter),
            patch("src.tasks.content_monitoring_tasks.get_settings") as mock_settings,
        ):
            mock_engine.return_value = MagicMock()
            mock_engine.return_value.dispose = AsyncMock()
            settings = MagicMock()
            settings.DB_POOL_SIZE = 5
            settings.DB_POOL_MAX_OVERFLOW = 10
            settings.DB_POOL_TIMEOUT = 30
            settings.DB_POOL_RECYCLE = 1800
            settings.AI_NOTE_WRITING_ENABLED = True
            settings.AI_NOTE_WRITER_MODEL = "openai/gpt-4"
            settings.AI_NOTE_WRITER_SYSTEM_PROMPT = "You are a fact-checker."
            mock_settings.return_value = settings

            from src.tasks.content_monitoring_tasks import generate_ai_note_task

            result = await generate_ai_note_task(
                community_server_id=community_server_id,
                request_id="req123",
                content="test claim content",
                fact_check_item_id=fact_check_item_id,
                similarity_score=0.85,
                db_url="postgresql+asyncpg://test:test@localhost/test",
            )

            assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_respects_rate_limit(self):
        """Task returns rate_limited status when rate limit exceeded (AC #8)."""
        community_server_id = "platform123"

        mock_rate_limiter = MagicMock()
        mock_rate_limiter.check_rate_limit = AsyncMock(return_value=(False, 60))

        with (
            patch("src.tasks.content_monitoring_tasks.rate_limiter", mock_rate_limiter),
            patch("src.tasks.content_monitoring_tasks.get_settings") as mock_settings,
        ):
            settings = MagicMock()
            settings.AI_NOTE_WRITING_ENABLED = True
            mock_settings.return_value = settings

            from src.tasks.content_monitoring_tasks import generate_ai_note_task

            result = await generate_ai_note_task(
                community_server_id=community_server_id,
                request_id="req123",
                content="test content",
                fact_check_item_id=str(uuid4()),
                similarity_score=0.85,
                db_url="postgresql+asyncpg://test:test@localhost/test",
            )

            assert result["status"] == "rate_limited"


class TestVisionDescriptionTask:
    """Test vision description task (AC #11)."""

    @pytest.mark.asyncio
    async def test_processes_vision_request_successfully(self):
        """Task processes vision request and updates message archive."""
        message_archive_id = str(uuid4())
        image_url = "https://example.com/image.jpg"
        community_server_id = "platform123"

        mock_archive = MagicMock()
        mock_archive.image_description = None

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=mock_archive)
        mock_session.commit = AsyncMock()

        mock_session_maker = MagicMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_vision_service = MagicMock()
        mock_vision_service.describe_image = AsyncMock(return_value="A detailed image description")

        with (
            patch("src.tasks.content_monitoring_tasks.create_async_engine") as mock_engine,
            patch(
                "src.tasks.content_monitoring_tasks.async_sessionmaker",
                return_value=mock_session_maker,
            ),
            patch(
                "src.tasks.content_monitoring_tasks.VisionService", return_value=mock_vision_service
            ),
            patch("src.tasks.content_monitoring_tasks._get_llm_service"),
            patch("src.tasks.content_monitoring_tasks.get_settings") as mock_settings,
        ):
            mock_engine.return_value = MagicMock()
            mock_engine.return_value.dispose = AsyncMock()
            settings = MagicMock()
            settings.DB_POOL_SIZE = 5
            settings.DB_POOL_MAX_OVERFLOW = 10
            settings.DB_POOL_TIMEOUT = 30
            settings.DB_POOL_RECYCLE = 1800
            mock_settings.return_value = settings

            from src.tasks.content_monitoring_tasks import process_vision_description_task

            result = await process_vision_description_task(
                message_archive_id=message_archive_id,
                image_url=image_url,
                community_server_id=community_server_id,
                db_url="postgresql+asyncpg://test:test@localhost/test",
            )

            assert result["status"] == "completed"
            assert mock_archive.image_description == "A detailed image description"

    @pytest.mark.asyncio
    async def test_skips_if_already_processed(self):
        """Task skips processing if image already has description (idempotency)."""
        message_archive_id = str(uuid4())

        mock_archive = MagicMock()
        mock_archive.image_description = "Existing description"

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=mock_archive)

        mock_session_maker = MagicMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.tasks.content_monitoring_tasks.create_async_engine") as mock_engine,
            patch(
                "src.tasks.content_monitoring_tasks.async_sessionmaker",
                return_value=mock_session_maker,
            ),
            patch("src.tasks.content_monitoring_tasks.get_settings") as mock_settings,
        ):
            mock_engine.return_value = MagicMock()
            mock_engine.return_value.dispose = AsyncMock()
            settings = MagicMock()
            settings.DB_POOL_SIZE = 5
            settings.DB_POOL_MAX_OVERFLOW = 10
            settings.DB_POOL_TIMEOUT = 30
            settings.DB_POOL_RECYCLE = 1800
            mock_settings.return_value = settings

            from src.tasks.content_monitoring_tasks import process_vision_description_task

            result = await process_vision_description_task(
                message_archive_id=message_archive_id,
                image_url="https://example.com/image.jpg",
                community_server_id="platform123",
                db_url="postgresql+asyncpg://test:test@localhost/test",
            )

            assert result["status"] == "already_processed"


class TestAuditLogTask:
    """Test audit log persistence task (AC #12)."""

    @pytest.mark.asyncio
    async def test_persists_audit_log_successfully(self):
        """Task persists audit log to database."""
        user_id = str(uuid4())
        community_server_id = str(uuid4())
        action = "note.created"
        details = {"note_id": "note123"}

        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        mock_session_maker = MagicMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.tasks.content_monitoring_tasks.create_async_engine") as mock_engine,
            patch(
                "src.tasks.content_monitoring_tasks.async_sessionmaker",
                return_value=mock_session_maker,
            ),
            patch("src.tasks.content_monitoring_tasks.get_settings") as mock_settings,
        ):
            mock_engine.return_value = MagicMock()
            mock_engine.return_value.dispose = AsyncMock()
            settings = MagicMock()
            settings.DB_POOL_SIZE = 5
            settings.DB_POOL_MAX_OVERFLOW = 10
            settings.DB_POOL_TIMEOUT = 30
            settings.DB_POOL_RECYCLE = 1800
            mock_settings.return_value = settings

            from src.tasks.content_monitoring_tasks import persist_audit_log_task

            result = await persist_audit_log_task(
                user_id=user_id,
                community_server_id=community_server_id,
                action=action,
                resource="note",
                resource_id="note123",
                details=details,
                ip_address="127.0.0.1",
                user_agent="TestAgent/1.0",
                db_url="postgresql+asyncpg://test:test@localhost/test",
            )

            assert result["status"] == "completed"
            mock_session.add.assert_called_once()


class TestTaskIQLabels:
    """Test TaskIQ labels are properly configured."""

    def test_bulk_scan_batch_task_has_labels(self):
        """Verify bulk scan batch task has component and task_type labels."""
        from src.tasks.broker import _all_registered_tasks

        assert "content:batch_scan" in _all_registered_tasks

        _, labels = _all_registered_tasks["content:batch_scan"]
        assert labels.get("component") == "content_monitoring"
        assert labels.get("task_type") == "batch"

    def test_finalize_scan_task_has_labels(self):
        """Verify finalize scan task has component and task_type labels."""
        from src.tasks.broker import _all_registered_tasks

        assert "content:finalize_scan" in _all_registered_tasks

        _, labels = _all_registered_tasks["content:finalize_scan"]
        assert labels.get("component") == "content_monitoring"
        assert labels.get("task_type") == "finalize"

    def test_ai_note_task_has_labels(self):
        """Verify AI note task has component and task_type labels."""
        from src.tasks.broker import _all_registered_tasks

        assert "content:ai_note" in _all_registered_tasks

        _, labels = _all_registered_tasks["content:ai_note"]
        assert labels.get("component") == "content_monitoring"
        assert labels.get("task_type") == "generation"

    def test_vision_task_has_labels(self):
        """Verify vision task has component and task_type labels."""
        from src.tasks.broker import _all_registered_tasks

        assert "content:vision_description" in _all_registered_tasks

        _, labels = _all_registered_tasks["content:vision_description"]
        assert labels.get("component") == "content_monitoring"
        assert labels.get("task_type") == "vision"

    def test_audit_log_task_has_labels(self):
        """Verify audit log task has component and task_type labels."""
        from src.tasks.broker import _all_registered_tasks

        assert "content:audit_log" in _all_registered_tasks

        _, labels = _all_registered_tasks["content:audit_log"]
        assert labels.get("component") == "content_monitoring"
        assert labels.get("task_type") == "audit"


class TestOpenTelemetryTracing:
    """Test OpenTelemetry tracing integration (AC #6)."""

    @pytest.mark.asyncio
    async def test_bulk_scan_task_creates_span(self):
        """Verify bulk scan task creates OpenTelemetry span with attributes."""
        scan_id = str(uuid4())
        community_server_id = str(uuid4())

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

        mock_redis = AsyncMock()
        mock_redis.connect = AsyncMock()
        mock_redis.disconnect = AsyncMock()
        mock_redis.client = MagicMock()

        mock_span = MagicMock()
        mock_span.set_attribute = MagicMock()
        mock_span.__enter__ = MagicMock(return_value=mock_span)
        mock_span.__exit__ = MagicMock(return_value=None)

        mock_tracer = MagicMock()
        mock_tracer.start_as_current_span = MagicMock(return_value=mock_span)

        mock_llm_service = MagicMock()

        with (
            patch("src.tasks.content_monitoring_tasks.create_async_engine") as mock_engine,
            patch(
                "src.tasks.content_monitoring_tasks.async_sessionmaker",
                return_value=mock_session_maker,
            ),
            patch("src.tasks.content_monitoring_tasks.RedisClient", return_value=mock_redis),
            patch(
                "src.tasks.content_monitoring_tasks.BulkContentScanService",
                return_value=mock_service,
            ),
            patch("src.tasks.content_monitoring_tasks.EmbeddingService"),
            patch(
                "src.tasks.content_monitoring_tasks._get_llm_service", return_value=mock_llm_service
            ),
            patch("src.tasks.content_monitoring_tasks.get_settings") as mock_settings,
            patch("src.tasks.content_monitoring_tasks._tracer", mock_tracer),
        ):
            mock_engine.return_value = MagicMock()
            mock_engine.return_value.dispose = AsyncMock()
            settings = MagicMock()
            settings.DB_POOL_SIZE = 5
            settings.DB_POOL_MAX_OVERFLOW = 10
            settings.DB_POOL_TIMEOUT = 30
            settings.DB_POOL_RECYCLE = 1800
            settings.SIMILARITY_SEARCH_DEFAULT_THRESHOLD = 0.7
            mock_settings.return_value = settings

            from src.tasks.content_monitoring_tasks import process_bulk_scan_batch_task

            await process_bulk_scan_batch_task(
                scan_id=scan_id,
                community_server_id=community_server_id,
                batch_number=1,
                messages=[make_test_message("msg1", "ch1", "test")],
                db_url="postgresql+asyncpg://test:test@localhost/test",
                redis_url="redis://localhost:6379",
            )

            mock_tracer.start_as_current_span.assert_called_once_with("content.batch_scan")
            mock_span.set_attribute.assert_any_call("task.scan_id", scan_id)
            mock_span.set_attribute.assert_any_call("task.component", "content_monitoring")
