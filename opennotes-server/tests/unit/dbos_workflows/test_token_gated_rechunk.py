from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from src.dbos_workflows.circuit_breaker import CircuitOpenError
from src.dbos_workflows.token_bucket.config import WorkflowWeight


class TestRechunkQueueConfig:
    def test_worker_concurrency_accommodates_waiting_workflows(self) -> None:
        from src.dbos_workflows.rechunk_workflow import rechunk_queue

        assert rechunk_queue.worker_concurrency >= 6

    def test_concurrency_accommodates_waiting_workflows(self) -> None:
        from src.dbos_workflows.rechunk_workflow import rechunk_queue

        assert rechunk_queue.concurrency >= 30


class TestRechunkFactCheckTokenGated:
    def test_acquires_and_releases_tokens(self) -> None:
        from src.dbos_workflows.rechunk_workflow import rechunk_fact_check_workflow

        batch_job_id = str(uuid4())
        item_ids = [str(uuid4())]

        with (
            patch("src.dbos_workflows.rechunk_workflow.TokenGate") as mock_gate_cls,
            patch("src.dbos_workflows.rechunk_workflow.process_fact_check_item") as mock_process,
            patch("src.dbos_workflows.rechunk_workflow.update_batch_job_progress_sync"),
            patch("src.dbos_workflows.rechunk_workflow.finalize_batch_job_sync", return_value=True),
            patch("src.dbos_workflows.rechunk_workflow.DBOS") as mock_dbos,
        ):
            mock_dbos.workflow_id = "wf-test"
            mock_gate = MagicMock()
            mock_gate_cls.return_value = mock_gate
            mock_process.return_value = {"success": True}

            rechunk_fact_check_workflow.__wrapped__(  # type: ignore[attr-defined]
                batch_job_id=batch_job_id,
                community_server_id=None,
                item_ids=item_ids,
            )

            mock_gate_cls.assert_called_once_with(pool="default", weight=WorkflowWeight.RECHUNK)
            mock_gate.acquire.assert_called_once()
            mock_gate.release.assert_called_once()

    def test_releases_tokens_on_circuit_breaker_error(self) -> None:
        from src.dbos_workflows.rechunk_workflow import rechunk_fact_check_workflow

        batch_job_id = str(uuid4())
        item_ids = [str(uuid4()) for _ in range(10)]

        with (
            patch("src.dbos_workflows.rechunk_workflow.TokenGate") as mock_gate_cls,
            patch("src.dbos_workflows.rechunk_workflow.process_fact_check_item") as mock_process,
            patch("src.dbos_workflows.rechunk_workflow.update_batch_job_progress_sync"),
            patch("src.dbos_workflows.rechunk_workflow.finalize_batch_job_sync", return_value=True),
            patch("src.dbos_workflows.rechunk_workflow.DBOS") as mock_dbos,
        ):
            mock_dbos.workflow_id = "wf-test"
            mock_gate = MagicMock()
            mock_gate_cls.return_value = mock_gate
            mock_process.side_effect = RuntimeError("Always fail")

            with pytest.raises(CircuitOpenError):
                rechunk_fact_check_workflow.__wrapped__(  # type: ignore[attr-defined]
                    batch_job_id=batch_job_id,
                    community_server_id=None,
                    item_ids=item_ids,
                )

            mock_gate.acquire.assert_called_once()
            mock_gate.release.assert_called_once()


class TestChunkSingleFactCheckTokenGated:
    def test_acquires_and_releases_tokens(self) -> None:
        from src.dbos_workflows.rechunk_workflow import chunk_single_fact_check_workflow

        fact_check_id = str(uuid4())

        with (
            patch("src.dbos_workflows.rechunk_workflow.TokenGate") as mock_gate_cls,
            patch("src.dbos_workflows.rechunk_workflow.process_fact_check_item") as mock_process,
            patch("src.dbos_workflows.rechunk_workflow.DBOS") as mock_dbos,
        ):
            mock_dbos.workflow_id = "wf-test"
            mock_gate = MagicMock()
            mock_gate_cls.return_value = mock_gate
            mock_process.return_value = {"success": True, "item_id": fact_check_id}

            chunk_single_fact_check_workflow.__wrapped__(  # type: ignore[attr-defined]
                fact_check_id=fact_check_id,
                community_server_id=None,
            )

            mock_gate_cls.assert_called_once_with(pool="default", weight=WorkflowWeight.RECHUNK)
            mock_gate.acquire.assert_called_once()
            mock_gate.release.assert_called_once()

    def test_releases_tokens_on_processing_failure(self) -> None:
        from src.dbos_workflows.rechunk_workflow import chunk_single_fact_check_workflow

        fact_check_id = str(uuid4())

        with (
            patch("src.dbos_workflows.rechunk_workflow.TokenGate") as mock_gate_cls,
            patch("src.dbos_workflows.rechunk_workflow.process_fact_check_item") as mock_process,
            patch("src.dbos_workflows.rechunk_workflow.DBOS") as mock_dbos,
        ):
            mock_dbos.workflow_id = "wf-test"
            mock_gate = MagicMock()
            mock_gate_cls.return_value = mock_gate
            mock_process.side_effect = RuntimeError("boom")

            result = chunk_single_fact_check_workflow.__wrapped__(  # type: ignore[attr-defined]
                fact_check_id=fact_check_id,
                community_server_id=None,
            )

            assert result["success"] is False
            mock_gate.acquire.assert_called_once()
            mock_gate.release.assert_called_once()


class TestRechunkPreviouslySeenTokenGated:
    def test_acquires_and_releases_tokens(self) -> None:
        from src.dbos_workflows.rechunk_workflow import rechunk_previously_seen_workflow

        batch_job_id = str(uuid4())
        community_server_id = str(uuid4())
        item_ids = [str(uuid4())]

        with (
            patch("src.dbos_workflows.rechunk_workflow.TokenGate") as mock_gate_cls,
            patch(
                "src.dbos_workflows.rechunk_workflow.process_previously_seen_item"
            ) as mock_process,
            patch("src.dbos_workflows.rechunk_workflow.update_batch_job_progress_sync"),
            patch("src.dbos_workflows.rechunk_workflow.finalize_batch_job_sync", return_value=True),
            patch("src.dbos_workflows.rechunk_workflow.DBOS") as mock_dbos,
        ):
            mock_dbos.workflow_id = "wf-test"
            mock_gate = MagicMock()
            mock_gate_cls.return_value = mock_gate
            mock_process.return_value = {"success": True}

            rechunk_previously_seen_workflow.__wrapped__(
                batch_job_id=batch_job_id,
                community_server_id=community_server_id,
                item_ids=item_ids,
            )

            mock_gate_cls.assert_called_once_with(pool="default", weight=WorkflowWeight.RECHUNK)
            mock_gate.acquire.assert_called_once()
            mock_gate.release.assert_called_once()

    def test_releases_tokens_on_circuit_breaker_error(self) -> None:
        from src.dbos_workflows.rechunk_workflow import rechunk_previously_seen_workflow

        batch_job_id = str(uuid4())
        community_server_id = str(uuid4())
        item_ids = [str(uuid4()) for _ in range(10)]

        with (
            patch("src.dbos_workflows.rechunk_workflow.TokenGate") as mock_gate_cls,
            patch(
                "src.dbos_workflows.rechunk_workflow.process_previously_seen_item"
            ) as mock_process,
            patch("src.dbos_workflows.rechunk_workflow.update_batch_job_progress_sync"),
            patch("src.dbos_workflows.rechunk_workflow.finalize_batch_job_sync", return_value=True),
            patch("src.dbos_workflows.rechunk_workflow.DBOS") as mock_dbos,
        ):
            mock_dbos.workflow_id = "wf-test"
            mock_gate = MagicMock()
            mock_gate_cls.return_value = mock_gate
            mock_process.side_effect = RuntimeError("Always fail")

            with pytest.raises(CircuitOpenError):
                rechunk_previously_seen_workflow.__wrapped__(
                    batch_job_id=batch_job_id,
                    community_server_id=community_server_id,
                    item_ids=item_ids,
                )

            mock_gate.acquire.assert_called_once()
            mock_gate.release.assert_called_once()
