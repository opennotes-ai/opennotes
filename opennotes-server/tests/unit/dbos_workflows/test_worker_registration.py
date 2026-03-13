"""Tests for DBOS workflow registration in worker mode."""

from __future__ import annotations

import ast
import importlib
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _build_torch_stub() -> ModuleType:
    torch_module = ModuleType("torch")
    nn_module = ModuleType("torch.nn")
    parameter_module = ModuleType("torch.nn.parameter")
    init_module = ModuleType("torch.nn.init")
    utils_module = ModuleType("torch.nn.utils")
    optim_module = ModuleType("torch.optim")
    cuda_module = ModuleType("torch.cuda")

    class _Module:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

    class _Callable:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

        def __call__(self, *_args: object, **_kwargs: object) -> MagicMock:
            return MagicMock()

    nn_module.Module = _Module
    nn_module.Embedding = _Callable
    nn_module.BCEWithLogitsLoss = _Callable
    nn_module.MSELoss = _Callable
    nn_module.Sigmoid = _Callable
    nn_module.Parameter = lambda *_args, **_kwargs: MagicMock()
    nn_module.parameter = parameter_module
    nn_module.init = init_module
    nn_module.utils = utils_module
    nn_module.modules = SimpleNamespace(loss=SimpleNamespace(_Loss=object))

    parameter_module.Parameter = nn_module.Parameter
    init_module.xavier_uniform_ = lambda *_args, **_kwargs: None
    utils_module.clip_grad_norm_ = lambda *_args, **_kwargs: None
    optim_module.Adam = _Callable
    cuda_module.is_available = lambda: False

    torch_module.nn = nn_module
    torch_module.optim = optim_module
    torch_module.cuda = cuda_module
    torch_module.backends = SimpleNamespace(mps=SimpleNamespace(is_available=lambda: False))
    torch_module.Tensor = object
    torch_module.FloatTensor = object
    torch_module.IntTensor = object
    torch_module.LongTensor = object
    torch_module.float32 = object()
    torch_module.device = lambda name="cpu", *_args, **_kwargs: name
    torch_module.tensor = lambda *_args, **_kwargs: MagicMock()
    torch_module.zeros = lambda *_args, **_kwargs: MagicMock()
    torch_module.ones = lambda *_args, **_kwargs: MagicMock()
    torch_module.from_numpy = lambda *_args, **_kwargs: MagicMock()
    torch_module.isnan = lambda *_args, **_kwargs: MagicMock(any=lambda: False)
    torch_module.manual_seed = lambda *_args, **_kwargs: None
    torch_module.set_num_threads = lambda *_args, **_kwargs: None
    torch_module.get_num_threads = lambda: 1

    return torch_module


@pytest.fixture
def main_module(monkeypatch: pytest.MonkeyPatch):
    torch_stub = _build_torch_stub()

    monkeypatch.setitem(sys.modules, "torch", torch_stub)
    monkeypatch.setitem(sys.modules, "torch.nn", torch_stub.nn)
    monkeypatch.setitem(sys.modules, "torch.nn.parameter", torch_stub.nn.parameter)
    monkeypatch.setitem(sys.modules, "torch.nn.init", torch_stub.nn.init)
    monkeypatch.setitem(sys.modules, "torch.nn.utils", torch_stub.nn.utils)
    monkeypatch.setitem(sys.modules, "torch.optim", torch_stub.optim)
    monkeypatch.setitem(sys.modules, "torch.cuda", torch_stub.cuda)

    sys.modules.pop("src.main", None)

    imported_main_module = importlib.import_module("src.main")
    return importlib.reload(imported_main_module)


class TestWorkerWorkflowRegistration:
    """Verify workflows are registered when SERVER_MODE=dbos_worker."""

    def test_discover_dbos_workflow_modules_reports_parse_errors_with_module_context(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        main_module,
    ) -> None:
        fake_src_root = tmp_path / "src"
        dbos_workflows_root = fake_src_root / "dbos_workflows"
        simulation_workflows_root = fake_src_root / "simulation" / "workflows"
        dbos_workflows_root.mkdir(parents=True)
        simulation_workflows_root.mkdir(parents=True)
        fake_main = fake_src_root / "main.py"
        fake_main.write_text("# stub main file\n", encoding="utf-8")

        (dbos_workflows_root / "healthy.py").write_text(
            "from dbos import DBOS\n"
            "@DBOS.workflow()\n"
            "def healthy_workflow() -> None:\n"
            "    return None\n",
            encoding="utf-8",
        )
        (dbos_workflows_root / "broken.py").write_text(
            "from dbos import DBOS\n@DBOS.workflow()\ndef broken_workflow(\n",
            encoding="utf-8",
        )

        monkeypatch.setattr(main_module, "__file__", str(fake_main))

        discovery = main_module._discover_dbos_workflow_modules()

        assert [
            (module.module_path, module.workflow_names) for module in discovery.discovered_modules
        ] == [("src.dbos_workflows.healthy", ("healthy_workflow",))]
        assert discovery.errors == [
            "Failed to inspect workflow module src.dbos_workflows.broken "
            f"({dbos_workflows_root / 'broken.py'}): "
            "SyntaxError: '(' was never closed (<unknown>, line 3)"
        ]

    def test_register_dbos_workflows_raises_when_any_dispatchable_workflow_is_missing(
        self,
        main_module,
    ) -> None:
        real_import_module = importlib.import_module
        fake_root = Path("/tmp/fake-workflows")

        def healthy_workflow() -> None:
            return None

        healthy_workflow.__qualname__ = "healthy_workflow"
        healthy_module = SimpleNamespace(healthy_workflow=healthy_workflow)
        missing_module = SimpleNamespace()

        def fake_import_module(module_path: str) -> object:
            if module_path == "src.fake.good":
                return healthy_module
            if module_path == "src.fake.missing":
                return missing_module
            return real_import_module(module_path)

        with (
            pytest.raises(RuntimeError) as exc_info,
            patch(
                "src.main._discover_dbos_workflow_modules",
                return_value=main_module.DiscoveredDBOSWorkflowModules(
                    discovered_modules=[
                        main_module.DiscoveredDBOSWorkflowModule(
                            module_path="src.fake.good",
                            module_file=fake_root / "good.py",
                            workflow_names=("healthy_workflow",),
                        ),
                        main_module.DiscoveredDBOSWorkflowModule(
                            module_path="src.fake.missing",
                            module_file=fake_root / "missing.py",
                            workflow_names=("missing_workflow",),
                        ),
                    ],
                    errors=[],
                ),
            ),
            patch("importlib.import_module", side_effect=fake_import_module),
        ):
            main_module._register_dbos_workflows()

        message = str(exc_info.value)
        assert "Workflow registration incomplete" in message
        assert "src.fake.missing" in message
        assert str(fake_root / "missing.py") in message
        assert "missing_workflow" in message

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
    async def test_workflow_modules_imported_in_worker_mode(self, main_module) -> None:
        """_init_dbos imports workflow modules before launch() in worker mode."""
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

            await main_module._init_dbos(is_dbos_worker=True)

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
    async def test_worker_mode_fails_before_launch_when_workflow_registration_is_incomplete(
        self,
        main_module,
    ) -> None:
        """Worker mode must abort startup before launch if workflow registration fails."""
        with (
            patch("src.main.settings") as mock_settings,
            patch("src.main.get_dbos") as mock_get_dbos,
            patch("src.main.validate_dbos_connection"),
            patch("src.main.logger") as mock_logger,
            patch(
                "src.main._register_dbos_workflows",
                side_effect=RuntimeError("Workflow registration incomplete"),
            ),
        ):
            mock_settings.TESTING = False
            mock_settings.DBOS_CONDUCTOR_KEY = None
            mock_dbos = MagicMock()
            mock_get_dbos.return_value = mock_dbos

            with pytest.raises(
                RuntimeError,
                match="DBOS initialization failed: Workflow registration incomplete",
            ):
                await main_module._init_dbos(is_dbos_worker=True)

            mock_dbos.launch.assert_not_called()

            info_messages = [str(call) for call in mock_logger.info.call_args_list]
            assert not any("DBOS workflow modules loaded" in message for message in info_messages)
            assert not any(
                "DBOS worker mode - queue polling enabled and validated" in message
                for message in info_messages
            )

    @pytest.mark.asyncio
    async def test_server_mode_does_not_import_workflows(self, main_module) -> None:
        """Server mode (is_dbos_worker=False) does not import workflow modules."""
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

            await main_module._init_dbos(is_dbos_worker=False)

            mock_listen_queues.assert_called_once_with([])
            mock_dbos.launch.assert_called_once()

            log_calls = [
                call
                for call in mock_logger.info.call_args_list
                if "workflow modules loaded" in str(call)
            ]
            assert len(log_calls) == 0, "Server mode should not log workflow module loading"

    @pytest.mark.asyncio
    async def test_workflow_import_happens_before_launch(self, main_module) -> None:
        """Workflow module import must happen before dbos.launch()."""
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

            await main_module._init_dbos(is_dbos_worker=True)

            assert call_order == ["import_logged", "launch_called"], (
                f"Import must happen before launch. Actual order: {call_order}"
            )
