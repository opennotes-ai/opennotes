"""Dispatch-registry integration tests for the TASK-1474 slot handlers.

Verifies that each of the 5 registered handlers (SAFETY_MODERATION,
SAFETY_WEB_RISK, SAFETY_IMAGE_MODERATION, SAFETY_VIDEO_MODERATION,
FACTS_CLAIMS_KNOWN_MISINFO) is reachable via the orchestrator's
`_SECTION_HANDLERS` dict and that `_run_section` calls the handler for
registered slugs while falling back to the empty-data stub for
unregistered slugs.

These are structural tests — they do NOT exercise the handlers' internal
HTTP or DB paths. Handler behavior is covered by each task's own test
file (test_web_risk_worker.py, test_moderation_slot.py, etc.).
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.analyses.schemas import SectionSlug


def test_section_handlers_registry_includes_all_1474_slots() -> None:
    from src.jobs.orchestrator import _SECTION_HANDLERS

    assert SectionSlug.SAFETY_MODERATION in _SECTION_HANDLERS
    assert SectionSlug.SAFETY_WEB_RISK in _SECTION_HANDLERS
    assert SectionSlug.SAFETY_IMAGE_MODERATION in _SECTION_HANDLERS
    assert SectionSlug.SAFETY_VIDEO_MODERATION in _SECTION_HANDLERS
    assert SectionSlug.FACTS_CLAIMS_KNOWN_MISINFO in _SECTION_HANDLERS


def test_section_handlers_are_callable() -> None:
    from src.jobs.orchestrator import _SECTION_HANDLERS

    for slug, handler in _SECTION_HANDLERS.items():
        assert callable(handler), f"handler for {slug} is not callable"


def test_unregistered_slugs_fall_back_to_empty_stub() -> None:
    from src.jobs.orchestrator import _SECTION_HANDLERS

    # The 1473-landed slots that haven't yet been wired to real handlers
    # remain in the empty-stub fallback path.
    assert SectionSlug.TONE_DYNAMICS_FLASHPOINT not in _SECTION_HANDLERS
    assert SectionSlug.TONE_DYNAMICS_SCD not in _SECTION_HANDLERS
    assert SectionSlug.FACTS_CLAIMS_DEDUP not in _SECTION_HANDLERS
    assert SectionSlug.OPINIONS_SENTIMENTS_SENTIMENT not in _SECTION_HANDLERS
    assert SectionSlug.OPINIONS_SENTIMENTS_SUBJECTIVE not in _SECTION_HANDLERS


@pytest.mark.asyncio
async def test_run_section_invokes_registered_handler_and_persists_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.jobs import orchestrator

    captured: dict[str, object] = {}

    async def fake_handler(pool, job_id, task_attempt, payload, settings):
        captured["called"] = True
        captured["job_id"] = job_id
        return {"findings": [{"url": "x", "threat_types": ["MALWARE"]}]}

    async def fake_write_slot(pool, job_id, task_attempt, slug, slot):
        captured["persisted_slug"] = slug
        captured["persisted_data"] = slot.data

    monkeypatch.setitem(
        orchestrator._SECTION_HANDLERS, SectionSlug.SAFETY_WEB_RISK, fake_handler
    )
    monkeypatch.setattr(orchestrator, "write_slot", fake_write_slot)
    monkeypatch.setattr(
        orchestrator, "mark_slot_failed", AsyncMock()
    )

    await orchestrator._run_section(
        pool=object(),
        job_id=uuid4(),
        task_attempt=uuid4(),
        slug=SectionSlug.SAFETY_WEB_RISK,
        payload=object(),
        settings=object(),
    )

    assert captured["called"] is True
    assert captured["persisted_slug"] == SectionSlug.SAFETY_WEB_RISK
    assert captured["persisted_data"] == {
        "findings": [{"url": "x", "threat_types": ["MALWARE"]}]
    }


@pytest.mark.asyncio
async def test_run_section_writes_failed_slot_when_handler_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """On handler exception, write_slot persists state=FAILED with the error.

    Uses write_slot (not mark_slot_failed) because _run_section writes the
    terminal state directly without a preceding RUNNING transition — and
    mark_slot_failed's CAS requires state='running' in the DB (codex P1.1).
    """
    from src.analyses.schemas import SectionState
    from src.jobs import orchestrator

    captured: dict[str, object] = {}

    async def fake_write_slot(pool, job_id, task_attempt, slug, slot):
        captured["slot_state"] = slot.state
        captured["slot_error"] = slot.error
        captured["slot_data"] = slot.data

    async def raising_handler(*args, **kwargs):
        raise RuntimeError("upstream 503")

    monkeypatch.setitem(
        orchestrator._SECTION_HANDLERS, SectionSlug.SAFETY_WEB_RISK, raising_handler
    )
    monkeypatch.setattr(orchestrator, "write_slot", fake_write_slot)

    await orchestrator._run_section(
        pool=object(),
        job_id=uuid4(),
        task_attempt=uuid4(),
        slug=SectionSlug.SAFETY_WEB_RISK,
        payload=object(),
        settings=object(),
    )

    assert captured["slot_state"] == SectionState.FAILED
    assert captured["slot_data"] is None
    assert "upstream 503" in str(captured["slot_error"])


@pytest.mark.asyncio
async def test_run_section_uses_empty_stub_for_unregistered_slug(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.jobs import orchestrator

    captured: dict[str, object] = {}

    async def fake_write_slot(pool, job_id, task_attempt, slug, slot):
        captured["slug"] = slug
        captured["data"] = slot.data

    monkeypatch.setattr(orchestrator, "write_slot", fake_write_slot)

    # TONE_DYNAMICS_FLASHPOINT has no registered handler → empty stub.
    await orchestrator._run_section(
        pool=object(),
        job_id=uuid4(),
        task_attempt=uuid4(),
        slug=SectionSlug.TONE_DYNAMICS_FLASHPOINT,
        payload=object(),
        settings=object(),
    )

    assert captured["slug"] == SectionSlug.TONE_DYNAMICS_FLASHPOINT
    assert captured["data"] == {"flashpoint_matches": []}
