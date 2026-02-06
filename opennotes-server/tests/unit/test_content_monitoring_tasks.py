"""
Unit tests for TaskIQ content monitoring tasks.

Tests cover:
- AI note generation task
- Vision description task
- Audit log persistence task
- Rate limiting preservation
- OpenTelemetry tracing

Bulk scan batch processing and finalization tasks have been migrated to DBOS workflows.
See tests/unit/test_content_scan_workflow.py for DBOS workflow tests.

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
        """Task serializes details dict to JSON string for Text column (task-910.04)."""
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


class TestWorkerEventPublisher:
    """Test worker event publisher context manager (task-976)."""

    @pytest.mark.asyncio
    async def test_create_worker_event_publisher_connects_and_disconnects(self):
        """Worker event publisher creates its own NATS connection and cleans up."""
        mock_nats_client = MagicMock()
        mock_nats_client.connect = AsyncMock()
        mock_nats_client.disconnect = AsyncMock()

        with patch("src.events.nats_client.NATSClientManager", return_value=mock_nats_client):
            from src.events.publisher import create_worker_event_publisher

            async with create_worker_event_publisher() as publisher:
                mock_nats_client.connect.assert_called_once()
                assert publisher.nats is mock_nats_client

            mock_nats_client.disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_worker_event_publisher_disconnects_on_error(self):
        """Worker event publisher disconnects even if an error occurs."""
        mock_nats_client = MagicMock()
        mock_nats_client.connect = AsyncMock()
        mock_nats_client.disconnect = AsyncMock()

        with patch("src.events.nats_client.NATSClientManager", return_value=mock_nats_client):
            from src.events.publisher import create_worker_event_publisher

            with pytest.raises(ValueError, match="test error"):
                async with create_worker_event_publisher():
                    raise ValueError("test error")

            mock_nats_client.connect.assert_called_once()
            mock_nats_client.disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_event_publisher_accepts_custom_nats_client(self):
        """EventPublisher can be initialized with a custom NATS client."""
        mock_nats_client = MagicMock()

        from src.events.publisher import EventPublisher

        publisher = EventPublisher(nats=mock_nats_client)

        assert publisher.nats is mock_nats_client

    @pytest.mark.asyncio
    async def test_event_publisher_uses_global_singleton_by_default(self):
        """EventPublisher uses global nats_client singleton when no client provided."""
        from src.events.nats_client import nats_client
        from src.events.publisher import EventPublisher

        publisher = EventPublisher()

        assert publisher.nats is nats_client

    @pytest.mark.asyncio
    async def test_create_worker_event_publisher_propagates_connect_error_and_disconnects(self):
        """Worker event publisher propagates connect error and still calls disconnect."""
        mock_nats_client = MagicMock()
        mock_nats_client.connect = AsyncMock(side_effect=ConnectionError("NATS connection failed"))
        mock_nats_client.disconnect = AsyncMock()

        with patch("src.events.nats_client.NATSClientManager", return_value=mock_nats_client):
            from src.events.publisher import create_worker_event_publisher

            with pytest.raises(ConnectionError, match="NATS connection failed"):
                async with create_worker_event_publisher():
                    pass

            mock_nats_client.connect.assert_called_once()
            mock_nats_client.disconnect.assert_called_once()
