from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest


@pytest.mark.unit
class TestSetWorkflowResultStep:
    def test_counts_succeeded_and_failed(self):
        from src.simulation.workflows.playground_url_workflow import set_workflow_result_step

        results = [
            {"request_id": "r1", "url": "u1", "status": "PENDING"},
            {"request_id": "r2", "url": "u2", "status": "FAILED", "error": "timeout"},
            {"request_id": "r3", "url": "u3", "status": "PENDING"},
        ]

        summary = set_workflow_result_step.__wrapped__(results, 3)

        assert summary["url_count"] == 3
        assert summary["succeeded"] == 2
        assert summary["failed"] == 1
        assert len(summary["results"]) == 3

    def test_all_failed(self):
        from src.simulation.workflows.playground_url_workflow import set_workflow_result_step

        results = [
            {"request_id": "r1", "url": "u1", "status": "FAILED", "error": "e1"},
            {"request_id": "r2", "url": "u2", "status": "FAILED", "error": "e2"},
        ]

        summary = set_workflow_result_step.__wrapped__(results, 2)

        assert summary["succeeded"] == 0
        assert summary["failed"] == 2

    def test_all_succeeded(self):
        from src.simulation.workflows.playground_url_workflow import set_workflow_result_step

        results = [
            {"request_id": "r1", "url": "u1", "status": "PENDING"},
            {"request_id": "r2", "url": "u2", "status": "PENDING"},
        ]

        summary = set_workflow_result_step.__wrapped__(results, 2)

        assert summary["succeeded"] == 2
        assert summary["failed"] == 0

    def test_empty_results(self):
        from src.simulation.workflows.playground_url_workflow import set_workflow_result_step

        summary = set_workflow_result_step.__wrapped__([], 0)

        assert summary["url_count"] == 0
        assert summary["succeeded"] == 0
        assert summary["failed"] == 0
        assert summary["results"] == []


@pytest.mark.unit
class TestExtractAndCreateRequestStep:
    def test_ssrf_rejection_returns_failed(self):
        from src.simulation.workflows.playground_url_workflow import (
            extract_and_create_request_step,
        )

        with patch(
            "src.shared.url_validation.validate_url_security",
            side_effect=ValueError("private IP"),
        ):
            result = extract_and_create_request_step.__wrapped__(
                url="http://192.168.1.1/internal",
                community_server_id=str(uuid4()),
                requested_by="test-user",
                request_id="playground-test-wf-0",
            )

        assert result["status"] == "FAILED"
        assert result["error"] == "URL validation failed"
        assert result["request_id"] == "playground-test-wf-0"
        assert result["url"] == "http://192.168.1.1/internal"

    def test_content_extraction_failure_returns_failed(self):
        from src.simulation.workflows.playground_url_workflow import (
            extract_and_create_request_step,
        )

        with (
            patch(
                "src.shared.url_validation.validate_url_security",
            ),
            patch(
                "src.simulation.workflows.playground_url_workflow.run_sync",
                return_value={
                    "request_id": "playground-wf1-0",
                    "url": "https://example.com/bad",
                    "status": "FAILED",
                    "error": "Could not extract content",
                },
            ),
        ):
            result = extract_and_create_request_step.__wrapped__(
                url="https://example.com/bad",
                community_server_id=str(uuid4()),
                requested_by="test-user",
                request_id="playground-wf1-0",
            )

        assert result["status"] == "FAILED"
        assert result["request_id"] == "playground-wf1-0"

    def test_successful_extraction(self):
        from src.simulation.workflows.playground_url_workflow import (
            extract_and_create_request_step,
        )

        with (
            patch(
                "src.shared.url_validation.validate_url_security",
            ),
            patch(
                "src.simulation.workflows.playground_url_workflow.run_sync",
                return_value={
                    "request_id": "playground-wf1-0",
                    "url": "https://example.com/article",
                    "status": "PENDING",
                    "content_preview": "Some extracted text",
                },
            ),
        ):
            result = extract_and_create_request_step.__wrapped__(
                url="https://example.com/article",
                community_server_id=str(uuid4()),
                requested_by="test-user",
                request_id="playground-wf1-0",
            )

        assert result["status"] == "PENDING"
        assert result["request_id"] == "playground-wf1-0"
        assert result["content_preview"] == "Some extracted text"

    def test_request_id_is_deterministic_from_parameter(self):
        from src.simulation.workflows.playground_url_workflow import (
            extract_and_create_request_step,
        )

        request_id = "playground-my-workflow-id-0"

        with (
            patch(
                "src.shared.url_validation.validate_url_security",
                side_effect=ValueError("blocked"),
            ),
        ):
            result = extract_and_create_request_step.__wrapped__(
                url="http://localhost/evil",
                community_server_id=str(uuid4()),
                requested_by="test-user",
                request_id=request_id,
            )

        assert result["request_id"] == request_id


@pytest.mark.unit
class TestRunPlaygroundUrlExtraction:
    def test_workflow_deduplicates_urls(self):
        import json

        from src.simulation.workflows.playground_url_workflow import (
            run_playground_url_extraction,
        )

        urls_json = json.dumps(
            [
                "https://example.com/a",
                "https://example.com/b",
                "https://example.com/a",
            ]
        )

        step_calls = []

        def mock_step(url, cs_id, requested_by, request_id):
            step_calls.append({"url": url, "request_id": request_id})
            return {
                "request_id": request_id,
                "url": url,
                "status": "PENDING",
            }

        def mock_summary(results, url_count):
            return {
                "url_count": url_count,
                "succeeded": len(results),
                "failed": 0,
                "results": results,
            }

        with (
            patch(
                "src.simulation.workflows.playground_url_workflow.extract_and_create_request_step",
                side_effect=mock_step,
            ),
            patch(
                "src.simulation.workflows.playground_url_workflow.set_workflow_result_step",
                side_effect=mock_summary,
            ),
            patch(
                "src.simulation.workflows.playground_url_workflow.DBOS",
            ) as mock_dbos,
        ):
            mock_dbos.workflow_id = "test-wf-123"
            result = run_playground_url_extraction.__wrapped__(
                urls_json,
                str(uuid4()),
                "test-user",
            )

        assert len(step_calls) == 2
        assert step_calls[0]["url"] == "https://example.com/a"
        assert step_calls[1]["url"] == "https://example.com/b"
        assert result["url_count"] == 2

    def test_workflow_generates_deterministic_request_ids(self):
        import json

        from src.simulation.workflows.playground_url_workflow import (
            run_playground_url_extraction,
        )

        urls_json = json.dumps(["https://example.com/x", "https://example.com/y"])

        captured_ids = []

        def mock_step(url, cs_id, requested_by, request_id):
            captured_ids.append(request_id)
            return {
                "request_id": request_id,
                "url": url,
                "status": "PENDING",
            }

        def mock_summary(results, url_count):
            return {
                "url_count": url_count,
                "succeeded": len(results),
                "failed": 0,
                "results": results,
            }

        with (
            patch(
                "src.simulation.workflows.playground_url_workflow.extract_and_create_request_step",
                side_effect=mock_step,
            ),
            patch(
                "src.simulation.workflows.playground_url_workflow.set_workflow_result_step",
                side_effect=mock_summary,
            ),
            patch(
                "src.simulation.workflows.playground_url_workflow.DBOS",
            ) as mock_dbos,
        ):
            mock_dbos.workflow_id = "wf-abc"
            run_playground_url_extraction.__wrapped__(
                urls_json,
                str(uuid4()),
                "test-user",
            )

        assert captured_ids == ["playground-wf-abc-0", "playground-wf-abc-1"]


@pytest.mark.unit
class TestDispatchPlaygroundUrlExtraction:
    @pytest.mark.asyncio
    async def test_enqueues_workflow_via_dbos_client(self):
        from src.simulation.workflows.playground_url_workflow import (
            dispatch_playground_url_extraction,
        )

        mock_handle = MagicMock()
        mock_handle.workflow_id = "playground-urls-fakeid"
        mock_client = MagicMock()
        mock_client.enqueue.return_value = mock_handle

        cs_id = uuid4()

        with patch(
            "src.dbos_workflows.config.get_dbos_client",
            return_value=mock_client,
        ):
            wf_id = await dispatch_playground_url_extraction(
                urls=["https://example.com/a"],
                community_server_id=cs_id,
                requested_by="test-user",
            )

        assert wf_id == "playground-urls-fakeid"
        mock_client.enqueue.assert_called_once()
        call_args = mock_client.enqueue.call_args
        options = call_args[0][0]
        assert options["queue_name"] == "playground_url_extraction"

    @pytest.mark.asyncio
    async def test_passes_serialized_urls(self):
        import json

        from src.simulation.workflows.playground_url_workflow import (
            dispatch_playground_url_extraction,
        )

        mock_handle = MagicMock()
        mock_handle.workflow_id = "wf-test"
        mock_client = MagicMock()
        mock_client.enqueue.return_value = mock_handle

        urls = ["https://example.com/1", "https://example.com/2"]

        with patch(
            "src.dbos_workflows.config.get_dbos_client",
            return_value=mock_client,
        ):
            await dispatch_playground_url_extraction(
                urls=urls,
                community_server_id=uuid4(),
                requested_by="test-user",
            )

        call_args = mock_client.enqueue.call_args
        urls_json_arg = call_args[0][1]
        assert json.loads(urls_json_arg) == urls
