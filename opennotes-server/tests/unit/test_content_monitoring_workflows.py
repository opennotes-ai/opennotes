"""Unit tests for DBOS content monitoring workflows.

Tests cover:
- Deprecated TaskIQ stubs return {"status": "deprecated"}
- start_ai_note_workflow calls DBOSClient.start_workflow correctly
- call_persist_audit_log calls DBOSClient.start_workflow correctly
- Audit middleware calls call_persist_audit_log instead of NATS
"""

import json
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest


class TestDeprecatedTaskIQStubs:
    @pytest.mark.asyncio
    async def test_generate_ai_note_task_returns_deprecated(self):
        from src.tasks.content_monitoring_tasks import generate_ai_note_task

        result = await generate_ai_note_task(
            community_server_id="platform123",
            request_id="req123",
            content="test content",
            scan_type="similarity",
            db_url="postgresql+asyncpg://test:test@localhost/test",
        )

        assert result["status"] == "deprecated"
        assert result["migrated_to"] == "dbos"

    @pytest.mark.asyncio
    async def test_process_vision_description_task_returns_deprecated(self):
        from src.tasks.content_monitoring_tasks import process_vision_description_task

        result = await process_vision_description_task(
            message_archive_id=str(uuid4()),
            image_url="https://example.com/image.jpg",
            community_server_id="platform123",
            db_url="postgresql+asyncpg://test:test@localhost/test",
        )

        assert result["status"] == "deprecated"
        assert result["migrated_to"] == "dbos"

    @pytest.mark.asyncio
    async def test_persist_audit_log_task_returns_deprecated(self):
        from src.tasks.content_monitoring_tasks import persist_audit_log_task

        result = await persist_audit_log_task(
            user_id=str(uuid4()),
            community_server_id=None,
            action="test.action",
            resource="test",
            resource_id=None,
            details=None,
            ip_address=None,
            user_agent=None,
            db_url="postgresql+asyncpg://test:test@localhost/test",
        )

        assert result["status"] == "deprecated"
        assert result["migrated_to"] == "dbos"


class TestStartAINoteWorkflow:
    def test_calls_dbos_client_start_workflow(self):
        mock_client = MagicMock()

        with patch(
            "src.dbos_workflows.config.get_dbos_client",
            return_value=mock_client,
        ):
            from src.dbos_workflows.content_monitoring_workflows import (
                ai_note_generation_workflow,
                start_ai_note_workflow,
            )

            start_ai_note_workflow(
                community_server_id="platform123",
                request_id="req456",
                content="test claim",
                scan_type="similarity",
                fact_check_item_id="fc-item-1",
                similarity_score=0.85,
            )

            mock_client.start_workflow.assert_called_once_with(
                ai_note_generation_workflow,
                "platform123",
                "req456",
                "test claim",
                "similarity",
                "fc-item-1",
                0.85,
                None,
            )

    def test_serializes_moderation_metadata_to_json(self):
        mock_client = MagicMock()
        moderation_metadata = {
            "categories": {"harassment": True},
            "scores": {"harassment": 0.92},
            "flagged_categories": ["harassment"],
        }

        with patch(
            "src.dbos_workflows.config.get_dbos_client",
            return_value=mock_client,
        ):
            from src.dbos_workflows.content_monitoring_workflows import (
                ai_note_generation_workflow,
                start_ai_note_workflow,
            )

            start_ai_note_workflow(
                community_server_id="platform123",
                request_id="req789",
                content="test content",
                scan_type="openai_moderation",
                moderation_metadata=moderation_metadata,
            )

            call_args = mock_client.start_workflow.call_args
            positional = call_args[0]
            assert positional[0] == ai_note_generation_workflow
            metadata_json = positional[7]
            assert json.loads(metadata_json) == moderation_metadata


class TestCallPersistAuditLog:
    def test_calls_dbos_client_start_workflow(self):
        mock_client = MagicMock()

        with patch(
            "src.dbos_workflows.config.get_dbos_client",
            return_value=mock_client,
        ):
            from src.dbos_workflows.content_monitoring_workflows import (
                _audit_log_wrapper_workflow,
                call_persist_audit_log,
            )

            call_persist_audit_log(
                user_id="user-123",
                action="POST /api/notes",
                resource="notes",
                resource_id="note-456",
                details='{"status_code": 201}',
                ip_address="127.0.0.1",
                user_agent="TestAgent/1.0",
                created_at_iso="2024-01-15T10:30:00+00:00",
            )

            mock_client.start_workflow.assert_called_once_with(
                _audit_log_wrapper_workflow,
                "user-123",
                "POST /api/notes",
                "notes",
                "note-456",
                '{"status_code": 201}',
                "127.0.0.1",
                "TestAgent/1.0",
                "2024-01-15T10:30:00+00:00",
            )

    def test_handles_none_optional_fields(self):
        mock_client = MagicMock()

        with patch(
            "src.dbos_workflows.config.get_dbos_client",
            return_value=mock_client,
        ):
            from src.dbos_workflows.content_monitoring_workflows import (
                _audit_log_wrapper_workflow,
                call_persist_audit_log,
            )

            call_persist_audit_log(
                user_id=None,
                action="system.startup",
                resource="server",
            )

            mock_client.start_workflow.assert_called_once_with(
                _audit_log_wrapper_workflow,
                None,
                "system.startup",
                "server",
                None,
                None,
                None,
                None,
                None,
            )


class TestAuditMiddlewareUsesDBOS:
    @pytest.mark.asyncio
    async def test_publish_audit_log_calls_dbos_instead_of_nats(self):
        from src.middleware.audit import AuditMiddleware

        middleware = AuditMiddleware(app=MagicMock())

        mock_request = MagicMock()
        mock_request.method = "POST"
        mock_request.url.path = "/api/v1/notes"
        mock_request.client.host = "127.0.0.1"
        mock_request.headers.get.return_value = "TestAgent/1.0"

        mock_response = MagicMock()
        mock_response.status_code = 201

        from datetime import UTC, datetime

        start_time = datetime.now(UTC)

        with patch("src.middleware.audit.call_persist_audit_log") as mock_call:
            await middleware._publish_audit_log(
                request=mock_request,
                response=mock_response,
                request_body=None,
                start_time=start_time,
                user_id=uuid4(),
            )

            mock_call.assert_called_once()
            call_args = mock_call.call_args.args
            assert call_args[1] == "POST /api/v1/notes"
            assert call_args[2] == "notes"
            assert call_args[5] == "127.0.0.1"


class TestHelperFunctionsStillAccessible:
    def test_build_fact_check_prompt_accessible(self):
        from src.tasks.content_monitoring_tasks import _build_fact_check_prompt

        mock_item = MagicMock()
        mock_item.title = "Test"
        mock_item.rating = "false"
        mock_item.summary = "Summary"
        mock_item.content = "Content"
        mock_item.source_url = "https://example.com"

        result = _build_fact_check_prompt("test message", mock_item, 0.85)
        assert "test message" in result
        assert "85.00%" in result

    def test_build_general_explanation_prompt_accessible(self):
        from src.tasks.content_monitoring_tasks import _build_general_explanation_prompt

        result = _build_general_explanation_prompt("test message")
        assert "test message" in result

    def test_create_db_engine_accessible(self):
        from src.tasks.content_monitoring_tasks import _create_db_engine

        assert callable(_create_db_engine)

    def test_get_llm_service_accessible(self):
        from src.tasks.content_monitoring_tasks import _get_llm_service

        assert callable(_get_llm_service)


class TestTaskIQLabelsStillRegistered:
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
