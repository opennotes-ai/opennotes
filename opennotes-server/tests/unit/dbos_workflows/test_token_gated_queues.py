from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

from src.dbos_workflows.token_bucket.config import WorkflowWeight


class TestQueueConcurrencyBumped:
    def test_content_scan_queue(self):
        from src.dbos_workflows.content_scan_workflow import content_scan_queue

        assert content_scan_queue.worker_concurrency >= 6
        assert content_scan_queue.concurrency >= 12

    def test_import_pipeline_queue(self):
        from src.dbos_workflows.import_workflow import import_pipeline_queue

        assert import_pipeline_queue.worker_concurrency >= 3
        assert import_pipeline_queue.concurrency >= 9

    def test_approval_queue(self):
        from src.dbos_workflows.approval_workflow import approval_queue

        assert approval_queue.worker_concurrency >= 3
        assert approval_queue.concurrency >= 6

    def test_content_monitoring_queue(self):
        from src.dbos_workflows.content_monitoring_workflows import content_monitoring_queue

        assert content_monitoring_queue.worker_concurrency >= 6
        assert content_monitoring_queue.concurrency >= 12

    def test_simulation_orchestrator_queue(self):
        from src.simulation.workflows.orchestrator_workflow import simulation_orchestrator_queue

        assert simulation_orchestrator_queue.worker_concurrency >= 3
        assert simulation_orchestrator_queue.concurrency >= 6

    def test_simulation_turn_queue(self):
        from src.simulation.workflows.agent_turn_workflow import simulation_turn_queue

        assert simulation_turn_queue.worker_concurrency >= 6
        assert simulation_turn_queue.concurrency >= 24


class TestContentScanTokenGated:
    def test_acquires_and_releases_tokens(self) -> None:
        from src.dbos_workflows.content_scan_workflow import (
            content_scan_orchestration_workflow,
        )

        scan_id = str(uuid4())
        community_server_id = str(uuid4())

        with (
            patch("src.dbos_workflows.content_scan_workflow.TokenGate") as mock_gate_cls,
            patch("src.dbos_workflows.content_scan_workflow.create_scan_record_step"),
            patch("src.dbos_workflows.content_scan_workflow._checkpoint_wall_clock_step"),
            patch("src.dbos_workflows.content_scan_workflow.finalize_scan_step", return_value={}),
            patch("src.dbos_workflows.content_scan_workflow.DBOS") as mock_dbos,
        ):
            mock_dbos.workflow_id = "wf-test"
            mock_dbos.recv.return_value = {"messages_scanned": 0}
            mock_gate = MagicMock()
            mock_gate_cls.return_value = mock_gate

            content_scan_orchestration_workflow.__wrapped__(
                scan_id=scan_id,
                community_server_id=community_server_id,
                scan_types_json="[]",
            )

            mock_gate_cls.assert_called_once_with(
                pool="default", weight=WorkflowWeight.CONTENT_SCAN
            )
            mock_gate.acquire.assert_called_once()
            mock_gate.release.assert_called_once()


class TestImportPipelineTokenGated:
    def test_fact_check_import_acquires_and_releases(self) -> None:
        from src.dbos_workflows.import_workflow import fact_check_import_workflow

        batch_job_id = str(uuid4())

        with (
            patch("src.dbos_workflows.import_workflow.TokenGate") as mock_gate_cls,
            patch("src.dbos_workflows.import_workflow.start_import_step", return_value=True),
            patch(
                "src.dbos_workflows.import_workflow.import_csv_step",
                return_value={"valid_rows": 1, "invalid_rows": 0},
            ),
            patch("src.dbos_workflows.import_workflow.finalize_batch_job_sync", return_value=True),
            patch("src.dbos_workflows.import_workflow.DBOS") as mock_dbos,
        ):
            mock_dbos.workflow_id = "wf-test"
            mock_gate = MagicMock()
            mock_gate_cls.return_value = mock_gate

            fact_check_import_workflow.__wrapped__(
                batch_job_id=batch_job_id,
                batch_size=100,
                dry_run=False,
                enqueue_scrapes=False,
            )

            mock_gate_cls.assert_called_once_with(
                pool="default", weight=WorkflowWeight.IMPORT_PIPELINE
            )
            mock_gate.acquire.assert_called_once()
            mock_gate.release.assert_called_once()

    def test_scrape_candidates_acquires_and_releases(self) -> None:
        from src.dbos_workflows.import_workflow import scrape_candidates_workflow

        batch_job_id = str(uuid4())

        with (
            patch("src.dbos_workflows.import_workflow.TokenGate") as mock_gate_cls,
            patch(
                "src.dbos_workflows.import_workflow.recover_and_count_scrape_step",
                return_value={"recovered": 0, "total_candidates": 0},
            ),
            patch("src.dbos_workflows.import_workflow.finalize_batch_job_sync", return_value=True),
            patch("src.dbos_workflows.import_workflow.DBOS") as mock_dbos,
        ):
            mock_dbos.workflow_id = "wf-test"
            mock_gate = MagicMock()
            mock_gate_cls.return_value = mock_gate

            scrape_candidates_workflow.__wrapped__(
                batch_job_id=batch_job_id,
                batch_size=100,
                dry_run=True,
            )

            mock_gate_cls.assert_called_once_with(
                pool="default", weight=WorkflowWeight.IMPORT_PIPELINE
            )
            mock_gate.acquire.assert_called_once()
            mock_gate.release.assert_called_once()

    def test_promote_candidates_acquires_and_releases(self) -> None:
        from src.dbos_workflows.import_workflow import promote_candidates_workflow

        batch_job_id = str(uuid4())

        with (
            patch("src.dbos_workflows.import_workflow.TokenGate") as mock_gate_cls,
            patch(
                "src.dbos_workflows.import_workflow.recover_and_count_promote_step",
                return_value={"recovered": 0, "total_candidates": 0},
            ),
            patch("src.dbos_workflows.import_workflow.finalize_batch_job_sync", return_value=True),
            patch("src.dbos_workflows.import_workflow.DBOS") as mock_dbos,
        ):
            mock_dbos.workflow_id = "wf-test"
            mock_gate = MagicMock()
            mock_gate_cls.return_value = mock_gate

            promote_candidates_workflow.__wrapped__(
                batch_job_id=batch_job_id,
                batch_size=100,
                dry_run=True,
            )

            mock_gate_cls.assert_called_once_with(
                pool="default", weight=WorkflowWeight.IMPORT_PIPELINE
            )
            mock_gate.acquire.assert_called_once()
            mock_gate.release.assert_called_once()


class TestApprovalTokenGated:
    def test_bulk_approval_acquires_and_releases(self) -> None:
        from src.dbos_workflows.approval_workflow import bulk_approval_workflow

        batch_job_id = str(uuid4())

        with (
            patch("src.dbos_workflows.approval_workflow.TokenGate") as mock_gate_cls,
            patch(
                "src.dbos_workflows.approval_workflow.count_approval_candidates_step",
                return_value=0,
            ),
            patch("src.dbos_workflows.approval_workflow.start_batch_job_sync", return_value=True),
            patch(
                "src.dbos_workflows.approval_workflow.finalize_batch_job_sync", return_value=True
            ),
            patch("src.dbos_workflows.approval_workflow.DBOS") as mock_dbos,
        ):
            mock_dbos.workflow_id = "wf-test"
            mock_gate = MagicMock()
            mock_gate_cls.return_value = mock_gate

            bulk_approval_workflow.__wrapped__(
                batch_job_id=batch_job_id,
                threshold=0.9,
                auto_promote=False,
                limit=100,
                status=None,
                dataset_name=None,
                dataset_tags=None,
                has_content=None,
                published_date_from=None,
                published_date_to=None,
            )

            mock_gate_cls.assert_called_once_with(pool="default", weight=WorkflowWeight.APPROVAL)
            mock_gate.acquire.assert_called_once()
            mock_gate.release.assert_called_once()


class TestContentMonitoringTokenGated:
    def test_ai_note_generation_acquires_and_releases(self) -> None:
        from src.dbos_workflows.content_monitoring_workflows import (
            ai_note_generation_workflow,
        )

        with (
            patch("src.dbos_workflows.content_monitoring_workflows.TokenGate") as mock_gate_cls,
            patch(
                "src.dbos_workflows.content_monitoring_workflows.generate_ai_note_step",
                return_value={"status": "completed"},
            ),
            patch("src.dbos_workflows.content_monitoring_workflows.DBOS") as mock_dbos,
        ):
            mock_dbos.workflow_id = "wf-test"
            mock_gate = MagicMock()
            mock_gate_cls.return_value = mock_gate

            ai_note_generation_workflow.__wrapped__(
                community_server_id="platform123",
                request_id="req123",
                content="test content",
                scan_type="similarity",
            )

            mock_gate_cls.assert_called_once_with(
                pool="default", weight=WorkflowWeight.CONTENT_MONITORING
            )
            mock_gate.acquire.assert_called_once()
            mock_gate.release.assert_called_once()

    def test_vision_description_acquires_and_releases(self) -> None:
        from src.dbos_workflows.content_monitoring_workflows import (
            vision_description_workflow,
        )

        with (
            patch("src.dbos_workflows.content_monitoring_workflows.TokenGate") as mock_gate_cls,
            patch(
                "src.dbos_workflows.content_monitoring_workflows.generate_vision_description_step",
                return_value={"status": "completed"},
            ),
            patch("src.dbos_workflows.content_monitoring_workflows.DBOS") as mock_dbos,
        ):
            mock_dbos.workflow_id = "wf-test"
            mock_gate = MagicMock()
            mock_gate_cls.return_value = mock_gate

            vision_description_workflow.__wrapped__(
                message_archive_id=str(uuid4()),
                image_url="https://example.com/image.jpg",
                community_server_id="platform123",
            )

            mock_gate_cls.assert_called_once_with(
                pool="default", weight=WorkflowWeight.CONTENT_MONITORING
            )
            mock_gate.acquire.assert_called_once()
            mock_gate.release.assert_called_once()


class TestSimulationOrchestratorTokenGated:
    def test_run_orchestrator_acquires_and_releases(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import run_orchestrator

        simulation_run_id = str(uuid4())

        with (
            patch("src.simulation.workflows.orchestrator_workflow.TokenGate") as mock_gate_cls,
            patch(
                "src.simulation.workflows.orchestrator_workflow.initialize_run_step",
                side_effect=RuntimeError("init fail"),
            ),
            patch("src.simulation.workflows.orchestrator_workflow.DBOS") as mock_dbos,
        ):
            mock_dbos.workflow_id = "wf-test"
            mock_gate = MagicMock()
            mock_gate_cls.return_value = mock_gate

            result = run_orchestrator.__wrapped__(simulation_run_id=simulation_run_id)

            assert result["status"] == "failed"
            mock_gate_cls.assert_called_once_with(
                pool="default", weight=WorkflowWeight.SIMULATION_ORCHESTRATOR
            )
            mock_gate.acquire.assert_called_once()
            mock_gate.release.assert_called_once()


class TestSimulationTurnTokenGated:
    def test_run_agent_turn_acquires_and_releases(self) -> None:
        from src.simulation.workflows.agent_turn_workflow import run_agent_turn

        agent_instance_id = str(uuid4())

        with (
            patch("src.simulation.workflows.agent_turn_workflow.TokenGate") as mock_gate_cls,
            patch(
                "src.simulation.workflows.agent_turn_workflow.load_agent_context_step",
                return_value={
                    "agent_instance_id": agent_instance_id,
                    "message_history": [],
                    "instance_turn_count": 0,
                    "memory_compaction_strategy": "none",
                    "memory_compaction_config": None,
                    "community_server_id": None,
                    "memory_id": None,
                    "model_name": "test",
                    "personality": "test",
                    "model_params": {},
                    "user_profile_id": str(uuid4()),
                    "agent_profile_id": str(uuid4()),
                    "simulation_run_id": str(uuid4()),
                    "recent_actions": [],
                },
            ),
            patch(
                "src.simulation.workflows.agent_turn_workflow.compact_memory_step",
                return_value={"messages": [], "was_compacted": False},
            ),
            patch(
                "src.simulation.workflows.agent_turn_workflow.build_deps_step",
                return_value={"available_requests": [], "available_notes": []},
            ),
            patch(
                "src.simulation.workflows.agent_turn_workflow.select_action_step",
                return_value={
                    "action_type": "write_note",
                    "reasoning": "test",
                    "phase1_messages": [],
                },
            ),
            patch(
                "src.simulation.workflows.agent_turn_workflow.execute_agent_turn_step",
                return_value={
                    "action": {"action_type": "skip"},
                    "new_messages": [],
                },
            ),
            patch(
                "src.simulation.workflows.agent_turn_workflow.persist_state_step",
                return_value={
                    "agent_instance_id": agent_instance_id,
                    "action_type": "skip",
                    "persisted": True,
                },
            ),
            patch("src.simulation.workflows.agent_turn_workflow.DBOS") as mock_dbos,
        ):
            mock_dbos.workflow_id = "wf-test"
            mock_gate = MagicMock()
            mock_gate_cls.return_value = mock_gate

            result = run_agent_turn.__wrapped__(agent_instance_id=agent_instance_id)

            assert result["persisted"] is True
            mock_gate_cls.assert_called_once_with(
                pool="default", weight=WorkflowWeight.SIMULATION_TURN
            )
            mock_gate.acquire.assert_called_once()
            mock_gate.release.assert_called_once()
