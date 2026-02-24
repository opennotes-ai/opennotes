from __future__ import annotations

import inspect
import re
from datetime import UTC, datetime
from unittest.mock import patch

from src.dbos_workflows.token_bucket.cleanup import (
    CLEANUP_STALE_TOKEN_HOLDS_WORKFLOW_NAME,
    MAX_HOLD_DURATION_SECONDS,
    cleanup_stale_token_holds,
    find_stale_holds,
    release_stale_hold,
)


class TestFindStaleHolds:
    def test_returns_list_of_hold_dicts(self):
        expected = [
            {
                "id": "abc-123",
                "pool_name": "default",
                "workflow_id": "wf-old",
                "weight": 3,
                "acquired_at": "2026-01-01T00:00:00+00:00",
            }
        ]
        with patch(
            "src.dbos_workflows.token_bucket.cleanup.run_sync",
            return_value=expected,
        ):
            result = find_stale_holds(MAX_HOLD_DURATION_SECONDS)

        assert len(result) == 1
        assert result[0]["workflow_id"] == "wf-old"

    def test_returns_empty_when_no_stale_holds(self):
        with patch(
            "src.dbos_workflows.token_bucket.cleanup.run_sync",
            return_value=[],
        ):
            result = find_stale_holds(MAX_HOLD_DURATION_SECONDS)

        assert result == []

    def test_accepts_custom_max_age(self):
        with patch(
            "src.dbos_workflows.token_bucket.cleanup.run_sync",
            return_value=[],
        ) as mock_run_sync:
            find_stale_holds(7200)

        mock_run_sync.assert_called_once()


class TestReleaseStaleHold:
    def _make_hold(self) -> dict:
        return {
            "id": "abc-123",
            "pool_name": "default",
            "workflow_id": "wf-old",
            "weight": 3,
            "acquired_at": "2026-01-01T00:00:00+00:00",
        }

    def test_returns_true_when_released(self):
        with patch(
            "src.dbos_workflows.token_bucket.cleanup.run_sync",
            return_value=True,
        ):
            result = release_stale_hold(self._make_hold())

        assert result is True

    def test_returns_false_when_already_released(self):
        with patch(
            "src.dbos_workflows.token_bucket.cleanup.run_sync",
            return_value=False,
        ):
            result = release_stale_hold(self._make_hold())

        assert result is False


class TestCleanupStaleTokenHoldsWorkflow:
    def test_workflow_returns_found_and_released_counts(self):
        stale_holds = [
            {"id": "1", "pool_name": "p", "workflow_id": "wf-1", "weight": 1, "acquired_at": "t"},
            {"id": "2", "pool_name": "p", "workflow_id": "wf-2", "weight": 2, "acquired_at": "t"},
        ]
        with (
            patch(
                "src.dbos_workflows.token_bucket.cleanup.find_stale_holds",
                return_value=stale_holds,
            ),
            patch(
                "src.dbos_workflows.token_bucket.cleanup.release_stale_hold",
                side_effect=[True, True],
            ),
        ):
            result = cleanup_stale_token_holds.__wrapped__(
                scheduled_time=datetime.now(UTC),
                actual_time=datetime.now(UTC),
            )

        assert result == {"found": 2, "released": 2}

    def test_workflow_with_no_stale_holds(self):
        with (
            patch(
                "src.dbos_workflows.token_bucket.cleanup.find_stale_holds",
                return_value=[],
            ),
        ):
            result = cleanup_stale_token_holds.__wrapped__(
                scheduled_time=datetime.now(UTC),
                actual_time=datetime.now(UTC),
            )

        assert result == {"found": 0, "released": 0}

    def test_workflow_counts_partial_releases(self):
        stale_holds = [
            {"id": "1", "pool_name": "p", "workflow_id": "wf-1", "weight": 1, "acquired_at": "t"},
            {"id": "2", "pool_name": "p", "workflow_id": "wf-2", "weight": 2, "acquired_at": "t"},
            {"id": "3", "pool_name": "p", "workflow_id": "wf-3", "weight": 1, "acquired_at": "t"},
        ]
        with (
            patch(
                "src.dbos_workflows.token_bucket.cleanup.find_stale_holds",
                return_value=stale_holds,
            ),
            patch(
                "src.dbos_workflows.token_bucket.cleanup.release_stale_hold",
                side_effect=[True, False, True],
            ),
        ):
            result = cleanup_stale_token_holds.__wrapped__(
                scheduled_time=datetime.now(UTC),
                actual_time=datetime.now(UTC),
            )

        assert result == {"found": 3, "released": 2}


class TestConstants:
    def test_max_hold_duration(self):
        assert MAX_HOLD_DURATION_SECONDS == 3600

    def test_workflow_name_uses_qualname(self):
        assert cleanup_stale_token_holds.__qualname__ == CLEANUP_STALE_TOKEN_HOLDS_WORKFLOW_NAME

    def test_workflow_name_is_string(self):
        assert isinstance(CLEANUP_STALE_TOKEN_HOLDS_WORKFLOW_NAME, str)


class TestDecoratorPresence:
    def test_workflow_has_wrapped_attribute(self):
        assert hasattr(cleanup_stale_token_holds, "__wrapped__")

    def test_cron_expression_is_valid(self):
        source = inspect.getsource(cleanup_stale_token_holds)
        match = re.search(r'@DBOS\.scheduled\("([^"]+)"\)', source)
        assert match is not None
        assert match.group(1) == "*/5 * * * *"
