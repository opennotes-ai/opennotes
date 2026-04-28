from __future__ import annotations

import asyncio
import threading
from typing import Any

import pytest
from pydantic import ValidationError

from src.config import Settings
from src.services import vertex_limiter
from src.services.vertex_limiter import vertex_slot


async def test_vertex_slot_waits_for_single_global_slot(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(VERTEX_MAX_CONCURRENCY=1)
    entered_first = asyncio.Event()
    release_first = asyncio.Event()
    second_attempted = asyncio.Event()
    entered_second = asyncio.Event()

    async def first_worker() -> None:
        async with vertex_slot(settings):
            entered_first.set()
            await release_first.wait()

    async def second_worker() -> None:
        second_attempted.set()
        async with vertex_slot(settings):
            entered_second.set()

    first_task = asyncio.create_task(first_worker())
    await entered_first.wait()

    second_task = asyncio.create_task(second_worker())
    await second_attempted.wait()
    await asyncio.sleep(0)

    assert not entered_second.is_set()

    release_first.set()
    await entered_second.wait()
    await asyncio.gather(first_task, second_task)


async def test_vertex_slot_records_wait_ms(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded: dict[str, Any] = {}

    class _RecordingSpan:
        def __enter__(self) -> _RecordingSpan:
            return self

        def __exit__(self, *_args: Any) -> None:
            return None

        def set_attribute(self, key: str, value: Any) -> None:
            recorded[key] = value

    def _fake_span(_name: str, **_attrs: Any) -> _RecordingSpan:
        return _RecordingSpan()

    monkeypatch.setattr(vertex_limiter.logfire, "span", _fake_span)

    async with vertex_slot(Settings(VERTEX_MAX_CONCURRENCY=17)):
        pass

    assert isinstance(recorded["vertex_limiter.wait_ms"], float)
    assert recorded["vertex_limiter.wait_ms"] >= 0.0


async def test_vertex_slot_rejects_cap_change_while_slot_is_active() -> None:
    async with vertex_slot(Settings(VERTEX_MAX_CONCURRENCY=1)):
        with pytest.raises(RuntimeError, match="VERTEX_MAX_CONCURRENCY changed"):
            async with vertex_slot(Settings(VERTEX_MAX_CONCURRENCY=2)):
                pass


async def test_vertex_slot_reserves_pending_state_before_returning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_state_for = vertex_limiter._limiter_state_for
    selected_state = threading.Event()
    release_first = threading.Event()
    errors: list[BaseException] = []

    def _paused_state_for(
        limit: int, loop: asyncio.AbstractEventLoop
    ) -> vertex_limiter._LimiterState:
        state = original_state_for(limit, loop)
        if limit == 1:
            selected_state.set()
            release_first.wait(timeout=1.0)
        return state

    async def _first_caller() -> None:
        async with vertex_slot(Settings(VERTEX_MAX_CONCURRENCY=1)):
            pass

    def _run_first_caller() -> None:
        try:
            asyncio.run(_first_caller())
        except BaseException as exc:  # pragma: no cover - asserted after join
            errors.append(exc)

    monkeypatch.setattr(vertex_limiter, "_limiter_state_for", _paused_state_for)

    first_thread = threading.Thread(target=_run_first_caller)
    first_thread.start()
    assert selected_state.wait(timeout=1.0)

    try:
        with pytest.raises(RuntimeError, match="active or waiting"):
            async with vertex_slot(Settings(VERTEX_MAX_CONCURRENCY=2)):
                pass
    finally:
        release_first.set()
        first_thread.join(timeout=1.0)

    assert not first_thread.is_alive()
    assert errors == []


def test_settings_rejects_non_positive_vertex_max_concurrency() -> None:
    with pytest.raises(ValidationError, match="VERTEX_MAX_CONCURRENCY"):
        Settings(VERTEX_MAX_CONCURRENCY=0)
