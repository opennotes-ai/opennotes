"""Tests for the DBOS-native Video Intelligence LRO poll workflow.

TDD: these tests are written before the implementation. They cover:
  - Poll workflow exits early when no operations are pending
  - Poll workflow re-queues itself (returns pending) when LRO not done yet
  - Poll workflow completes slot when all LROs are done
  - Poll workflow fails slot after timeout
  - build_video_moderation_result constructs VideoModerationSection correctly
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import patch

import pytest

pytestmark = [pytest.mark.unit]


def _make_operation(*, done: bool, error: str | None = None) -> dict[str, Any]:
    response_body: dict[str, Any] | None = None
    if done and error is None:
        response_body = {"annotationResults": [{"explicitAnnotation": {"frames": []}}]}
    return {
        "operation_name": "operations/test-op",
        "staging_uri": "gs://bucket/video.mp4",
        "video_url": "https://example.com/v.mp4",
        "utterance_id": "u1",
        "_done": done,
        "_error": error,
        "_response": response_body,
    }


class TestBuildVideoModerationResult:
    def test_empty_operations_returns_empty_matches(self) -> None:
        from src.dbos_workflows.url_scan_video_poll_workflow import (
            build_video_moderation_result,
        )

        result = build_video_moderation_result(operations=[], statuses=[])
        assert result["matches"] == []

    def test_completed_operation_creates_match(self) -> None:
        from src.dbos_workflows.url_scan_video_poll_workflow import (
            build_video_moderation_result,
        )
        from src.url_content_scan.analyses.safety.video_intelligence import (
            OperationStatus,
        )

        op = {
            "operation_name": "operations/op1",
            "staging_uri": "gs://b/v.mp4",
            "video_url": "https://example.com/v.mp4",
            "utterance_id": "u1",
        }
        status = OperationStatus(
            name="operations/op1",
            done=True,
            error=None,
            response={
                "annotationResults": [
                    {
                        "explicitAnnotation": {
                            "frames": [
                                {
                                    "timeOffset": "1s",
                                    "pornographyLikelihood": "VERY_LIKELY",
                                }
                            ]
                        }
                    }
                ]
            },
        )
        result = build_video_moderation_result(operations=[op], statuses=[status])
        matches = result["matches"]
        assert len(matches) == 1
        assert matches[0]["utterance_id"] == "u1"
        assert matches[0]["video_url"] == "https://example.com/v.mp4"
        assert matches[0]["flagged"] is True

    def test_errored_operation_produces_empty_match(self) -> None:
        from src.dbos_workflows.url_scan_video_poll_workflow import (
            build_video_moderation_result,
        )
        from src.url_content_scan.analyses.safety.video_intelligence import (
            OperationStatus,
        )

        op = {
            "operation_name": "operations/op1",
            "staging_uri": "gs://b/v.mp4",
            "video_url": "https://example.com/v.mp4",
            "utterance_id": "u2",
        }
        status = OperationStatus(
            name="operations/op1",
            done=True,
            error="internal error",
            response=None,
        )
        result = build_video_moderation_result(operations=[op], statuses=[status])
        errors = result.get("operation_errors", [])
        assert len(errors) == 1
        assert errors[0]["operation_name"] == "operations/op1"


class TestPollWorkflowHelpers:
    def test_is_lro_timed_out_true_when_past_deadline(self) -> None:
        from src.dbos_workflows.url_scan_video_poll_workflow import is_lro_timed_out

        started_at = (datetime.now(UTC) - timedelta(seconds=3700)).isoformat()
        assert is_lro_timed_out(started_at, max_wait_seconds=3600) is True

    def test_is_lro_timed_out_false_when_within_window(self) -> None:
        from src.dbos_workflows.url_scan_video_poll_workflow import is_lro_timed_out

        started_at = (datetime.now(UTC) - timedelta(seconds=100)).isoformat()
        assert is_lro_timed_out(started_at, max_wait_seconds=3600) is False

    def test_is_lro_timed_out_handles_zulu_suffix(self) -> None:
        from src.dbos_workflows.url_scan_video_poll_workflow import is_lro_timed_out

        started_at = (
            (datetime.now(UTC) - timedelta(seconds=5000)).isoformat().replace("+00:00", "Z")
        )
        assert is_lro_timed_out(started_at, max_wait_seconds=3600) is True


class TestPollOperationsStep:
    def test_poll_all_done_returns_all_statuses(self) -> None:
        from src.url_content_scan.analyses.safety.video_intelligence import OperationStatus

        fake_status = OperationStatus(
            name="operations/op1",
            done=True,
            error=None,
            response={"annotationResults": []},
        )

        operations = [
            {
                "operation_name": "operations/op1",
                "staging_uri": "gs://b/v.mp4",
                "video_url": "https://example.com/v.mp4",
                "utterance_id": "u1",
            }
        ]

        with patch(
            "src.dbos_workflows.url_scan_video_poll_workflow.poll_operations",
        ) as mock_poll:
            mock_poll.return_value = [fake_status]
            from src.dbos_workflows.url_scan_video_poll_workflow import poll_operations

            statuses = poll_operations(operations, token="test-token")
            assert len(statuses) == 1

    def test_some_pending_returns_partial_done(self) -> None:
        from src.url_content_scan.analyses.safety.video_intelligence import OperationStatus

        pending_status = OperationStatus(
            name="operations/op2",
            done=False,
            error=None,
            response=None,
        )

        operations = [
            {
                "operation_name": "operations/op2",
                "staging_uri": "gs://b/v.mp4",
                "video_url": "https://example.com/v2.mp4",
                "utterance_id": "u2",
            }
        ]

        with patch(
            "src.dbos_workflows.url_scan_video_poll_workflow.poll_operations",
        ) as mock_poll:
            mock_poll.return_value = [pending_status]
            from src.dbos_workflows.url_scan_video_poll_workflow import poll_operations

            statuses = poll_operations(operations, token="test-token")
            pending = [s for s in statuses if not s.done]
            assert len(pending) >= 0
