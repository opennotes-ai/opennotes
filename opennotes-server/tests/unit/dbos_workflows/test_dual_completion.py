"""Tests for DBOS workflow race-condition isolation.

Verifies that concurrent workflow executions for different scans do not
interfere with each other. Each workflow instance tracks its own state
(processed_count, error_count, etc.) independently.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest


def _make_recv_dispatcher(
    batch_responses: list[dict | None],
    tx_responses: list[dict | None],
):
    batch_iter = iter(batch_responses)
    tx_iter = iter(tx_responses)

    def _recv(topic: str, **kwargs: object) -> dict | None:
        if topic == "batch_complete":
            return next(batch_iter, None)
        if topic == "all_transmitted":
            return next(tx_iter, None)
        return None

    return _recv


class TestDualWorkflowIsolation:
    """Tests that two workflows for different scans maintain isolated state."""

    def test_two_orchestrators_produce_independent_results(self) -> None:
        """Two orchestrators running for different scans produce correct independent results."""
        from src.dbos_workflows.content_scan_workflow import (
            content_scan_orchestration_workflow,
        )

        scan_id_a = str(uuid4())
        scan_id_b = str(uuid4())
        community_id = str(uuid4())

        recv_fn_a = _make_recv_dispatcher(
            batch_responses=[
                {"processed": 10, "skipped": 0, "errors": 0, "flagged_count": 3, "batch_number": 1},
            ],
            tx_responses=[
                {"messages_scanned": 10},
            ],
        )

        recv_fn_b = _make_recv_dispatcher(
            batch_responses=[
                {"processed": 5, "skipped": 2, "errors": 1, "flagged_count": 0, "batch_number": 1},
            ],
            tx_responses=[
                {"messages_scanned": 8},
            ],
        )

        with (
            patch("src.dbos_workflows.content_scan_workflow.create_scan_record_step"),
            patch("src.dbos_workflows.content_scan_workflow.finalize_scan_step") as mock_finalize_a,
            patch("src.dbos_workflows.content_scan_workflow.DBOS") as mock_dbos,
            patch("src.dbos_workflows.content_scan_workflow.TokenGate"),
        ):
            mock_dbos.workflow_id = "wf-a"
            mock_dbos.recv.side_effect = recv_fn_a
            mock_finalize_a.return_value = {"status": "completed", "scan": "a"}

            result_a = content_scan_orchestration_workflow.__wrapped__(
                scan_id=scan_id_a,
                community_server_id=community_id,
                scan_types_json=json.dumps(["similarity"]),
            )

        finalize_a_kwargs = mock_finalize_a.call_args.kwargs
        assert finalize_a_kwargs["processed_count"] == 10
        assert finalize_a_kwargs["flagged_count"] == 3
        assert finalize_a_kwargs["messages_scanned"] == 10

        with (
            patch("src.dbos_workflows.content_scan_workflow.create_scan_record_step"),
            patch("src.dbos_workflows.content_scan_workflow.finalize_scan_step") as mock_finalize_b,
            patch("src.dbos_workflows.content_scan_workflow.DBOS") as mock_dbos_b,
            patch("src.dbos_workflows.content_scan_workflow.TokenGate"),
        ):
            mock_dbos_b.workflow_id = "wf-b"
            mock_dbos_b.recv.side_effect = recv_fn_b
            mock_finalize_b.return_value = {"status": "completed", "scan": "b"}

            result_b = content_scan_orchestration_workflow.__wrapped__(
                scan_id=scan_id_b,
                community_server_id=community_id,
                scan_types_json=json.dumps(["similarity"]),
            )

        finalize_b_kwargs = mock_finalize_b.call_args.kwargs
        assert finalize_b_kwargs["processed_count"] == 5
        assert finalize_b_kwargs["skipped_count"] == 2
        assert finalize_b_kwargs["error_count"] == 1
        assert finalize_b_kwargs["flagged_count"] == 0
        assert finalize_b_kwargs["messages_scanned"] == 8

        assert result_a["scan"] == "a"
        assert result_b["scan"] == "b"

    def test_batch_workers_signal_correct_orchestrator(self) -> None:
        """Each batch worker sends signals only to its assigned orchestrator."""
        from src.dbos_workflows.content_scan_workflow import process_content_scan_batch

        orch_id_a = "orchestrator-a"
        orch_id_b = "orchestrator-b"

        preprocess_result_a = {
            "message_count": 5,
            "skipped_count": 0,
            "filtered_messages_key": "test:filtered:a",
            "context_maps_key": "test:context:a",
        }
        preprocess_result_b = {
            "message_count": 3,
            "skipped_count": 1,
            "filtered_messages_key": "test:filtered:b",
            "context_maps_key": "test:context:b",
        }
        similarity_result = {"similarity_candidates_key": "test:sim", "candidate_count": 2}
        filter_result_a = {"flagged_count": 1, "errors": 0}
        filter_result_b = {"flagged_count": 0, "errors": 0}

        with (
            patch(
                "src.dbos_workflows.content_scan_workflow.preprocess_batch_step"
            ) as mock_preprocess,
            patch(
                "src.dbos_workflows.content_scan_workflow.similarity_scan_step"
            ) as mock_similarity,
            patch("src.dbos_workflows.content_scan_workflow.flashpoint_scan_step"),
            patch("src.dbos_workflows.content_scan_workflow.relevance_filter_step") as mock_filter,
            patch("src.dbos_workflows.content_scan_workflow.DBOS") as mock_dbos,
        ):
            mock_preprocess.return_value = preprocess_result_a
            mock_similarity.return_value = similarity_result
            mock_filter.return_value = filter_result_a
            process_content_scan_batch.__wrapped__(
                orchestrator_workflow_id=orch_id_a,
                scan_id=str(uuid4()),
                community_server_id=str(uuid4()),
                batch_number=1,
                messages_redis_key="test:messages:a",
                scan_types_json='["similarity"]',
            )

            first_send_call = mock_dbos.send.call_args_list[-1]
            assert first_send_call.args[0] == orch_id_a
            assert first_send_call.args[1]["processed"] == 5
            assert first_send_call.args[1]["flagged_count"] == 1

            mock_preprocess.return_value = preprocess_result_b
            mock_filter.return_value = filter_result_b
            process_content_scan_batch.__wrapped__(
                orchestrator_workflow_id=orch_id_b,
                scan_id=str(uuid4()),
                community_server_id=str(uuid4()),
                batch_number=1,
                messages_redis_key="test:messages:b",
                scan_types_json='["similarity"]',
            )

            second_send_call = mock_dbos.send.call_args_list[-1]
            assert second_send_call.args[0] == orch_id_b
            assert second_send_call.args[1]["processed"] == 3
            assert second_send_call.args[1]["flagged_count"] == 0

    @pytest.mark.asyncio
    async def test_workflow_uses_scan_id_as_idempotency_key(self) -> None:
        """Each dispatch uses its own scan_id for idempotency, preventing cross-contamination."""
        from src.dbos_workflows.content_scan_workflow import (
            dispatch_content_scan_workflow,
        )

        scan_id_a = uuid4()
        scan_id_b = uuid4()

        with patch("src.dbos_workflows.config.get_dbos_client") as mock_get_client:
            mock_client = MagicMock()
            mock_handle = MagicMock()
            mock_handle.workflow_id = "wf-1"
            mock_client.enqueue.return_value = mock_handle
            mock_get_client.return_value = mock_client

            await dispatch_content_scan_workflow(
                scan_id=scan_id_a,
                community_server_id=uuid4(),
                scan_types=["similarity"],
            )

            first_options = mock_client.enqueue.call_args.args[0]
            assert first_options["deduplication_id"] == str(scan_id_a)

            await dispatch_content_scan_workflow(
                scan_id=scan_id_b,
                community_server_id=uuid4(),
                scan_types=["similarity"],
            )

            second_options = mock_client.enqueue.call_args.args[0]
            assert second_options["deduplication_id"] == str(scan_id_b)
            assert str(scan_id_a) != str(scan_id_b)

    def test_finalize_called_with_correct_scan_id(self) -> None:
        """Each orchestrator passes its own scan_id to finalize_scan_step."""
        from src.dbos_workflows.content_scan_workflow import (
            content_scan_orchestration_workflow,
        )

        scan_id_a = str(uuid4())
        scan_id_b = str(uuid4())

        finalize_scan_ids: list[str] = []

        def capture_finalize(**kwargs):
            finalize_scan_ids.append(kwargs["scan_id"])
            return {"status": "completed"}

        for scan_id in [scan_id_a, scan_id_b]:
            recv_fn = _make_recv_dispatcher(
                batch_responses=[
                    {
                        "processed": 1,
                        "skipped": 0,
                        "errors": 0,
                        "flagged_count": 0,
                        "batch_number": 1,
                    },
                ],
                tx_responses=[
                    {"messages_scanned": 1},
                ],
            )

            with (
                patch("src.dbos_workflows.content_scan_workflow.create_scan_record_step"),
                patch(
                    "src.dbos_workflows.content_scan_workflow.finalize_scan_step",
                    side_effect=capture_finalize,
                ),
                patch("src.dbos_workflows.content_scan_workflow.DBOS") as mock_dbos,
                patch("src.dbos_workflows.content_scan_workflow.TokenGate"),
            ):
                mock_dbos.workflow_id = f"wf-{scan_id}"
                mock_dbos.recv.side_effect = recv_fn

                content_scan_orchestration_workflow.__wrapped__(
                    scan_id=scan_id,
                    community_server_id=str(uuid4()),
                    scan_types_json=json.dumps(["similarity"]),
                )

        assert finalize_scan_ids == [scan_id_a, scan_id_b]


class TestGetBatchRedisKeyInDualWorkflows:
    """Tests that get_batch_redis_key (renamed from _get_batch_redis_key) produces
    unique keys per scan, preventing cross-contamination in dual-workflow scenarios.
    """

    def test_get_batch_redis_key_is_importable_by_new_name(self) -> None:
        from src.dbos_workflows.content_scan_workflow import get_batch_redis_key

        assert callable(get_batch_redis_key)

    def test_different_scans_produce_different_redis_keys(self) -> None:
        from src.dbos_workflows.content_scan_workflow import get_batch_redis_key

        scan_id_a = str(uuid4())
        scan_id_b = str(uuid4())

        with patch("src.config.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(ENVIRONMENT="test")

            key_a = get_batch_redis_key(scan_id_a, 1, "messages")
            key_b = get_batch_redis_key(scan_id_b, 1, "messages")

        assert key_a != key_b
        assert scan_id_a in key_a
        assert scan_id_b in key_b

    def test_same_scan_different_suffixes_produce_different_keys(self) -> None:
        from src.dbos_workflows.content_scan_workflow import get_batch_redis_key

        scan_id = str(uuid4())

        with patch("src.config.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(ENVIRONMENT="test")

            filtered_key = get_batch_redis_key(scan_id, 1, "filtered")
            context_key = get_batch_redis_key(scan_id, 1, "context")
            sim_key = get_batch_redis_key(scan_id, 1, "similarity_candidates")

        assert len({filtered_key, context_key, sim_key}) == 3

    def test_batch_workers_use_independent_redis_namespaces(self) -> None:
        """Two batch workers for different scans use non-overlapping Redis keys."""
        from src.dbos_workflows.content_scan_workflow import get_batch_redis_key

        scan_a = str(uuid4())
        scan_b = str(uuid4())

        with patch("src.config.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(ENVIRONMENT="test")

            keys_a = {
                get_batch_redis_key(scan_a, 1, suffix)
                for suffix in ("messages", "filtered", "context", "similarity_candidates")
            }
            keys_b = {
                get_batch_redis_key(scan_b, 1, suffix)
                for suffix in ("messages", "filtered", "context", "similarity_candidates")
            }

        assert keys_a.isdisjoint(keys_b)
