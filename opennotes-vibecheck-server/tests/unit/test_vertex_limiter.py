from __future__ import annotations

import asyncio
import threading
from typing import Any

import pytest
from pydantic import ValidationError

from src.config import Settings
from src.services import vertex_limiter
from src.services.vertex_limiter import vertex_slot


class _SharedFakeRedis:
    def __init__(self) -> None:
        self.tokens: set[str] = set()
        self.loaded_scripts: list[str] = []

    async def script_load(self, script: str) -> str:
        self.loaded_scripts.append(script)
        return "release" if "not_owner_or_expired" in script else "acquire"

    async def evalsha(self, sha: str, numkeys: int, *args: Any) -> list[Any]:
        assert numkeys == 2
        if sha == "acquire":
            token = str(args[2])
            limit = int(args[3])
            lease_ttl_ms = int(args[4])
            if len(self.tokens) >= limit:
                return [0, len(self.tokens), limit, lease_ttl_ms, 1, "saturated"]
            self.tokens.add(token)
            return [1, len(self.tokens), limit, lease_ttl_ms, 0, "acquired"]

        token = str(args[2])
        released = token in self.tokens
        self.tokens.discard(token)
        return [1 if released else 0, token, len(self.tokens), "released"]

    async def aclose(self) -> None:
        return None


class _FailingRedis:
    async def script_load(self, script: str) -> str:
        assert script
        return "acquire"

    async def evalsha(self, sha: str, numkeys: int, *keys_and_args: Any) -> list[Any]:
        assert sha
        assert numkeys == 2
        assert keys_and_args
        raise TimeoutError("redis unavailable")

    async def aclose(self) -> None:
        return None


@pytest.fixture(autouse=True)
def reset_vertex_limiter_state() -> None:
    vertex_limiter._reset_for_tests()


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
    assert recorded["vertex_limiter.backend"] == "local"


async def test_vertex_slot_uses_redis_backend_when_limiter_url_is_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = _SharedFakeRedis()
    monkeypatch.setattr(vertex_limiter, "_new_redis_client", lambda _settings: redis)
    settings = Settings(
        VIBECHECK_LIMITER_REDIS_URL="rediss://:secret@10.0.0.1:6379",
        VIBECHECK_LIMITER_REDIS_CA_CERT_PATH="/etc/ssl/vibecheck-limiter-redis/ca.crt",
        VERTEX_LEASE_ACQUIRE_TIMEOUT_MS=10,
        VERTEX_LEASE_RETRY_MIN_MS=1,
        VERTEX_LEASE_RETRY_MAX_MS=1,
    )

    async with vertex_slot(settings):
        assert len(redis.tokens) == 1

    assert redis.tokens == set()


async def test_redis_backend_enforces_shared_capacity_across_instances() -> None:
    redis = _SharedFakeRedis()
    first_backend = vertex_limiter._RedisLeaseBackend(redis)
    second_backend = vertex_limiter._RedisLeaseBackend(redis)

    first_lease = await first_backend.acquire(
        limit=1,
        lease_ttl_ms=60_000,
        acquire_timeout_ms=10,
        retry_min_ms=1,
        retry_max_ms=1,
    )

    with pytest.raises(vertex_limiter.VertexLimiterSaturationError):
        await second_backend.acquire(
            limit=1,
            lease_ttl_ms=60_000,
            acquire_timeout_ms=1,
            retry_min_ms=1,
            retry_max_ms=1,
        )

    await first_backend.release(first_lease)
    second_lease = await second_backend.acquire(
        limit=1,
        lease_ttl_ms=60_000,
        acquire_timeout_ms=10,
        retry_min_ms=1,
        retry_max_ms=1,
    )
    await second_backend.release(second_lease)

    assert redis.tokens == set()


async def test_redis_backend_fails_closed_when_backend_is_unavailable() -> None:
    backend = vertex_limiter._RedisLeaseBackend(_FailingRedis())

    with pytest.raises(vertex_limiter.VertexLimiterBackendUnavailableError):
        await backend.acquire(
            limit=1,
            lease_ttl_ms=60_000,
            acquire_timeout_ms=10,
            retry_min_ms=1,
            retry_max_ms=1,
        )


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
