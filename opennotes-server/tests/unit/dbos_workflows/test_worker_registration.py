"""Tests for DBOS workflow registration in worker mode."""

from __future__ import annotations

import ast
import importlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestWorkerWorkflowRegistration:
    """Verify workflows are registered when SERVER_MODE=dbos_worker."""

    def test_register_dbos_workflows_discovers_workflow_names_even_if_exports_are_missing(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from src import dbos_workflows
        from src.main import _register_dbos_workflows
        from src.simulation import workflows as simulation_workflows

        monkeypatch.delattr(
            dbos_workflows,
            "CLEANUP_STALE_TOKEN_HOLDS_WORKFLOW_NAME",
            raising=True,
        )
        monkeypatch.delattr(
            simulation_workflows,
            "SCORE_COMMUNITY_SERVER_WORKFLOW_NAME",
            raising=True,
        )

        registered = set(_register_dbos_workflows())

        assert "cleanup_stale_token_holds" in registered
        assert "score_community_server" in registered
        assert "run_agent_turn" in registered

    def test_register_dbos_workflows_isolates_broken_module_imports(self) -> None:
        from src.main import _register_dbos_workflows

        real_import_module = importlib.import_module

        def healthy_workflow() -> None:
            return None

        healthy_workflow.__qualname__ = "healthy_workflow"
        healthy_module = SimpleNamespace(healthy_workflow=healthy_workflow)

        def fake_import_module(module_path: str) -> object:
            if module_path == "src.fake.good":
                return healthy_module
            if module_path == "src.fake.bad":
                raise RuntimeError("boom")
            return real_import_module(module_path)

        with (
            patch(
                "src.main._discover_dbos_workflow_modules",
                return_value=[
                    ("src.fake.good", ("healthy_workflow",)),
                    ("src.fake.bad", ("broken_workflow",)),
                ],
            ),
            patch("importlib.import_module", side_effect=fake_import_module),
            patch("src.main.logger") as mock_logger,
        ):
            registered = _register_dbos_workflows()

        assert registered == ["healthy_workflow"]
        mock_logger.error.assert_called_once()

    def test_workflow_packages_avoid_eager_submodule_imports(self) -> None:
        src_root = Path(__file__).resolve().parents[3] / "src"
        init_files = [
            src_root / "dbos_workflows" / "__init__.py",
            src_root / "simulation" / "workflows" / "__init__.py",
        ]

        for init_file in init_files:
            tree = ast.parse(init_file.read_text())
            eager_imports = [
                node.module
                for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom)
                and node.module
                and (
                    node.module.startswith("src.dbos_workflows")
                    or node.module.startswith("src.simulation.workflows")
                )
            ]
            assert eager_imports == [], f"{init_file} still eagerly imports {eager_imports}"

    @pytest.mark.asyncio
    async def test_workflow_modules_imported_in_worker_mode(self) -> None:
        """_init_dbos imports workflow modules before launch() in worker mode."""
        from src.main import _init_dbos

        with (
            patch("src.main.settings") as mock_settings,
            patch("src.main.get_dbos") as mock_get_dbos,
            patch("src.main.validate_dbos_connection"),
            patch("src.main.logger") as mock_logger,
            patch("src.main.asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread,
            patch(
                "src.dbos_workflows.token_bucket.config.ensure_pool_exists_async",
                new_callable=AsyncMock,
            ),
            patch(
                "src.dbos_workflows.token_bucket.config.register_worker_async",
                new_callable=AsyncMock,
            ),
            patch(
                "src.dbos_workflows.token_bucket.config.start_worker_heartbeat",
                new_callable=AsyncMock,
            ),
            patch(
                "src.bulk_content_scan.flashpoint_service.get_flashpoint_service",
                return_value=MagicMock(),
            ),
        ):
            mock_settings.TESTING = False
            mock_settings.DBOS_CONDUCTOR_KEY = None
            mock_dbos = MagicMock()
            mock_get_dbos.return_value = mock_dbos
            mock_to_thread.return_value = True

            await _init_dbos(is_dbos_worker=True)

            mock_dbos.launch.assert_called_once()

            log_calls = [
                call
                for call in mock_logger.info.call_args_list
                if "workflow modules loaded" in str(call)
            ]
            assert len(log_calls) == 1, "Expected 'DBOS workflow modules loaded' log message"

            log_call = log_calls[0]
            assert "extra" in log_call.kwargs
            assert "registered_workflows" in log_call.kwargs["extra"]
            workflows = log_call.kwargs["extra"]["registered_workflows"]
            workflow_names = {w.rsplit(".", 1)[-1] for w in workflows}
            expected = {
                "rechunk_fact_check_workflow",
                "chunk_single_fact_check_workflow",
                "rechunk_previously_seen_workflow",
                "content_scan_orchestration_workflow",
                "process_content_scan_batch",
                "ai_note_generation_workflow",
                "vision_description_workflow",
                "_audit_log_wrapper_workflow",
                "cleanup_stale_batch_jobs_workflow",
                "monitor_stuck_batch_jobs_workflow",
                "fact_check_import_workflow",
                "scrape_candidates_workflow",
                "promote_candidates_workflow",
                "bulk_approval_workflow",
                "cleanup_stale_token_holds",
                "run_agent_turn",
                "run_orchestrator",
                "run_playground_url_extraction",
                "score_community_server",
            }
            assert workflow_names == expected

    @pytest.mark.asyncio
    async def test_server_mode_does_not_import_workflows(self) -> None:
        """Server mode (is_dbos_worker=False) does not import workflow modules."""
        from src.main import _init_dbos

        with (
            patch("src.main.settings") as mock_settings,
            patch("src.main.get_dbos") as mock_get_dbos,
            patch("src.main.validate_dbos_connection"),
            patch("src.main.logger") as mock_logger,
            patch("src.main.asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread,
            patch("dbos.DBOS.listen_queues") as mock_listen_queues,
        ):
            mock_settings.TESTING = False
            mock_settings.DBOS_CONDUCTOR_KEY = None
            mock_dbos = MagicMock()
            mock_get_dbos.return_value = mock_dbos
            mock_to_thread.return_value = True

            await _init_dbos(is_dbos_worker=False)

            mock_listen_queues.assert_called_once_with([])
            mock_dbos.launch.assert_called_once()

            log_calls = [
                call
                for call in mock_logger.info.call_args_list
                if "workflow modules loaded" in str(call)
            ]
            assert len(log_calls) == 0, "Server mode should not log workflow module loading"

    @pytest.mark.asyncio
    async def test_workflow_import_happens_before_launch(self) -> None:
        """Workflow module import must happen before dbos.launch()."""
        from src.main import _init_dbos

        call_order: list[str] = []

        def track_launch() -> None:
            call_order.append("launch_called")

        def tracking_info(msg: str, *args: object, **kwargs: object) -> None:
            if "workflow modules loaded" in msg:
                call_order.append("import_logged")

        with (
            patch("src.main.settings") as mock_settings,
            patch("src.main.get_dbos") as mock_get_dbos,
            patch("src.main.validate_dbos_connection"),
            patch("src.main.logger") as mock_logger,
            patch("src.main.asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread,
            patch(
                "src.dbos_workflows.token_bucket.config.ensure_pool_exists_async",
                new_callable=AsyncMock,
            ),
            patch(
                "src.dbos_workflows.token_bucket.config.register_worker_async",
                new_callable=AsyncMock,
            ),
            patch(
                "src.dbos_workflows.token_bucket.config.start_worker_heartbeat",
                new_callable=AsyncMock,
            ),
            patch(
                "src.bulk_content_scan.flashpoint_service.get_flashpoint_service",
                return_value=MagicMock(),
            ),
        ):
            mock_settings.TESTING = False
            mock_settings.DBOS_CONDUCTOR_KEY = None
            mock_dbos = MagicMock()
            mock_dbos.launch.side_effect = track_launch
            mock_get_dbos.return_value = mock_dbos
            mock_to_thread.return_value = True
            mock_logger.info.side_effect = tracking_info

            await _init_dbos(is_dbos_worker=True)

            assert call_order == ["import_logged", "launch_called"], (
                f"Import must happen before launch. Actual order: {call_order}"
            )
