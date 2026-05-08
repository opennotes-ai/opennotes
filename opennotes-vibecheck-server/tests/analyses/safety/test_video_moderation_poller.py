from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.analyses.safety import video_moderation_poller
from src.analyses.safety.video_intelligence_client import OperationStatus
from src.analyses.safety.video_moderation_poller import (
    VideoModerationPollPayload,
    video_moderation_poll,
)
from src.config import Settings


class _Pool:
    def __init__(self, slot: dict[str, Any] | None) -> None:
        self.slot = slot

    def acquire(self):
        pool = self

        class _Conn:
            async def fetchrow(self, *_args):
                return {"slot": pool.slot}

        class _CM:
            async def __aenter__(self):
                return _Conn()

            async def __aexit__(self, *_exc):
                return False

        return _CM()


def _payload(job_id, task_attempt, slot_attempt) -> VideoModerationPollPayload:
    return VideoModerationPollPayload(
        job_id=job_id,
        task_attempt=task_attempt,
        slot_attempt=slot_attempt,
    )


def _slot(slot_attempt, *, started_at: datetime | None = None) -> dict[str, Any]:
    return {
        "state": "running",
        "attempt_id": str(slot_attempt),
        "data": {
            "status": "polling",
            "started_at": (started_at or datetime.now(UTC)).isoformat(),
            "operations": [
                {
                    "operation_name": "operations/1",
                    "staging_uri": "gs://bucket/a.mp4",
                    "video_url": "https://example.com/a.mp4",
                    "utterance_id": "utt-1",
                }
            ],
        },
    }


@pytest.mark.asyncio
async def test_pending_operation_reenqueues_poll(monkeypatch: pytest.MonkeyPatch) -> None:
    job_id = uuid4()
    task_attempt = uuid4()
    slot_attempt = uuid4()
    enqueue = AsyncMock()
    monkeypatch.setattr(video_moderation_poller, "get_access_token", lambda _scope: "token")
    monkeypatch.setattr(video_moderation_poller, "enqueue_video_moderation_poll", enqueue)
    monkeypatch.setattr(
        video_moderation_poller,
        "get_operation",
        AsyncMock(return_value=OperationStatus("operations/1", False, None, None)),
    )

    result = await video_moderation_poll(
        _payload(job_id, task_attempt, slot_attempt),
        pool=_Pool(_slot(slot_attempt)),
        settings=Settings(),
    )

    assert result == "pending"
    enqueue.assert_awaited_once()


@pytest.mark.asyncio
async def test_done_operation_marks_slot_done(monkeypatch: pytest.MonkeyPatch) -> None:
    job_id = uuid4()
    task_attempt = uuid4()
    slot_attempt = uuid4()
    mark_done = AsyncMock(return_value=1)
    monkeypatch.setattr(video_moderation_poller, "get_access_token", lambda _scope: "token")
    monkeypatch.setattr(video_moderation_poller, "mark_slot_done", mark_done)
    monkeypatch.setattr(video_moderation_poller, "maybe_finalize_job", AsyncMock())
    monkeypatch.setattr(video_moderation_poller, "_cleanup_staged_objects", AsyncMock())
    monkeypatch.setattr(
        video_moderation_poller,
        "get_operation",
        AsyncMock(return_value=OperationStatus(
            "operations/1",
            True,
            None,
            {
                "annotationResults": [
                    {
                        "explicitAnnotation": {
                            "frames": [
                                {
                                    "timeOffset": "1.000s",
                                    "pornographyLikelihood": "VERY_LIKELY",
                                }
                            ]
                        }
                    }
                ]
            },
        )),
    )

    result = await video_moderation_poll(
        _payload(job_id, task_attempt, slot_attempt),
        pool=_Pool(_slot(slot_attempt)),
        settings=Settings(),
    )

    assert result == "done"
    assert mark_done.await_args is not None
    data = mark_done.await_args.args[4]
    assert data["matches"][0]["segment_findings"][0]["start_offset_ms"] == 1000
    assert data["matches"][0]["flagged"] is True


@pytest.mark.asyncio
async def test_timeout_marks_slot_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    job_id = uuid4()
    task_attempt = uuid4()
    slot_attempt = uuid4()
    mark_failed = AsyncMock(return_value=1)
    monkeypatch.setattr(video_moderation_poller, "get_access_token", lambda _scope: "token")
    monkeypatch.setattr(video_moderation_poller, "mark_slot_failed", mark_failed)
    monkeypatch.setattr(video_moderation_poller, "maybe_finalize_job", AsyncMock())
    monkeypatch.setattr(video_moderation_poller, "_cleanup_staged_objects", AsyncMock())
    monkeypatch.setattr(
        video_moderation_poller,
        "get_operation",
        AsyncMock(return_value=OperationStatus("operations/1", False, None, None)),
    )

    result = await video_moderation_poll(
        _payload(job_id, task_attempt, slot_attempt),
        pool=_Pool(_slot(slot_attempt, started_at=datetime.now(UTC) - timedelta(hours=1))),
        settings=Settings(VIDEO_MODERATION_MAX_WAIT_SEC=1),
    )

    assert result == "failed"
    assert mark_failed.await_args is not None
    assert "operations/1" in mark_failed.await_args.kwargs["error"]


@pytest.mark.asyncio
async def test_terminal_slot_exits_cleanly() -> None:
    result = await video_moderation_poll(
        _payload(uuid4(), uuid4(), uuid4()),
        pool=_Pool({"state": "done", "attempt_id": str(uuid4())}),
        settings=Settings(),
    )

    assert result == "stale"
