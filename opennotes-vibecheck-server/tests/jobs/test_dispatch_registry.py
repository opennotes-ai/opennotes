"""Dispatch-registry integration tests for async vibecheck slot handlers.

Verifies that every SectionSlug is reachable via the orchestrator's
`_SECTION_HANDLERS` dict and that `_run_section` calls registered handlers.

These are structural tests — they do NOT exercise the handlers' internal
HTTP or DB paths. Handler behavior is covered by each task's own test
file (test_web_risk_worker.py, test_moderation_slot.py, etc.).
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.analyses.schemas import SectionSlug
from src.config import Settings


def _settings() -> Settings:
    return Settings()


def test_section_handlers_registry_includes_every_section_slug() -> None:
    from src.jobs.orchestrator import _SECTION_HANDLERS

    assert set(_SECTION_HANDLERS) == set(SectionSlug)


def test_section_handlers_are_callable() -> None:
    from src.jobs.orchestrator import _SECTION_HANDLERS

    for slug, handler in _SECTION_HANDLERS.items():
        assert callable(handler), f"handler for {slug} is not callable"


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
        settings=_settings(),
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
        settings=_settings(),
    )

    assert captured["slot_state"] == SectionState.FAILED
    assert captured["slot_data"] is None
    assert "upstream 503" in str(captured["slot_error"])


@pytest.mark.asyncio
async def test_run_section_invokes_new_tone_handler_instead_of_empty_stub(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.jobs import orchestrator

    captured: dict[str, object] = {}

    async def fake_handler(pool, job_id, task_attempt, payload, settings):
        return {"flashpoint_matches": [{"utterance_id": "u-2"}]}

    async def fake_write_slot(pool, job_id, task_attempt, slug, slot):
        captured["slug"] = slug
        captured["data"] = slot.data

    monkeypatch.setitem(
        orchestrator._SECTION_HANDLERS,
        SectionSlug.TONE_DYNAMICS_FLASHPOINT,
        fake_handler,
    )
    monkeypatch.setattr(orchestrator, "write_slot", fake_write_slot)

    await orchestrator._run_section(
        pool=object(),
        job_id=uuid4(),
        task_attempt=uuid4(),
        slug=SectionSlug.TONE_DYNAMICS_FLASHPOINT,
        payload=object(),
        settings=_settings(),
    )

    assert captured["slug"] == SectionSlug.TONE_DYNAMICS_FLASHPOINT
    assert captured["data"] == {"flashpoint_matches": [{"utterance_id": "u-2"}]}
