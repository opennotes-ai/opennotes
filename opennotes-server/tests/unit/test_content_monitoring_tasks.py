"""Unit tests for deprecated TaskIQ content monitoring task stubs.

These tasks have been migrated to DBOS durable workflows.
See src/dbos_workflows/content_monitoring_workflows.py for the replacement.
See tests/unit/test_content_monitoring_workflows.py for DBOS workflow tests.

The @register_task stubs are kept to drain legacy JetStream messages.
These tests verify the stubs return {"status": "deprecated"} and that
the helper functions remain accessible.
"""

from unittest.mock import MagicMock
from uuid import uuid4

import pytest


class TestGenerateAINoteTask:
    @pytest.mark.asyncio
    async def test_returns_deprecated_status(self):
        from src.tasks.content_monitoring_tasks import generate_ai_note_task

        result = await generate_ai_note_task(
            community_server_id="platform123",
            request_id="req123",
            content="test claim content",
            scan_type="similarity",
            db_url="postgresql+asyncpg://test:test@localhost/test",
            fact_check_item_id=str(uuid4()),
            similarity_score=0.85,
        )

        assert result["status"] == "deprecated"
        assert result["migrated_to"] == "dbos"


class TestBuildGeneralExplanationPrompt:
    def test_prompt_without_moderation_metadata(self):
        from src.tasks.content_monitoring_tasks import _build_general_explanation_prompt

        prompt = _build_general_explanation_prompt("Test message content")

        assert "Test message content" in prompt
        assert "Content Moderation Analysis" not in prompt

    def test_prompt_includes_moderation_metadata(self):
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
    @pytest.mark.asyncio
    async def test_returns_deprecated_status(self):
        from src.tasks.content_monitoring_tasks import process_vision_description_task

        result = await process_vision_description_task(
            message_archive_id=str(uuid4()),
            image_url="https://example.com/image.jpg",
            community_server_id="platform123",
            db_url="postgresql+asyncpg://test:test@localhost/test",
        )

        assert result["status"] == "deprecated"
        assert result["migrated_to"] == "dbos"


class TestAuditLogTask:
    @pytest.mark.asyncio
    async def test_returns_deprecated_status(self):
        from src.tasks.content_monitoring_tasks import persist_audit_log_task

        result = await persist_audit_log_task(
            user_id=str(uuid4()),
            community_server_id=str(uuid4()),
            action="note.created",
            resource="note",
            resource_id="note123",
            details={"note_id": "note123"},
            ip_address="127.0.0.1",
            user_agent="TestAgent/1.0",
            db_url="postgresql+asyncpg://test:test@localhost/test",
        )

        assert result["status"] == "deprecated"
        assert result["migrated_to"] == "dbos"


class TestTaskIQLabels:
    def test_ai_note_task_has_labels(self):
        from src.tasks.broker import _all_registered_tasks

        assert "content:ai_note" in _all_registered_tasks

        _, labels = _all_registered_tasks["content:ai_note"]
        assert labels.get("component") == "content_monitoring"
        assert labels.get("task_type") == "generation"

    def test_vision_task_has_labels(self):
        from src.tasks.broker import _all_registered_tasks

        assert "content:vision_description" in _all_registered_tasks

        _, labels = _all_registered_tasks["content:vision_description"]
        assert labels.get("component") == "content_monitoring"
        assert labels.get("task_type") == "vision"

    def test_audit_log_task_has_labels(self):
        from src.tasks.broker import _all_registered_tasks

        assert "content:audit_log" in _all_registered_tasks

        _, labels = _all_registered_tasks["content:audit_log"]
        assert labels.get("component") == "content_monitoring"
        assert labels.get("task_type") == "audit"


class TestHelperFunctionsAccessible:
    def test_build_fact_check_prompt(self):
        from src.tasks.content_monitoring_tasks import _build_fact_check_prompt

        mock_item = MagicMock()
        mock_item.title = "Test Title"
        mock_item.rating = "false"
        mock_item.summary = "Test summary"
        mock_item.content = "Test content"
        mock_item.source_url = "https://example.com"

        result = _build_fact_check_prompt("test message", mock_item, 0.85)
        assert "test message" in result
        assert "Test Title" in result
        assert "85.00%" in result

    def test_create_db_engine_accessible(self):
        from src.tasks.content_monitoring_tasks import _create_db_engine

        assert callable(_create_db_engine)

    def test_get_llm_service_accessible(self):
        from src.tasks.content_monitoring_tasks import _get_llm_service

        assert callable(_get_llm_service)


class TestWorkerEventPublisher:
    @pytest.mark.asyncio
    async def test_create_worker_event_publisher_connects_and_disconnects(self):
        from unittest.mock import AsyncMock, MagicMock, patch

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
        from unittest.mock import AsyncMock, MagicMock, patch

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
        mock_nats_client = MagicMock()

        from src.events.publisher import EventPublisher

        publisher = EventPublisher(nats=mock_nats_client)

        assert publisher.nats is mock_nats_client

    @pytest.mark.asyncio
    async def test_event_publisher_uses_global_singleton_by_default(self):
        from src.events.nats_client import nats_client
        from src.events.publisher import EventPublisher

        publisher = EventPublisher()

        assert publisher.nats is nats_client

    @pytest.mark.asyncio
    async def test_create_worker_event_publisher_propagates_connect_error_and_disconnects(self):
        from unittest.mock import AsyncMock, MagicMock, patch

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
