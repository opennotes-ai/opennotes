"""Tests for DBOS workflow registration in worker mode."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestWorkerWorkflowRegistration:
    """Verify workflows are registered when SERVER_MODE=dbos_worker."""

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
            assert len(workflows) == 7
            workflow_names = {w.rsplit(".", 1)[-1] for w in workflows}
            expected = {
                "rechunk_fact_check_workflow",
                "chunk_single_fact_check_workflow",
                "content_scan_orchestration_workflow",
                "process_content_scan_batch",
                "ai_note_generation_workflow",
                "vision_description_workflow",
                "_audit_log_wrapper_workflow",
            }
            assert workflow_names == expected

    @pytest.mark.asyncio
    async def test_server_mode_does_not_import_workflows(self) -> None:
        """Server mode (is_dbos_worker=False) does not import workflow modules."""
        from src.main import _init_dbos

        with (
            patch("src.main.settings") as mock_settings,
            patch("src.main.get_dbos_client") as mock_get_client,
            patch("src.main.logger") as mock_logger,
        ):
            mock_settings.TESTING = False
            mock_settings.DBOS_CONDUCTOR_KEY = None
            mock_get_client.return_value = MagicMock()

            await _init_dbos(is_dbos_worker=False)

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
