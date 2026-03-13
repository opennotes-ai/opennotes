from __future__ import annotations

import importlib

_LAZY_IMPORTS: dict[str, tuple[str, str]] = {
    "RUN_AGENT_TURN_WORKFLOW_NAME": (
        "src.simulation.workflows.agent_turn_workflow",
        "RUN_AGENT_TURN_WORKFLOW_NAME",
    ),
    "RUN_ORCHESTRATOR_WORKFLOW_NAME": (
        "src.simulation.workflows.orchestrator_workflow",
        "RUN_ORCHESTRATOR_WORKFLOW_NAME",
    ),
    "RUN_PLAYGROUND_URL_EXTRACTION_NAME": (
        "src.simulation.workflows.playground_url_workflow",
        "RUN_PLAYGROUND_URL_EXTRACTION_NAME",
    ),
    "SCORE_COMMUNITY_SERVER_WORKFLOW_NAME": (
        "src.simulation.workflows.scoring_workflow",
        "SCORE_COMMUNITY_SERVER_WORKFLOW_NAME",
    ),
    "dispatch_agent_turn": (
        "src.simulation.workflows.agent_turn_workflow",
        "dispatch_agent_turn",
    ),
    "dispatch_community_scoring": (
        "src.simulation.workflows.scoring_workflow",
        "dispatch_community_scoring",
    ),
    "dispatch_orchestrator": (
        "src.simulation.workflows.orchestrator_workflow",
        "dispatch_orchestrator",
    ),
    "dispatch_playground_url_extraction": (
        "src.simulation.workflows.playground_url_workflow",
        "dispatch_playground_url_extraction",
    ),
    "run_agent_turn": ("src.simulation.workflows.agent_turn_workflow", "run_agent_turn"),
    "run_orchestrator": (
        "src.simulation.workflows.orchestrator_workflow",
        "run_orchestrator",
    ),
    "run_playground_url_extraction": (
        "src.simulation.workflows.playground_url_workflow",
        "run_playground_url_extraction",
    ),
    "score_community_server": (
        "src.simulation.workflows.scoring_workflow",
        "score_community_server",
    ),
}


def __getattr__(name: str) -> object:
    if name in _LAZY_IMPORTS:
        module_path, attr = _LAZY_IMPORTS[name]
        mod = importlib.import_module(module_path)
        val = getattr(mod, attr)
        globals()[name] = val
        return val
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = list(_LAZY_IMPORTS)
