"""Viafoura Tier 2 /interact action tests."""

from __future__ import annotations

from src.jobs.orchestrator import _tier2_actions_for
from src.viafoura import ViafouraSignal
from src.viafoura.tier2_actions import build_viafoura_actions


def _signal() -> ViafouraSignal:
    return ViafouraSignal(
        container_id="12a31037f3c9a94d3cb9fbcaaf84d94f",
        site_domain=None,
        embed_origin="https://cdn.viafoura.net",
        iframe_src=None,
        has_conversations_component=True,
    )


def test_build_viafoura_actions_mounts_expands_and_marks_comments() -> None:
    actions = build_viafoura_actions(_signal())

    assert [action["type"] for action in actions] == [
        "wait",
        "scroll",
        "wait",
        "executeJavascript",
        "wait",
    ]
    script = actions[3]["script"]
    assert 'data-platform-comments' in script
    assert 'data-platform", "viafoura"' in script
    assert "vf-conversations-load-more-button" in script
    assert "viafoura_status:" in script
    assert "commentContainerSelectors" in script
    assert "commentTextFallbackSelectors" in script


def test_tier2_actions_for_dispatches_viafoura_signal() -> None:
    actions = _tier2_actions_for(_signal())

    assert [action["type"] for action in actions] == [
        "wait",
        "scroll",
        "wait",
        "executeJavascript",
        "wait",
    ]
    assert "data-platform-comments" in actions[3]["script"]
