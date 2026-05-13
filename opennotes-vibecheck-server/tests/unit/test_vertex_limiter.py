from __future__ import annotations

import asyncio
import socket
import threading
from typing import Any

import pytest
from pydantic import ValidationError
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

from src.config import Settings
from src.services import vertex_limiter
from src.services.vertex_limiter import vertex_slot


class _SharedFakeRedis:
    def __init__(self) -> None:
        self.tokens: dict[str, int] = {}
        self.now_ms = 0
        self.cleanup_calls: list[str] = []
        self.loaded_scripts: list[str] = []

    def advance(self, delta_ms: int) -> None:
        self.now_ms += delta_ms

    def _cleanup_expired(self, *, source: str) -> None:
        self.cleanup_calls.append(source)
        self.tokens = {
            token: expires_at_ms for token, expires_at_ms in self.tokens.items() if expires_at_ms > self.now_ms
        }

    async def script_load(self, script: str) -> str:
        self.loaded_scripts.append(script)
        return "release" if "not_owner_or_expired" in script else "acquire"

    async def evalsha(self, sha: str, numkeys: int, *args: Any) -> list[Any]:
        assert numkeys == 2
        if sha == "acquire":
            token = str(args[2])
            limit = int(args[3])
            lease_ttl_ms = int(args[4])
            self._cleanup_expired(source="acquire")
            if len(self.tokens) >= limit:
                return [0, len(self.tokens), limit, lease_ttl_ms, 1, "saturated"]
            self.tokens[token] = self.now_ms + lease_ttl_ms
            return [1, len(self.tokens), limit, lease_ttl_ms, 0, "acquired"]

        token = str(args[2])
        self._cleanup_expired(source="release")
        if token not in self.tokens:
            return [0, token, len(self.tokens), "not_owner_or_expired"]
        del self.tokens[token]
        return [1, token, len(self.tokens), "released"]

    async def aclose(self) -> None:
        return None


class _CloseTrackingRedis(_SharedFakeRedis):
    def __init__(self) -> None:
        super().__init__()
        self.aclose_calls = 0

    async def aclose(self) -> None:
        self.aclose_calls += 1


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


class _FailingNTimesRedis(_SharedFakeRedis):
    def __init__(self, fail_count: int) -> None:
        super().__init__()
        self._fail_count = fail_count
        self._failures = 0

    async def evalsha(self, sha: str, numkeys: int, *keys_and_args: Any) -> list[Any]:
        if self._failures < self._fail_count:
            self._failures += 1
            raise TimeoutError("redis unavailable")
        return await super().evalsha(sha, numkeys, *keys_and_args)


class _FailingNTimesEvalRedis(_SharedFakeRedis):
    def __init__(self, fail_count: int) -> None:
        super().__init__()
        self._fail_count = fail_count
        self._failures = 0

    async def evalsha(self, sha: str, numkeys: int, *keys_and_args: Any) -> list[Any]:
        if self._failures < self._fail_count:
            self._failures += 1
            raise TimeoutError("redis unavailable")
        return await super().evalsha(sha, numkeys, *keys_and_args)


class _FailingAfterFirstAcquireRedis(_SharedFakeRedis):
    def __init__(self) -> None:
        super().__init__()
        self._acquire_calls = 0

    async def evalsha(self, sha: str, numkeys: int, *keys_and_args: Any) -> list[Any]:
        if sha == "acquire":
            self._acquire_calls += 1
            if self._acquire_calls > 1:
                raise TimeoutError("redis unavailable")
        return await super().evalsha(sha, numkeys, *keys_and_args)


class _AcquiredThenFailingReleaseRedis:
    def __init__(self) -> None:
        self.acquired_tokens: set[str] = set()
        self.acquire_calls: int = 0
        self.release_calls: int = 0

    async def script_load(self, script: str) -> str:
        return "release" if "not_owner_or_expired" in script else "acquire"

    async def evalsha(self, sha: str, numkeys: int, *keys_and_args: Any) -> list[Any]:
        assert numkeys == 2
        if sha == "acquire":
            self.acquire_calls += 1
            token = str(keys_and_args[2])
            self.acquired_tokens.add(token)
            return [1, len(self.acquired_tokens), 1, 60_000, 0, "acquired"]
        assert sha == "release"
        self.release_calls += 1
        raise TimeoutError("redis unavailable")

    async def aclose(self) -> None:
        return None


class _BadReleaseResultRedis:
    async def script_load(self, script: str) -> str:
        assert script
        return "release"

    async def evalsha(self, sha: str, numkeys: int, *keys_and_args: Any) -> list[Any]:
        assert sha == "release"
        assert numkeys == 2
        assert len(keys_and_args) == 3
        return [1, "token", 0, 1]

    async def aclose(self) -> None:
        return None


class _BadAcquireResultRedis:
    async def script_load(self, script: str) -> str:
        assert script
        return "acquire"

    async def evalsha(self, sha: str, numkeys: int, *keys_and_args: Any) -> list[Any]:
        assert sha == "acquire"
        assert numkeys == 2
        assert len(keys_and_args) == 5
        return [2, 1, 1, 1, 1, "acquired"]

    async def aclose(self) -> None:
        return None


@pytest.fixture(autouse=True)
def reset_vertex_limiter_state() -> None:
    vertex_limiter._reset_for_tests()


def test_new_redis_client_timeout_values(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(
        VIBECHECK_LIMITER_REDIS_URL="rediss://:secret@10.0.0.1:6379",
        VIBECHECK_LIMITER_REDIS_CA_CERT_PATH="/etc/ssl/vibecheck-limiter-redis/ca.crt",
    )
    captured: dict[str, Any] = {}

    def _fake_from_url(url: str, **kwargs: Any) -> object:
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(vertex_limiter.redis_asyncio, "from_url", _fake_from_url)
    vertex_limiter._new_redis_client(settings)

    assert captured["socket_timeout"] == 1.5
    assert captured["socket_connect_timeout"] == 2.0
    assert captured["retry_on_timeout"] is True
    assert captured["retry_on_error"] == (RedisConnectionError, RedisTimeoutError)
    assert captured["socket_keepalive"] is True

    expected_keepalive_options = {
        option: value
        for option, value in (
            (getattr(socket, "TCP_KEEPIDLE", None), 60),
            (getattr(socket, "TCP_KEEPINTVL", None), 10),
            (getattr(socket, "TCP_KEEPCNT", None), 5),
        )
        if isinstance(option, int)
    }
    if expected_keepalive_options:
        assert captured["socket_keepalive_options"] == expected_keepalive_options
    else:
        assert captured.get("socket_keepalive_options") is None


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


async def test_vertex_slot_records_wait_ms_local_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    class _RecordingHistogram:
        def __init__(self) -> None:
            self.records: list[tuple[float, dict[str, str]]] = []

        def record(self, value: float, attributes: dict[str, str] | None = None) -> None:
            self.records.append((value, attributes or {}))

    recorded_histogram = _RecordingHistogram()
    monkeypatch.setattr(vertex_limiter, "VERTEX_LIMITER_WAIT_MS", recorded_histogram)

    async with vertex_slot(Settings(VERTEX_MAX_CONCURRENCY=1)):
        pass

    assert len(recorded_histogram.records) == 1
    recorded_wait_ms, recorded_attrs = recorded_histogram.records[0]
    assert isinstance(recorded_wait_ms, float)
    assert recorded_wait_ms >= 0.0
    assert recorded_attrs == {"vertex_limiter.backend": "local"}


async def test_vertex_slot_records_wait_ms_redis_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _RecordingHistogram:
        def __init__(self) -> None:
            self.records: list[tuple[float, dict[str, str]]] = []

        def record(self, value: float, attributes: dict[str, str] | None = None) -> None:
            self.records.append((value, attributes or {}))

    recording_histogram = _RecordingHistogram()
    redis = _SharedFakeRedis()
    monkeypatch.setattr(vertex_limiter, "_new_redis_client", lambda _settings: redis)
    monkeypatch.setattr(vertex_limiter, "VERTEX_LIMITER_WAIT_MS", recording_histogram)
    settings = Settings(
        VIBECHECK_LIMITER_REDIS_URL="rediss://:secret@10.0.0.1:6379",
        VIBECHECK_LIMITER_REDIS_CA_CERT_PATH="/etc/ssl/vibecheck-limiter-redis/ca.crt",
        VERTEX_LEASE_ACQUIRE_TIMEOUT_MS=10,
        VERTEX_LEASE_RETRY_MIN_MS=1,
        VERTEX_LEASE_RETRY_MAX_MS=1,
    )

    async with vertex_slot(settings):
        assert len(redis.tokens) == 1

    assert len(recording_histogram.records) == 1
    recorded_wait_ms, recorded_attrs = recording_histogram.records[0]
    assert isinstance(recorded_wait_ms, float)
    assert recorded_wait_ms >= 0.0
    assert recorded_attrs == {"vertex_limiter.backend": "redis"}


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

    assert redis.tokens == {}
    assert redis.cleanup_calls == ["acquire", "release"]


async def test_vertex_slot_redis_backend_key_change_defers_old_client_close_until_old_lease_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis_a = _CloseTrackingRedis()
    redis_b = _CloseTrackingRedis()

    def _fake_new_redis_client(settings: Settings) -> _CloseTrackingRedis:
        if settings.VIBECHECK_LIMITER_REDIS_URL == "rediss://:secret@10.0.0.1:6379":
            return redis_a
        return redis_b

    monkeypatch.setattr(vertex_limiter, "_new_redis_client", _fake_new_redis_client)

    old_settings = Settings(
        VIBECHECK_LIMITER_REDIS_URL="rediss://:secret@10.0.0.1:6379",
        VIBECHECK_LIMITER_REDIS_CA_CERT_PATH="/etc/ssl/vibecheck-limiter-redis/ca.crt",
        VERTEX_LEASE_ACQUIRE_TIMEOUT_MS=100,
        VERTEX_LEASE_RETRY_MIN_MS=1,
        VERTEX_LEASE_RETRY_MAX_MS=1,
    )
    new_settings = Settings(
        VIBECHECK_LIMITER_REDIS_URL="rediss://:secret@10.0.0.2:6379",
        VIBECHECK_LIMITER_REDIS_CA_CERT_PATH="/etc/ssl/vibecheck-limiter-redis/ca2.crt",
        VERTEX_LEASE_ACQUIRE_TIMEOUT_MS=100,
        VERTEX_LEASE_RETRY_MIN_MS=1,
        VERTEX_LEASE_RETRY_MAX_MS=1,
    )

    old_acquired = asyncio.Event()
    old_release = asyncio.Event()
    new_acquired = asyncio.Event()
    new_release = asyncio.Event()

    async def _old_slot() -> None:
        async with vertex_slot(old_settings):
            old_acquired.set()
            await old_release.wait()

    async def _new_slot() -> None:
        async with vertex_slot(new_settings):
            new_acquired.set()
            await new_release.wait()

    old_task = asyncio.create_task(_old_slot())
    await old_acquired.wait()

    new_task = asyncio.create_task(_new_slot())
    await new_acquired.wait()

    assert redis_a.aclose_calls == 0
    assert redis_a.tokens

    new_release.set()
    await new_task

    assert redis_b.aclose_calls == 0
    assert redis_a.aclose_calls == 0
    assert redis_a.tokens

    old_release.set()
    await old_task

    assert redis_a.tokens == {}
    assert redis_a.aclose_calls == 1


def test_reset_for_tests_closes_cached_redis_backend() -> None:
    redis = _CloseTrackingRedis()

    # _reset_for_tests is sync by design; this verifies it can safely run after a
    # backend has been cached and does not leave an open handle behind.
    old_backend = vertex_limiter._RedisLimiterBackend(redis)
    vertex_limiter._backend = (("redis", "x", "y", 1, object()), old_backend)

    assert vertex_limiter._backend is not None
    vertex_limiter._reset_for_tests()
    assert redis.aclose_calls == 1


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

    assert redis.tokens == {}


async def test_redis_backend_allows_repeated_use_on_same_loop() -> None:
    redis = _SharedFakeRedis()
    backend = vertex_limiter._RedisLeaseBackend(redis)

    first = await backend.acquire(
        limit=2,
        lease_ttl_ms=60_000,
        acquire_timeout_ms=10,
        retry_min_ms=1,
        retry_max_ms=1,
    )
    second = await backend.acquire(
        limit=2,
        lease_ttl_ms=60_000,
        acquire_timeout_ms=10,
        retry_min_ms=1,
        retry_max_ms=1,
    )

    assert first.token != second.token

    await backend.release(first)
    await backend.release(second)


async def test_redis_backend_rejects_cross_loop_acquire_after_first_use() -> None:
    redis = _SharedFakeRedis()
    backend = vertex_limiter._RedisLeaseBackend(redis)

    lease = await backend.acquire(
        limit=1,
        lease_ttl_ms=60_000,
        acquire_timeout_ms=10,
        retry_min_ms=1,
        retry_max_ms=1,
    )
    await backend.release(lease)

    def _run_in_other_loop() -> None:
        async def _acquire_in_other_loop() -> None:
            await backend.acquire(
                limit=1,
                lease_ttl_ms=60_000,
                acquire_timeout_ms=10,
                retry_min_ms=1,
                retry_max_ms=1,
            )

        asyncio.run(_acquire_in_other_loop())

    with pytest.raises(RuntimeError, match="multiple event loops"):
        await asyncio.to_thread(_run_in_other_loop)


async def test_redis_backend_cleans_expired_leases_on_acquire_and_release() -> None:
    redis = _SharedFakeRedis()
    backend = vertex_limiter._RedisLeaseBackend(redis)

    first_lease = await backend.acquire(
        limit=1,
        lease_ttl_ms=10,
        acquire_timeout_ms=10,
        retry_min_ms=1,
        retry_max_ms=1,
    )
    redis.advance(10)

    assert redis.tokens[first_lease.token] == 10
    second_lease = await backend.acquire(
        limit=1,
        lease_ttl_ms=10,
        acquire_timeout_ms=10,
        retry_min_ms=1,
        retry_max_ms=1,
    )
    assert second_lease.token != first_lease.token
    assert redis.cleanup_calls == ["acquire", "acquire"]

    release_response = await redis.evalsha(
        "release",
        2,
        "vibecheck:rl:vertex:slots",
        f"{backend._lease_key_prefix}:{first_lease.token}",
        first_lease.token,
    )
    assert release_response == [0, first_lease.token, 1, "not_owner_or_expired"]
    assert redis.cleanup_calls == ["acquire", "acquire", "release"]

    await backend.release(second_lease)
    assert redis.tokens == {}
    assert redis.cleanup_calls == ["acquire", "acquire", "release", "release"]


async def test_redis_backend_logs_warning_for_expired_lease_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = _SharedFakeRedis()
    warnings: list[tuple[str, dict[str, Any]]] = []

    def _record_warning(message: str, **kwargs: Any) -> None:
        warnings.append((message, kwargs))

    monkeypatch.setattr(vertex_limiter.logfire, "warning", _record_warning)
    backend = vertex_limiter._RedisLeaseBackend(redis)
    lease = await backend.acquire(
        limit=1,
        lease_ttl_ms=10,
        acquire_timeout_ms=10,
        retry_min_ms=1,
        retry_max_ms=1,
    )
    redis.advance(10)
    await backend.release(lease)

    assert warnings == [
        (
            "Vibecheck limiter Redis lease expired before release",
            {
                "alert_type": "ratelimit_lease_expired_before_release",
                "limiter_backend": "vibecheck-limiter-redis",
                "limiter_consumer": "vertex_gemini",
                "limiter_primitive": "distributed_lease",
                "limiter_result": "lease_expired_before_release",
                "fail_open": True,
                "lease_token": lease.token,
                "release_token": lease.token,
                "lease_active": 0,
                "lease_status": "not_owner_or_expired",
            },
        )
    ]


def test_parse_acquire_result_accepts_bytes_reason_and_status() -> None:
    assert vertex_limiter._parse_acquire_result([1, 2, 3, 4, 5, b"acquired"]) == (
        True,
        2,
        3,
        4,
        5,
        "acquired",
    )


@pytest.mark.parametrize("value", [2, -1, b"2", "7"])
def test_parse_acquire_result_rejects_non_zero_or_one_acquired_flag(value: Any) -> None:
    with pytest.raises(vertex_limiter.VertexLimiterError, match=r"acquired.*index=0"):
        vertex_limiter._parse_acquire_result([value, 1, 2, 3, 4, "acquired"])


def test_parse_release_result_accepts_bytes_reason_and_status() -> None:
    result = vertex_limiter._parse_release_result([0, b"token", 7, b"released"])
    assert result.removed is False
    assert result.token == "token"
    assert result.remaining == 7
    assert result.status == "released"


@pytest.mark.parametrize("reason", [123, object(), None])
def test_parse_acquire_and_release_reject_non_string_reason_status(reason: Any) -> None:
    with pytest.raises(vertex_limiter.VertexLimiterError, match=r"reason.*index=5"):
        vertex_limiter._parse_acquire_result([1, 2, 3, 4, 5, reason])

    with pytest.raises(vertex_limiter.VertexLimiterError, match=r"status.*index=3"):
        vertex_limiter._parse_release_result([1, "token", 7, reason])


async def test_release_parse_error_does_not_become_backend_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logged: list[tuple[str, list[Any]]] = []

    def _record_warning(exc: BaseException, **_kwargs: Any) -> None:
        logged.append(("warning", [type(exc).__name__]))

    monkeypatch.setattr(vertex_limiter, "_log_backend_unavailable", _record_warning)
    backend = vertex_limiter._RedisLeaseBackend(_BadReleaseResultRedis())
    lease = vertex_limiter._LimiterLease(
        token="token",
        backend="redis",
        max_concurrency=1,
        active=0,
        pending=0,
    )

    with pytest.raises(vertex_limiter.VertexLimiterError):
        await backend.release(lease)

    assert logged == []


async def test_acquire_parse_error_does_not_become_backend_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logged: list[tuple[str, list[Any]]] = []

    def _record_warning(exc: BaseException, **_kwargs: Any) -> None:
        logged.append(("warning", [type(exc).__name__]))

    monkeypatch.setattr(vertex_limiter, "_log_backend_unavailable", _record_warning)
    backend = vertex_limiter._RedisLeaseBackend(_BadAcquireResultRedis())

    with pytest.raises(vertex_limiter.VertexLimiterError):
        await backend.acquire(
            limit=1,
            lease_ttl_ms=60_000,
            acquire_timeout_ms=10,
            retry_min_ms=1,
            retry_max_ms=1,
        )

    assert logged == []


async def test_redis_backend_logs_debug_then_warning_for_persistent_acquire_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = _FailingNTimesEvalRedis(fail_count=2)
    warnings: list[tuple[str, dict[str, Any]]] = []
    debug: list[tuple[str, dict[str, Any]]] = []

    def _record_warning(message: str, **kwargs: Any) -> None:
        warnings.append((message, kwargs))

    def _record_debug(message: str, **kwargs: Any) -> None:
        debug.append((message, kwargs))

    monkeypatch.setattr(vertex_limiter.logfire, "warning", _record_warning)
    monkeypatch.setattr(vertex_limiter.logfire, "debug", _record_debug)
    backend = vertex_limiter._RedisLeaseBackend(redis)

    with pytest.raises(vertex_limiter.VertexLimiterBackendUnavailableError):
        await backend.acquire(
            limit=1,
            lease_ttl_ms=60_000,
            acquire_timeout_ms=10,
            retry_min_ms=1,
            retry_max_ms=1,
        )

    assert len(debug) == 1
    assert len(warnings) == 1
    assert debug[0] == (
        "Vibecheck limiter Redis backend unavailable",
        {
            "alert_type": "ratelimit_backend_unavailable",
            "limiter_backend": "vibecheck-limiter-redis",
            "limiter_consumer": "vertex_gemini",
            "limiter_primitive": "distributed_lease",
            "limiter_result": "backend_unavailable",
            "fail_open": False,
            "error_class": "TimeoutError",
        },
    )
    assert warnings[0] == (
        "Vibecheck limiter Redis backend unavailable",
        {
            "alert_type": "ratelimit_backend_unavailable",
            "limiter_backend": "vibecheck-limiter-redis",
            "limiter_consumer": "vertex_gemini",
            "limiter_primitive": "distributed_lease",
            "limiter_result": "backend_unavailable",
            "fail_open": False,
            "error_class": "TimeoutError",
        },
    )


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


async def test_vertex_slot_releases_errors_suppressed_when_body_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = _AcquiredThenFailingReleaseRedis()
    warnings: list[tuple[str, dict[str, Any]]] = []

    def _record_warning(message: str, **kwargs: Any) -> None:
        warnings.append((message, kwargs))

    monkeypatch.setattr(vertex_limiter, "_new_redis_client", lambda _settings: redis)
    monkeypatch.setattr(vertex_limiter.logfire, "warning", _record_warning)
    settings = Settings(VIBECHECK_LIMITER_REDIS_URL="rediss://:secret@10.0.0.1:6379")

    with pytest.raises(RuntimeError, match="boom"):
        async with vertex_slot(settings):
            raise RuntimeError("boom")

    assert redis.acquire_calls == 1
    assert redis.release_calls == 1
    assert len(warnings) >= 1
    assert warnings[-1][1]["limiter_result"] == "backend_unavailable"


async def test_vertex_slot_release_error_when_body_succeeds_is_not_suppressed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = _AcquiredThenFailingReleaseRedis()
    monkeypatch.setattr(vertex_limiter, "_new_redis_client", lambda _settings: redis)
    settings = Settings(VIBECHECK_LIMITER_REDIS_URL="rediss://:secret@10.0.0.1:6379")

    with pytest.raises(vertex_limiter.VertexLimiterBackendUnavailableError):
        async with vertex_slot(settings):
            pass

    assert redis.acquire_calls == 1
    assert redis.release_calls == 1


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


async def test_vertex_limiter_fallback_engages_on_consecutive_redis_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = _FailingNTimesRedis(fail_count=4)
    monkeypatch.setattr(vertex_limiter, "_new_redis_client", lambda _settings: redis)
    warnings: list[tuple[str, dict[str, Any]]] = []

    def _record_warning(message: str, **kwargs: Any) -> None:
        warnings.append((message, kwargs))

    monkeypatch.setattr(vertex_limiter.logfire, "warning", _record_warning)
    settings = Settings(
        VIBECHECK_LIMITER_REDIS_URL="rediss://:secret@10.0.0.1:6379",
        VIBECHECK_LIMITER_REDIS_CA_CERT_PATH="/etc/ssl/vibecheck-limiter-redis/ca.crt",
        VERTEX_MAX_CONCURRENCY=12,
        VIBECHECK_MAX_INSTANCES=3,
        VERTEX_LEASE_ACQUIRE_TIMEOUT_MS=10,
        VERTEX_LEASE_RETRY_MIN_MS=1,
        VERTEX_LEASE_RETRY_MAX_MS=1,
    )
    backend = vertex_limiter._FallbackingBackend(
        vertex_limiter._RedisLimiterBackend(redis),
        vertex_limiter._LocalLimiterBackend(),
    )

    with pytest.raises(vertex_limiter.VertexLimiterBackendUnavailableError):
        await backend.acquire(settings)

    lease = await backend.acquire(settings)
    try:
        assert lease.backend == "local"
        assert lease.max_concurrency == vertex_limiter._local_vertex_fallback_limit(settings)
        fallback_logs = [entry for entry in warnings if entry[1]["limiter_result"] == "fallback_engaged"]
        assert len(fallback_logs) == 1
        assert fallback_logs[0][1]["per_instance_cap"] == 4
        assert fallback_logs[0][1]["vibecheck_max_instances"] == 3
    finally:
        await backend.release(lease)


async def test_vertex_limiter_fallback_local_cap_is_bounded_per_instance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = _FailingNTimesRedis(fail_count=4)
    monkeypatch.setattr(vertex_limiter, "_new_redis_client", lambda _settings: redis)
    settings = Settings(
        VIBECHECK_LIMITER_REDIS_URL="rediss://:secret@10.0.0.1:6379",
        VIBECHECK_LIMITER_REDIS_CA_CERT_PATH="/etc/ssl/vibecheck-limiter-redis/ca.crt",
        VERTEX_MAX_CONCURRENCY=6,
        VIBECHECK_MAX_INSTANCES=2,
        VERTEX_LEASE_ACQUIRE_TIMEOUT_MS=10,
        VERTEX_LEASE_RETRY_MIN_MS=1,
        VERTEX_LEASE_RETRY_MAX_MS=1,
    )
    backend = vertex_limiter._FallbackingBackend(
        vertex_limiter._RedisLimiterBackend(redis),
        vertex_limiter._LocalLimiterBackend(),
    )

    with pytest.raises(vertex_limiter.VertexLimiterBackendUnavailableError):
        await backend.acquire(settings)

    lease_one = await backend.acquire(settings)
    lease_two = await backend.acquire(settings)
    lease_three = await backend.acquire(settings)
    assert lease_one.max_concurrency == 3
    assert lease_two.max_concurrency == 3
    assert lease_three.max_concurrency == 3

    blocked = asyncio.create_task(backend.acquire(settings))
    await asyncio.sleep(0)
    assert not blocked.done()

    await backend.release(lease_one)
    lease_four = await asyncio.wait_for(blocked, timeout=0.5)
    try:
        assert lease_four.backend == "local"
        assert lease_four.max_concurrency == 3
    finally:
        await backend.release(lease_four)
        await backend.release(lease_two)
        await backend.release(lease_three)


def test_vertex_limiter_fallback_local_cap_floors_to_one() -> None:
    settings = Settings(VERTEX_MAX_CONCURRENCY=2, VIBECHECK_MAX_INSTANCES=5)
    assert vertex_limiter._local_vertex_fallback_limit(settings) == 1


async def test_vertex_limiter_fallback_recovery_probe_logs_recovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = _FailingNTimesRedis(fail_count=4)
    monkeypatch.setattr(vertex_limiter, "_new_redis_client", lambda _settings: redis)
    warnings: list[tuple[str, dict[str, Any]]] = []

    def _record_warning(message: str, **kwargs: Any) -> None:
        warnings.append((message, kwargs))

    monkeypatch.setattr(vertex_limiter.logfire, "warning", _record_warning)
    settings = Settings(
        VIBECHECK_LIMITER_REDIS_URL="rediss://:secret@10.0.0.1:6379",
        VIBECHECK_LIMITER_REDIS_CA_CERT_PATH="/etc/ssl/vibecheck-limiter-redis/ca.crt",
        VERTEX_LEASE_ACQUIRE_TIMEOUT_MS=10,
        VERTEX_LEASE_RETRY_MIN_MS=1,
        VERTEX_LEASE_RETRY_MAX_MS=1,
    )
    redis_backend = vertex_limiter._RedisLimiterBackend(redis)
    backend = vertex_limiter._FallbackingBackend(
        redis_backend,
        vertex_limiter._LocalLimiterBackend(),
    )

    with pytest.raises(vertex_limiter.VertexLimiterBackendUnavailableError):
        await backend.acquire(settings)
    local_lease = await backend.acquire(settings)
    await backend.release(local_lease)

    probe_attempts = 0

    async def _probe() -> None:
        nonlocal probe_attempts
        if probe_attempts == 0:
            probe_attempts += 1
            raise vertex_limiter.VertexLimiterBackendUnavailableError("probe unavailable")

    monkeypatch.setattr(redis_backend._lease_backend, "probe", _probe)
    backend._fallback_cooldown_until = 0.0

    local_lease = await backend.acquire(settings)
    await backend.release(local_lease)

    recovered_lease = await backend.acquire(settings)
    backend._fallback_cooldown_until = 0.0
    await backend.release(recovered_lease)

    recovered_lease = await backend.acquire(settings)
    try:
        assert recovered_lease.backend == "redis"
    finally:
        await backend.release(recovered_lease)

    assert any(entry[1]["limiter_result"] == "fallback_engaged" for entry in warnings)
    assert any(entry[1]["limiter_result"] == "fallback_recovered" for entry in warnings)


async def test_vertex_limiter_mixed_inflight_releases_route_by_backend() -> None:
    redis = _SharedFakeRedis()
    backend = vertex_limiter._FallbackingBackend(
        vertex_limiter._RedisLimiterBackend(redis),
        vertex_limiter._LocalLimiterBackend(),
    )
    settings = Settings(VERTEX_MAX_CONCURRENCY=1)

    redis_lease = await backend._acquire_with_redis_backend(settings)
    local_lease = await backend._acquire_with_local_backend(settings)

    await backend.release(redis_lease)
    await backend.release(local_lease)

    assert redis.tokens == {}
