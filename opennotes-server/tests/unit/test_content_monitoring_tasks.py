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

Note: Because tasks use lazy imports to avoid import-time settings validation,
patches must target the SOURCE modules (where classes are defined) rather than
the task module itself.
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

        settings = MagicMock()
        settings.DB_POOL_SIZE = 5
        settings.DB_POOL_MAX_OVERFLOW = 10
        settings.DB_POOL_TIMEOUT = 30
        settings.DB_POOL_RECYCLE = 1800
        settings.SIMILARITY_SEARCH_DEFAULT_THRESHOLD = 0.7

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
            patch(
                "src.tasks.content_monitoring_tasks._get_llm_service", return_value=mock_llm_service
            ),
            patch("src.config.get_settings", return_value=settings),
        ):
            mock_engine.return_value = MagicMock()
            mock_engine.return_value.dispose = AsyncMock()

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
        mock_service.try_set_finalize_dispatched = AsyncMock(return_value=True)

        mock_redis = AsyncMock()
        mock_redis.connect = AsyncMock()
        mock_redis.disconnect = AsyncMock()
        mock_redis.client = MagicMock()

        mock_llm_service = MagicMock()

        settings = MagicMock()
        settings.DB_POOL_SIZE = 5
        settings.DB_POOL_MAX_OVERFLOW = 10
        settings.DB_POOL_TIMEOUT = 30
        settings.DB_POOL_RECYCLE = 1800
        settings.SIMILARITY_SEARCH_DEFAULT_THRESHOLD = 0.7

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
            patch(
                "src.tasks.content_monitoring_tasks._get_llm_service", return_value=mock_llm_service
            ),
            patch("src.config.get_settings", return_value=settings),
            patch("src.tasks.content_monitoring_tasks.finalize_bulk_scan_task") as mock_finalize,
        ):
            mock_engine.return_value = MagicMock()
            mock_engine.return_value.dispose = AsyncMock()
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

            mock_service.try_set_finalize_dispatched.assert_called_once()
            mock_finalize.kiq.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_finalization_when_already_dispatched(self):
        """Task skips finalization dispatch when idempotency flag already set."""
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
        mock_service.try_set_finalize_dispatched = AsyncMock(return_value=False)

        mock_redis = AsyncMock()
        mock_redis.connect = AsyncMock()
        mock_redis.disconnect = AsyncMock()
        mock_redis.client = MagicMock()

        mock_llm_service = MagicMock()

        settings = MagicMock()
        settings.DB_POOL_SIZE = 5
        settings.DB_POOL_MAX_OVERFLOW = 10
        settings.DB_POOL_TIMEOUT = 30
        settings.DB_POOL_RECYCLE = 1800
        settings.SIMILARITY_SEARCH_DEFAULT_THRESHOLD = 0.7

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
            patch(
                "src.tasks.content_monitoring_tasks._get_llm_service", return_value=mock_llm_service
            ),
            patch("src.config.get_settings", return_value=settings),
            patch("src.tasks.content_monitoring_tasks.finalize_bulk_scan_task") as mock_finalize,
        ):
            mock_engine.return_value = MagicMock()
            mock_engine.return_value.dispose = AsyncMock()
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

            mock_service.try_set_finalize_dispatched.assert_called_once()
            mock_finalize.kiq.assert_not_called()


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

        settings = MagicMock()
        settings.DB_POOL_SIZE = 5
        settings.DB_POOL_MAX_OVERFLOW = 10
        settings.DB_POOL_TIMEOUT = 30
        settings.DB_POOL_RECYCLE = 1800
        settings.NATS_STREAM_NAME = "opennotes"

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
            patch(
                "src.tasks.content_monitoring_tasks._get_llm_service", return_value=mock_llm_service
            ),
            patch(
                "src.bulk_content_scan.nats_handler.BulkScanResultsPublisher",
                return_value=mock_publisher,
            ),
            patch("src.events.publisher.event_publisher", mock_event_publisher),
            patch("src.config.get_settings", return_value=settings),
        ):
            mock_engine.return_value = MagicMock()
            mock_engine.return_value.dispose = AsyncMock()

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

        settings = MagicMock()
        settings.DB_POOL_SIZE = 5
        settings.DB_POOL_MAX_OVERFLOW = 10
        settings.DB_POOL_TIMEOUT = 30
        settings.DB_POOL_RECYCLE = 1800
        settings.AI_NOTE_WRITING_ENABLED = True
        settings.AI_NOTE_WRITER_MODEL = "openai/gpt-4"
        settings.AI_NOTE_WRITER_SYSTEM_PROMPT = "You are a fact-checker."

        with (
            patch("src.tasks.content_monitoring_tasks.create_async_engine") as mock_engine,
            patch(
                "src.tasks.content_monitoring_tasks.async_sessionmaker",
                return_value=mock_session_maker,
            ),
            patch(
                "src.tasks.content_monitoring_tasks._get_llm_service", return_value=mock_llm_service
            ),
            patch("src.webhooks.rate_limit.rate_limiter", mock_rate_limiter),
            patch("src.config.get_settings", return_value=settings),
        ):
            mock_engine.return_value = MagicMock()
            mock_engine.return_value.dispose = AsyncMock()

            from src.tasks.content_monitoring_tasks import generate_ai_note_task

            result = await generate_ai_note_task(
                community_server_id=community_server_id,
                request_id="req123",
                content="test claim content",
                scan_type="similarity",
                db_url="postgresql+asyncpg://test:test@localhost/test",
                fact_check_item_id=fact_check_item_id,
                similarity_score=0.85,
            )

            assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_respects_rate_limit(self):
        """Task returns rate_limited status when rate limit exceeded (AC #8)."""
        community_server_id = "platform123"

        mock_rate_limiter = MagicMock()
        mock_rate_limiter.check_rate_limit = AsyncMock(return_value=(False, 60))

        settings = MagicMock()
        settings.AI_NOTE_WRITING_ENABLED = True

        with (
            patch("src.webhooks.rate_limit.rate_limiter", mock_rate_limiter),
            patch("src.config.get_settings", return_value=settings),
        ):
            from src.tasks.content_monitoring_tasks import generate_ai_note_task

            result = await generate_ai_note_task(
                community_server_id=community_server_id,
                request_id="req123",
                content="test content",
                scan_type="similarity",
                db_url="postgresql+asyncpg://test:test@localhost/test",
                fact_check_item_id=str(uuid4()),
                similarity_score=0.85,
            )

            assert result["status"] == "rate_limited"

    @pytest.mark.asyncio
    async def test_moderation_scan_passes_metadata_to_prompt(self):
        """Task passes moderation_metadata to prompt for openai_moderation scans (task-941.01)."""
        community_server_id = "platform123"
        community_server_uuid = uuid4()
        moderation_metadata = {
            "categories": {"harassment": True, "violence": False},
            "scores": {"harassment": 0.92, "violence": 0.1},
            "flagged_categories": ["harassment"],
        }

        mock_result_community = MagicMock()
        mock_result_community.scalar_one_or_none.return_value = community_server_uuid

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result_community)
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

        settings = MagicMock()
        settings.DB_POOL_SIZE = 5
        settings.DB_POOL_MAX_OVERFLOW = 10
        settings.DB_POOL_TIMEOUT = 30
        settings.DB_POOL_RECYCLE = 1800
        settings.AI_NOTE_WRITING_ENABLED = True
        settings.AI_NOTE_WRITER_MODEL = "openai/gpt-4"
        settings.AI_NOTE_WRITER_SYSTEM_PROMPT = "You are a fact-checker."

        with (
            patch("src.tasks.content_monitoring_tasks.create_async_engine") as mock_engine,
            patch(
                "src.tasks.content_monitoring_tasks.async_sessionmaker",
                return_value=mock_session_maker,
            ),
            patch(
                "src.tasks.content_monitoring_tasks._get_llm_service", return_value=mock_llm_service
            ),
            patch("src.webhooks.rate_limit.rate_limiter", mock_rate_limiter),
            patch("src.config.get_settings", return_value=settings),
        ):
            mock_engine.return_value = MagicMock()
            mock_engine.return_value.dispose = AsyncMock()

            from src.tasks.content_monitoring_tasks import generate_ai_note_task

            result = await generate_ai_note_task(
                community_server_id=community_server_id,
                request_id="req123",
                content="test content flagged by moderation",
                scan_type="openai_moderation",
                db_url="postgresql+asyncpg://test:test@localhost/test",
                moderation_metadata=moderation_metadata,
            )

            assert result["status"] == "completed"

            call_args = mock_llm_service.complete.call_args
            messages = call_args.kwargs["messages"]
            user_message = messages[1].content

            assert "harassment" in user_message.lower()
            assert "Content Moderation Analysis" in user_message


class TestBuildGeneralExplanationPrompt:
    """Tests for _build_general_explanation_prompt function (task-941.01)."""

    def test_prompt_without_moderation_metadata(self):
        """Prompt should work without moderation metadata."""
        from src.tasks.content_monitoring_tasks import _build_general_explanation_prompt

        prompt = _build_general_explanation_prompt("Test message content")

        assert "Test message content" in prompt
        assert "Content Moderation Analysis" not in prompt

    def test_prompt_includes_moderation_metadata(self):
        """Prompt should include moderation context when metadata is provided."""
        from src.tasks.content_monitoring_tasks import _build_general_explanation_prompt

        moderation_metadata = {
            "categories": {"harassment": True, "violence": False, "hate": True},
            "scores": {"harassment": 0.92, "violence": 0.1, "hate": 0.75},
            "flagged_categories": ["harassment", "hate"],
        }

        prompt = _build_general_explanation_prompt("Test message", moderation_metadata)

        assert "Test message" in prompt
        assert "Content Moderation Analysis" in prompt
        assert "harassment" in prompt
        assert "hate" in prompt
        assert "92.00%" in prompt
        assert "75.00%" in prompt

    def test_prompt_with_empty_flagged_categories(self):
        """Prompt should handle empty flagged_categories gracefully."""
        from src.tasks.content_monitoring_tasks import _build_general_explanation_prompt

        moderation_metadata = {
            "categories": {},
            "scores": {},
            "flagged_categories": [],
        }

        prompt = _build_general_explanation_prompt("Test message", moderation_metadata)

        assert "Test message" in prompt
        assert "Content Moderation Analysis" in prompt
        assert "Flagged Categories" not in prompt


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
            patch("src.services.vision_service.VisionService", return_value=mock_vision_service),
            patch("src.tasks.content_monitoring_tasks._get_llm_service"),
            patch("src.config.get_settings", return_value=settings),
        ):
            mock_engine.return_value = MagicMock()
            mock_engine.return_value.dispose = AsyncMock()

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
            patch("src.config.get_settings", return_value=settings),
        ):
            mock_engine.return_value = MagicMock()
            mock_engine.return_value.dispose = AsyncMock()

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
        mock_session.refresh = AsyncMock()

        mock_session_maker = MagicMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

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
            patch("src.config.get_settings", return_value=settings),
        ):
            mock_engine.return_value = MagicMock()
            mock_engine.return_value.dispose = AsyncMock()

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

    @pytest.mark.asyncio
    async def test_details_field_serialized_to_json_string(self):
        """Task serializes details dict to JSON string for Text column (task-910.04).

        The AuditLog.details column is Text (string), so the task must call
        json.dumps() on the dict before storing. This test verifies the
        serialization is correct and can be parsed back.
        """
        import json

        user_id = str(uuid4())
        details = {"note_id": "note123", "nested": {"key": "value"}, "count": 42}

        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        mock_session_maker = MagicMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

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
            patch("src.config.get_settings", return_value=settings),
        ):
            mock_engine.return_value = MagicMock()
            mock_engine.return_value.dispose = AsyncMock()

            from src.tasks.content_monitoring_tasks import persist_audit_log_task

            await persist_audit_log_task(
                user_id=user_id,
                community_server_id=None,
                action="test.action",
                resource="test",
                resource_id="test123",
                details=details,
                ip_address="127.0.0.1",
                user_agent="TestAgent/1.0",
                db_url="postgresql+asyncpg://test:test@localhost/test",
            )

            added_audit_log = mock_session.add.call_args[0][0]
            assert isinstance(added_audit_log.details, str), "details must be JSON string, not dict"
            parsed_details = json.loads(added_audit_log.details)
            assert parsed_details == details, "JSON string must round-trip to original dict"

    @pytest.mark.asyncio
    async def test_details_field_none_when_not_provided(self):
        """Task stores None for details when not provided (task-910.04)."""
        user_id = str(uuid4())

        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        mock_session_maker = MagicMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

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
            patch("src.config.get_settings", return_value=settings),
        ):
            mock_engine.return_value = MagicMock()
            mock_engine.return_value.dispose = AsyncMock()

            from src.tasks.content_monitoring_tasks import persist_audit_log_task

            await persist_audit_log_task(
                user_id=user_id,
                community_server_id=None,
                action="test.action",
                resource="test",
                resource_id="test123",
                details=None,
                ip_address="127.0.0.1",
                user_agent="TestAgent/1.0",
                db_url="postgresql+asyncpg://test:test@localhost/test",
            )

            added_audit_log = mock_session.add.call_args[0][0]
            assert added_audit_log.details is None, "details must be None when not provided"


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


class TestErrorPaths:
    """Test error handling paths for content monitoring tasks."""

    @pytest.mark.asyncio
    async def test_batch_task_missing_platform_id_returns_error(self):
        """Task returns error status when platform_id not found for community server."""
        scan_id = str(uuid4())
        community_server_id = str(uuid4())

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: None))

        mock_session_maker = MagicMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

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
            patch("src.config.get_settings", return_value=settings),
        ):
            mock_engine.return_value = MagicMock()
            mock_engine.return_value.dispose = AsyncMock()

            from src.tasks.content_monitoring_tasks import process_bulk_scan_batch_task

            result = await process_bulk_scan_batch_task(
                scan_id=scan_id,
                community_server_id=community_server_id,
                batch_number=1,
                messages=[make_test_message("msg1", "ch1", "test")],
                db_url="postgresql+asyncpg://test:test@localhost/test",
                redis_url="redis://localhost:6379",
            )

            assert result["status"] == "error"
            assert "Platform ID not found" in result["error"]
            mock_redis.disconnect.assert_called_once()
            mock_engine.return_value.dispose.assert_called_once()

    @pytest.mark.asyncio
    async def test_ai_note_task_missing_community_server_returns_error(self):
        """Task returns error status when community server not found."""
        community_server_id = "nonexistent_platform_id"
        fact_check_item_id = str(uuid4())

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_session_maker = MagicMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_rate_limiter = MagicMock()
        mock_rate_limiter.check_rate_limit = AsyncMock(return_value=(True, None))

        settings = MagicMock()
        settings.DB_POOL_SIZE = 5
        settings.DB_POOL_MAX_OVERFLOW = 10
        settings.DB_POOL_TIMEOUT = 30
        settings.DB_POOL_RECYCLE = 1800
        settings.AI_NOTE_WRITING_ENABLED = True

        with (
            patch("src.tasks.content_monitoring_tasks.create_async_engine") as mock_engine,
            patch(
                "src.tasks.content_monitoring_tasks.async_sessionmaker",
                return_value=mock_session_maker,
            ),
            patch("src.webhooks.rate_limit.rate_limiter", mock_rate_limiter),
            patch("src.config.get_settings", return_value=settings),
        ):
            mock_engine.return_value = MagicMock()
            mock_engine.return_value.dispose = AsyncMock()

            from src.tasks.content_monitoring_tasks import generate_ai_note_task

            result = await generate_ai_note_task(
                community_server_id=community_server_id,
                request_id="req123",
                content="test content",
                scan_type="similarity",
                db_url="postgresql+asyncpg://test:test@localhost/test",
                fact_check_item_id=fact_check_item_id,
                similarity_score=0.85,
            )

            assert result["status"] == "error"
            assert "Community server not found" in result["error"]

    @pytest.mark.asyncio
    async def test_ai_note_task_missing_fact_check_item_returns_error(self):
        """Task returns error status when fact-check item not found."""
        community_server_id = "platform123"
        fact_check_item_id = str(uuid4())
        community_server_uuid = uuid4()

        mock_result_community = MagicMock()
        mock_result_community.scalar_one_or_none.return_value = community_server_uuid

        mock_result_fact_check = MagicMock()
        mock_result_fact_check.scalar_one_or_none.return_value = None

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(
            side_effect=[mock_result_community, mock_result_fact_check]
        )

        mock_session_maker = MagicMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_rate_limiter = MagicMock()
        mock_rate_limiter.check_rate_limit = AsyncMock(return_value=(True, None))

        settings = MagicMock()
        settings.DB_POOL_SIZE = 5
        settings.DB_POOL_MAX_OVERFLOW = 10
        settings.DB_POOL_TIMEOUT = 30
        settings.DB_POOL_RECYCLE = 1800
        settings.AI_NOTE_WRITING_ENABLED = True

        mock_llm_service = MagicMock()

        with (
            patch("src.tasks.content_monitoring_tasks.create_async_engine") as mock_engine,
            patch(
                "src.tasks.content_monitoring_tasks.async_sessionmaker",
                return_value=mock_session_maker,
            ),
            patch("src.webhooks.rate_limit.rate_limiter", mock_rate_limiter),
            patch("src.config.get_settings", return_value=settings),
            patch(
                "src.tasks.content_monitoring_tasks._get_llm_service",
                return_value=mock_llm_service,
            ),
        ):
            mock_engine.return_value = MagicMock()
            mock_engine.return_value.dispose = AsyncMock()

            from src.tasks.content_monitoring_tasks import generate_ai_note_task

            result = await generate_ai_note_task(
                community_server_id=community_server_id,
                request_id="req123",
                content="test content",
                scan_type="similarity",
                db_url="postgresql+asyncpg://test:test@localhost/test",
                fact_check_item_id=fact_check_item_id,
                similarity_score=0.85,
            )

            assert result["status"] == "error"
            assert "Fact-check item not found" in result["error"]

    @pytest.mark.asyncio
    async def test_persist_audit_log_task_full_execution(self):
        """Test persist_audit_log_task creates audit log with all fields."""
        user_id = str(uuid4())
        community_server_id = str(uuid4())
        action = "note.created"
        resource = "note"
        resource_id = "note123"
        details = {"note_id": "note123", "author": "user456"}
        ip_address = "192.168.1.1"
        user_agent = "Mozilla/5.0 TestAgent"
        created_at = "2024-01-15T10:30:00+00:00"

        mock_audit_log = MagicMock()
        mock_audit_log.id = uuid4()

        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        mock_session_maker = MagicMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

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
            patch("src.config.get_settings", return_value=settings),
        ):
            mock_engine.return_value = MagicMock()
            mock_engine.return_value.dispose = AsyncMock()

            from src.tasks.content_monitoring_tasks import persist_audit_log_task

            result = await persist_audit_log_task(
                user_id=user_id,
                community_server_id=community_server_id,
                action=action,
                resource=resource,
                resource_id=resource_id,
                details=details,
                ip_address=ip_address,
                user_agent=user_agent,
                db_url="postgresql+asyncpg://test:test@localhost/test",
                created_at=created_at,
            )

            assert result["status"] == "completed"
            assert "audit_log_id" in result
            mock_session.add.assert_called_once()
            mock_session.commit.assert_called_once()

            added_audit_log = mock_session.add.call_args[0][0]
            assert added_audit_log.action == action
            assert added_audit_log.resource == resource
            assert added_audit_log.resource_id == resource_id
            assert added_audit_log.ip_address == ip_address
            assert added_audit_log.user_agent == user_agent

    @pytest.mark.asyncio
    async def test_persist_audit_log_task_with_null_optional_fields(self):
        """Test persist_audit_log_task handles null optional fields correctly."""
        mock_audit_log = MagicMock()
        mock_audit_log.id = uuid4()

        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        mock_session_maker = MagicMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

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
            patch("src.config.get_settings", return_value=settings),
        ):
            mock_engine.return_value = MagicMock()
            mock_engine.return_value.dispose = AsyncMock()

            from src.tasks.content_monitoring_tasks import persist_audit_log_task

            result = await persist_audit_log_task(
                user_id=None,
                community_server_id=None,
                action="system.startup",
                resource="server",
                resource_id=None,
                details=None,
                ip_address=None,
                user_agent=None,
                db_url="postgresql+asyncpg://test:test@localhost/test",
                created_at=None,
            )

            assert result["status"] == "completed"
            mock_session.add.assert_called_once()

            added_audit_log = mock_session.add.call_args[0][0]
            assert added_audit_log.user_id is None
            assert added_audit_log.resource_id is None
            assert added_audit_log.details is None
            assert added_audit_log.ip_address is None
            assert added_audit_log.user_agent is None


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

        settings = MagicMock()
        settings.DB_POOL_SIZE = 5
        settings.DB_POOL_MAX_OVERFLOW = 10
        settings.DB_POOL_TIMEOUT = 30
        settings.DB_POOL_RECYCLE = 1800
        settings.SIMILARITY_SEARCH_DEFAULT_THRESHOLD = 0.7

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
            patch(
                "src.tasks.content_monitoring_tasks._get_llm_service", return_value=mock_llm_service
            ),
            patch("src.config.get_settings", return_value=settings),
            patch("src.tasks.content_monitoring_tasks._tracer", mock_tracer),
        ):
            mock_engine.return_value = MagicMock()
            mock_engine.return_value.dispose = AsyncMock()

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


class TestFinalizeDispatchIdempotency:
    """Test idempotency for finalize dispatch race condition (task-910.05).

    Tests that the Redis SETNX-based idempotency mechanism prevents
    double dispatch of finalize_bulk_scan_task when both handlers
    (batch and transmitted) attempt to trigger it simultaneously.
    """

    @pytest.mark.asyncio
    async def test_try_set_finalize_dispatched_returns_true_on_first_call(self):
        """First call to try_set_finalize_dispatched returns True."""
        from uuid import uuid4

        mock_redis = MagicMock()
        mock_redis.set = AsyncMock(return_value=True)

        from src.bulk_content_scan.service import BulkContentScanService

        service = BulkContentScanService(
            session=MagicMock(),
            embedding_service=MagicMock(),
            redis_client=mock_redis,
        )

        scan_id = uuid4()
        result = await service.try_set_finalize_dispatched(scan_id)

        assert result is True
        mock_redis.set.assert_called_once()
        call_kwargs = mock_redis.set.call_args
        assert call_kwargs.kwargs.get("nx") is True

    @pytest.mark.asyncio
    async def test_try_set_finalize_dispatched_returns_false_on_second_call(self):
        """Second call to try_set_finalize_dispatched returns False."""
        from uuid import uuid4

        mock_redis = MagicMock()
        mock_redis.set = AsyncMock(return_value=None)

        from src.bulk_content_scan.service import BulkContentScanService

        service = BulkContentScanService(
            session=MagicMock(),
            embedding_service=MagicMock(),
            redis_client=mock_redis,
        )

        scan_id = uuid4()
        result = await service.try_set_finalize_dispatched(scan_id)

        assert result is False

    @pytest.mark.asyncio
    async def test_concurrent_handlers_only_one_dispatches(self):
        """Simulate concurrent batch and transmitted handlers - only one dispatches."""
        import asyncio

        scan_id = str(uuid4())
        community_server_id = str(uuid4())

        dispatch_calls = []

        def create_mock_service(first_caller_wins: bool):
            mock_service = MagicMock()
            mock_service.process_messages = AsyncMock(return_value=[])
            mock_service.increment_processed_count = AsyncMock()
            mock_service.get_processed_count = AsyncMock(return_value=100)
            mock_service.get_all_batches_transmitted = AsyncMock(return_value=(True, 100))
            mock_service.append_flagged_result = AsyncMock()
            mock_service.try_set_finalize_dispatched = AsyncMock(return_value=first_caller_wins)
            return mock_service

        async def simulate_batch_handler(should_win: bool):
            mock_session = AsyncMock()
            mock_session.execute = AsyncMock(
                return_value=MagicMock(scalar_one_or_none=lambda: "platform123")
            )
            mock_session.commit = AsyncMock()

            mock_session_maker = MagicMock()
            mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

            mock_service = create_mock_service(should_win)
            mock_redis = AsyncMock()
            mock_redis.connect = AsyncMock()
            mock_redis.disconnect = AsyncMock()
            mock_redis.client = MagicMock()

            mock_finalize = MagicMock()
            mock_finalize.kiq = AsyncMock()

            settings = MagicMock()
            settings.DB_POOL_SIZE = 5
            settings.DB_POOL_MAX_OVERFLOW = 10
            settings.DB_POOL_TIMEOUT = 30
            settings.DB_POOL_RECYCLE = 1800
            settings.SIMILARITY_SEARCH_DEFAULT_THRESHOLD = 0.7

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
                patch(
                    "src.tasks.content_monitoring_tasks.finalize_bulk_scan_task",
                    mock_finalize,
                ),
            ):
                mock_engine.return_value = MagicMock()
                mock_engine.return_value.dispose = AsyncMock()

                from src.tasks.content_monitoring_tasks import process_bulk_scan_batch_task

                await process_bulk_scan_batch_task(
                    scan_id=scan_id,
                    community_server_id=community_server_id,
                    batch_number=1,
                    messages=[make_test_message("msg1", "ch1", "test")],
                    db_url="postgresql+asyncpg://test:test@localhost/test",
                    redis_url="redis://localhost:6379",
                )

                if mock_finalize.kiq.called:
                    dispatch_calls.append("batch")

        await asyncio.gather(
            simulate_batch_handler(should_win=True),
            simulate_batch_handler(should_win=False),
        )

        assert len(dispatch_calls) == 1
        assert dispatch_calls[0] == "batch"


class TestDualCompletionTriggerPattern:
    """Test dual-completion trigger pattern preservation (AC #7).

    The dual-completion trigger pattern ensures that scan finalization is triggered
    by whichever completes LAST - either the batch processing or the transmitted
    signal. This prevents race conditions where batches might still be processing
    when the "all batches transmitted" signal arrives.

    Coordination is handled via atomic Redis operations:
    - set_all_batches_transmitted(scan_id, messages_scanned) - sets transmitted flag
    - get_all_batches_transmitted(scan_id) - reads transmitted flag
    - get_processed_count(scan_id) - gets count of processed messages
    - increment_processed_count(scan_id, count) - atomic increment

    Finalization is triggered ONLY when BOTH conditions are true:
    1. transmitted flag is set (all batches have been sent)
    2. processed_count >= messages_scanned (all messages have been processed)
    """

    @pytest.mark.asyncio
    async def test_no_finalization_when_transmitted_not_set(self):
        """Task does NOT trigger finalization when transmitted flag is not set.

        This tests the first half of the dual-completion pattern: even if all
        messages have been processed, we don't finalize until we know all
        batches have been transmitted.
        """
        scan_id = str(uuid4())
        community_server_id = str(uuid4())
        messages = [make_test_message("msg1", "ch1", "test content")]

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
        mock_service.get_all_batches_transmitted = AsyncMock(return_value=(False, None))
        mock_service.append_flagged_result = AsyncMock()

        mock_redis = AsyncMock()
        mock_redis.connect = AsyncMock()
        mock_redis.disconnect = AsyncMock()
        mock_redis.client = MagicMock()

        mock_llm_service = MagicMock()

        settings = MagicMock()
        settings.DB_POOL_SIZE = 5
        settings.DB_POOL_MAX_OVERFLOW = 10
        settings.DB_POOL_TIMEOUT = 30
        settings.DB_POOL_RECYCLE = 1800
        settings.SIMILARITY_SEARCH_DEFAULT_THRESHOLD = 0.7

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
            patch(
                "src.tasks.content_monitoring_tasks._get_llm_service",
                return_value=mock_llm_service,
            ),
            patch("src.config.get_settings", return_value=settings),
            patch("src.tasks.content_monitoring_tasks.finalize_bulk_scan_task") as mock_finalize,
        ):
            mock_engine.return_value = MagicMock()
            mock_engine.return_value.dispose = AsyncMock()
            mock_finalize.kiq = AsyncMock()

            from src.tasks.content_monitoring_tasks import process_bulk_scan_batch_task

            await process_bulk_scan_batch_task(
                scan_id=scan_id,
                community_server_id=community_server_id,
                batch_number=1,
                messages=messages,
                db_url="postgresql+asyncpg://test:test@localhost/test",
                redis_url="redis://localhost:6379",
            )

            mock_service.get_all_batches_transmitted.assert_called()
            mock_finalize.kiq.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_finalization_when_processed_count_insufficient(self):
        """Task does NOT trigger finalization when processed count < messages_scanned.

        This tests the second half of the dual-completion pattern: even if the
        transmitted flag is set, we don't finalize until all messages have been
        processed.
        """
        scan_id = str(uuid4())
        community_server_id = str(uuid4())
        messages = [make_test_message("msg1", "ch1", "test content")]
        messages_scanned = 100

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
        mock_service.get_all_batches_transmitted = AsyncMock(return_value=(True, messages_scanned))
        mock_service.try_set_finalize_dispatched = AsyncMock(return_value=True)
        mock_service.append_flagged_result = AsyncMock()

        mock_redis = AsyncMock()
        mock_redis.connect = AsyncMock()
        mock_redis.disconnect = AsyncMock()
        mock_redis.client = MagicMock()

        mock_llm_service = MagicMock()

        settings = MagicMock()
        settings.DB_POOL_SIZE = 5
        settings.DB_POOL_MAX_OVERFLOW = 10
        settings.DB_POOL_TIMEOUT = 30
        settings.DB_POOL_RECYCLE = 1800
        settings.SIMILARITY_SEARCH_DEFAULT_THRESHOLD = 0.7

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
            patch(
                "src.tasks.content_monitoring_tasks._get_llm_service",
                return_value=mock_llm_service,
            ),
            patch("src.config.get_settings", return_value=settings),
            patch("src.tasks.content_monitoring_tasks.finalize_bulk_scan_task") as mock_finalize,
        ):
            mock_engine.return_value = MagicMock()
            mock_engine.return_value.dispose = AsyncMock()
            mock_finalize.kiq = AsyncMock()

            from src.tasks.content_monitoring_tasks import process_bulk_scan_batch_task

            await process_bulk_scan_batch_task(
                scan_id=scan_id,
                community_server_id=community_server_id,
                batch_number=5,
                messages=messages,
                db_url="postgresql+asyncpg://test:test@localhost/test",
                redis_url="redis://localhost:6379",
            )

            mock_service.get_all_batches_transmitted.assert_called()
            mock_service.get_processed_count.assert_called()
            mock_finalize.kiq.assert_not_called()

    @pytest.mark.asyncio
    async def test_finalization_triggered_when_both_conditions_met(self):
        """Task triggers finalization when BOTH transmitted=True AND processed >= scanned.

        This tests the complete dual-completion pattern: finalization only occurs
        when both conditions are satisfied. The last operation (either batch
        processing or transmitted signal) triggers the finalization.
        """
        scan_id = str(uuid4())
        community_server_id = str(uuid4())
        messages = [make_test_message("msg1", "ch1", "test content")]
        messages_scanned = 100

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
        mock_service.get_processed_count = AsyncMock(return_value=messages_scanned)
        mock_service.get_all_batches_transmitted = AsyncMock(return_value=(True, messages_scanned))
        mock_service.try_set_finalize_dispatched = AsyncMock(return_value=True)
        mock_service.append_flagged_result = AsyncMock()

        mock_redis = AsyncMock()
        mock_redis.connect = AsyncMock()
        mock_redis.disconnect = AsyncMock()
        mock_redis.client = MagicMock()

        mock_llm_service = MagicMock()

        settings = MagicMock()
        settings.DB_POOL_SIZE = 5
        settings.DB_POOL_MAX_OVERFLOW = 10
        settings.DB_POOL_TIMEOUT = 30
        settings.DB_POOL_RECYCLE = 1800
        settings.SIMILARITY_SEARCH_DEFAULT_THRESHOLD = 0.7

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
            patch(
                "src.tasks.content_monitoring_tasks._get_llm_service",
                return_value=mock_llm_service,
            ),
            patch("src.config.get_settings", return_value=settings),
            patch("src.tasks.content_monitoring_tasks.finalize_bulk_scan_task") as mock_finalize,
        ):
            mock_engine.return_value = MagicMock()
            mock_engine.return_value.dispose = AsyncMock()
            mock_finalize.kiq = AsyncMock()

            from src.tasks.content_monitoring_tasks import process_bulk_scan_batch_task

            await process_bulk_scan_batch_task(
                scan_id=scan_id,
                community_server_id=community_server_id,
                batch_number=10,
                messages=messages,
                db_url="postgresql+asyncpg://test:test@localhost/test",
                redis_url="redis://localhost:6379",
            )

            mock_service.get_all_batches_transmitted.assert_called()
            mock_service.get_processed_count.assert_called()
            mock_service.try_set_finalize_dispatched.assert_called_once()
            mock_finalize.kiq.assert_called_once()

            call_kwargs = mock_finalize.kiq.call_args.kwargs
            assert call_kwargs["scan_id"] == scan_id
            assert call_kwargs["community_server_id"] == community_server_id
            assert call_kwargs["messages_scanned"] == messages_scanned

    @pytest.mark.asyncio
    async def test_atomic_redis_operations_called_for_coordination(self):
        """Verify that atomic Redis operations are used for dual-completion coordination.

        The dual-completion pattern relies on atomic Redis operations to prevent
        race conditions. This test verifies that:
        1. increment_processed_count is called to atomically update count
        2. get_processed_count is called to read current state
        3. get_all_batches_transmitted is called to check transmitted flag
        4. try_set_finalize_dispatched is used for idempotent dispatch
        """
        scan_id = str(uuid4())
        community_server_id = str(uuid4())
        messages = [make_test_message("msg1", "ch1", "test content")]

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

        mock_llm_service = MagicMock()

        settings = MagicMock()
        settings.DB_POOL_SIZE = 5
        settings.DB_POOL_MAX_OVERFLOW = 10
        settings.DB_POOL_TIMEOUT = 30
        settings.DB_POOL_RECYCLE = 1800
        settings.SIMILARITY_SEARCH_DEFAULT_THRESHOLD = 0.7

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
            patch(
                "src.tasks.content_monitoring_tasks._get_llm_service",
                return_value=mock_llm_service,
            ),
            patch("src.config.get_settings", return_value=settings),
        ):
            mock_engine.return_value = MagicMock()
            mock_engine.return_value.dispose = AsyncMock()

            from src.tasks.content_monitoring_tasks import process_bulk_scan_batch_task

            await process_bulk_scan_batch_task(
                scan_id=scan_id,
                community_server_id=community_server_id,
                batch_number=1,
                messages=messages,
                db_url="postgresql+asyncpg://test:test@localhost/test",
                redis_url="redis://localhost:6379",
            )

            mock_service.increment_processed_count.assert_called_once()
            mock_service.get_processed_count.assert_called_once()
            mock_service.get_all_batches_transmitted.assert_called_once()
