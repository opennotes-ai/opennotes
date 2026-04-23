"""Unit tests for orchestrator internal logic (TASK-1473.59).

The full pipeline integration is covered by test_worker.py (HTTP surface).
These tests focus on internal helpers that are easier to drive in isolation
without standing up Postgres or the FastAPI app.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.analyses.schemas import SectionSlug
from src.jobs.orchestrator import TransientError, _run_section


# ---------------------------------------------------------------------------
# TASK-1473.59 regression — write_slot DB failure must propagate as
# TransientError so Cloud Tasks redelivers.
# ---------------------------------------------------------------------------


async def test_run_section_write_slot_exception_raises_transient_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression test for TASK-1473.59.

    A write_slot DB failure must propagate as TransientError so Cloud
    Tasks redelivers. Previously the except block swallowed the error and
    the job got stuck in analyzing.
    """
    from src.jobs import orchestrator

    async def boom(*args, **kwargs):
        raise RuntimeError("simulated DB failure")

    monkeypatch.setattr(orchestrator, "write_slot", boom)

    mark_slot_called = []

    async def mock_mark_slot_failed(*args, **kwargs):
        mark_slot_called.append(kwargs)
        return 0

    monkeypatch.setattr(orchestrator, "mark_slot_failed", mock_mark_slot_failed)

    pool = MagicMock()
    job_id = uuid4()
    task_attempt = uuid4()
    slug = SectionSlug.SAFETY_MODERATION
    payload = MagicMock()
    settings = MagicMock()

    with pytest.raises(TransientError, match="write_slot failed"):
        await _run_section(pool, job_id, task_attempt, slug, payload, settings)

    assert len(mark_slot_called) == 1, "mark_slot_failed should have been called once"


async def test_run_section_write_slot_exception_still_raises_when_mark_slot_also_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If both write_slot and mark_slot_failed fail, TransientError still
    propagates (the double-failure is logged and suppressed internally).
    """
    from src.jobs import orchestrator

    async def boom(*args, **kwargs):
        raise RuntimeError("simulated DB failure")

    monkeypatch.setattr(orchestrator, "write_slot", boom)
    monkeypatch.setattr(orchestrator, "mark_slot_failed", boom)

    pool = MagicMock()
    job_id = uuid4()
    task_attempt = uuid4()
    slug = SectionSlug.SAFETY_WEB_RISK
    payload = MagicMock()
    settings = MagicMock()

    with pytest.raises(TransientError, match="write_slot failed"):
        await _run_section(pool, job_id, task_attempt, slug, payload, settings)
