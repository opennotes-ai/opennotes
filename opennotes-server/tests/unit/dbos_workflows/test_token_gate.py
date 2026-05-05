from unittest.mock import patch

import pytest

from src.dbos_workflows.token_bucket.gate import TokenGate
from src.dbos_workflows.token_bucket.gate import logger as gate_logger


class TestTokenGateAcquire:
    @patch("src.dbos_workflows.token_bucket.gate.DBOS")
    @patch("src.dbos_workflows.token_bucket.gate.try_acquire_tokens")
    def test_acquire_immediate(self, mock_acquire, mock_dbos):
        mock_dbos.workflow_id = "wf-123"
        mock_acquire.return_value = True

        gate = TokenGate(pool="default", weight=3)
        gate.acquire()

        mock_acquire.assert_called_once_with("default", 3, "wf-123")
        mock_dbos.sleep.assert_not_called()

    @patch("src.dbos_workflows.token_bucket.gate.DBOS")
    @patch("src.dbos_workflows.token_bucket.gate.try_acquire_tokens")
    def test_parent_holds_token_skips_acquire(self, mock_acquire, mock_dbos):
        mock_dbos.workflow_id = "wf-child"

        gate = TokenGate(pool="default", weight=4, parent_holds_token=True)
        gate.acquire()

        mock_acquire.assert_not_called()
        mock_dbos.sleep.assert_not_called()
        assert gate._workflow_id is None

    @patch("src.dbos_workflows.token_bucket.gate.DBOS")
    @patch("src.dbos_workflows.token_bucket.gate.try_acquire_tokens")
    def test_acquire_polls_until_available(self, mock_acquire, mock_dbos):
        mock_dbos.workflow_id = "wf-123"
        mock_acquire.side_effect = [False, False, True]

        gate = TokenGate(pool="default", weight=3, poll_interval=1.0)
        gate.acquire()

        assert mock_acquire.call_count == 3
        assert mock_dbos.sleep.call_count == 2

    @patch("src.dbos_workflows.token_bucket.gate.DBOS")
    @patch("src.dbos_workflows.token_bucket.gate.try_acquire_tokens")
    def test_acquire_timeout(self, mock_acquire, mock_dbos):
        mock_dbos.workflow_id = "wf-123"
        mock_acquire.return_value = False

        gate = TokenGate(pool="default", weight=100, max_wait_seconds=3.0, poll_interval=2.0)
        with pytest.raises(TimeoutError, match="timed out"):
            gate.acquire()

    @patch("src.dbos_workflows.token_bucket.gate.DBOS")
    @patch("src.dbos_workflows.token_bucket.gate.try_acquire_tokens")
    def test_acquire_timeout_at_exact_boundary(self, mock_acquire, mock_dbos):
        """When elapsed equals max_wait, should raise TimeoutError."""
        mock_dbos.workflow_id = "wf-123"
        mock_acquire.return_value = False

        gate = TokenGate(pool="default", weight=100, max_wait_seconds=2.0, poll_interval=2.0)
        with pytest.raises(TimeoutError):
            gate.acquire()

    @patch("src.dbos_workflows.token_bucket.gate.DBOS")
    @patch("src.dbos_workflows.token_bucket.gate.try_acquire_tokens")
    def test_acquire_retries_on_transient_error(self, mock_acquire, mock_dbos):
        mock_dbos.workflow_id = "wf-123"
        mock_acquire.side_effect = [RuntimeError("connection reset"), True]

        gate = TokenGate(pool="default", weight=3, poll_interval=1.0)
        gate.acquire()

        assert mock_acquire.call_count == 2
        assert mock_dbos.sleep.call_count == 1

    @patch("src.dbos_workflows.token_bucket.gate.DBOS")
    @patch("src.dbos_workflows.token_bucket.gate.try_acquire_tokens")
    def test_acquire_logs_warning_on_transient_error(self, mock_acquire, mock_dbos, caplog):
        mock_dbos.workflow_id = "wf-456"
        mock_acquire.side_effect = [RuntimeError("db gone"), True]

        import logging

        with caplog.at_level(logging.WARNING, logger=gate_logger.name):
            gate = TokenGate(pool="gpu", weight=2, poll_interval=1.0)
            gate.acquire()

        assert any("try_acquire_tokens failed" in r.message for r in caplog.records)
        warning_record = next(r for r in caplog.records if "try_acquire_tokens failed" in r.message)
        assert warning_record.pool == "gpu"
        assert warning_record.workflow_id == "wf-456"

    @patch("src.dbos_workflows.token_bucket.gate.DBOS")
    @patch("src.dbos_workflows.token_bucket.gate.try_acquire_tokens")
    def test_acquire_all_errors_still_times_out(self, mock_acquire, mock_dbos):
        mock_dbos.workflow_id = "wf-123"
        mock_acquire.side_effect = RuntimeError("persistent failure")

        gate = TokenGate(pool="default", weight=1, max_wait_seconds=3.0, poll_interval=2.0)
        with pytest.raises(TimeoutError, match="timed out"):
            gate.acquire()


class TestTokenGateRelease:
    @patch("src.dbos_workflows.token_bucket.gate.release_tokens")
    def test_release_calls_release_tokens(self, mock_release):
        gate = TokenGate(pool="default", weight=3)
        gate._workflow_id = "wf-123"
        gate.release()

        mock_release.assert_called_once_with("default", "wf-123")

    @patch("src.dbos_workflows.token_bucket.gate.release_tokens")
    def test_release_noop_without_acquire(self, mock_release):
        gate = TokenGate(pool="default", weight=3)
        gate.release()

        mock_release.assert_not_called()

    @patch("src.dbos_workflows.token_bucket.gate.release_tokens")
    def test_release_noop_when_parent_holds_token(self, mock_release):
        gate = TokenGate(pool="default", weight=4, parent_holds_token=True)
        gate._workflow_id = "wf-child"
        gate.release()

        mock_release.assert_not_called()

    @patch("src.dbos_workflows.token_bucket.gate.release_tokens")
    @patch("src.dbos_workflows.token_bucket.gate.try_acquire_tokens")
    @patch("src.dbos_workflows.token_bucket.gate.DBOS")
    def test_workflow_id_not_set_on_timeout(self, mock_dbos, mock_acquire, mock_release):
        mock_dbos.workflow_id = "wf-timeout"
        mock_acquire.return_value = False

        gate = TokenGate(pool="default", weight=1, max_wait_seconds=1.0, poll_interval=1.0)
        with pytest.raises(TimeoutError):
            gate.acquire()

        assert gate._workflow_id is None
        gate.release()
        mock_release.assert_not_called()


class TestTokenGateDefaults:
    def test_default_values(self):
        gate = TokenGate()
        assert gate.pool == "default"
        assert gate.weight == 1
        assert gate.poll_interval == 2.0
        assert gate.max_wait_seconds == 300.0
        assert gate.parent_holds_token is False

    def test_custom_values(self):
        gate = TokenGate(
            pool="gpu",
            weight=5,
            poll_interval=5.0,
            max_wait_seconds=60.0,
            parent_holds_token=True,
        )
        assert gate.pool == "gpu"
        assert gate.weight == 5
        assert gate.poll_interval == 5.0
        assert gate.max_wait_seconds == 60.0
        assert gate.parent_holds_token is True
