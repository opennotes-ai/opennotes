"""Shared limiter for Vertex/Gemini calls."""

from __future__ import annotations

import asyncio
import secrets
import threading
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Protocol, cast

import logfire
from redis import asyncio as redis

from src.config import Settings, get_settings

_ACQUIRE_SCRIPT = """
local slots_key = KEYS[1]
local lease_key = KEYS[2]
local token = ARGV[1]
local limit = tonumber(ARGV[2])
local lease_ttl_ms = tonumber(ARGV[3])

local now_parts = redis.call("TIME")
local now_ms = tonumber(now_parts[1]) * 1000 + math.floor(tonumber(now_parts[2]) / 1000)
local expires_at = now_ms + lease_ttl_ms

redis.call("ZREMRANGEBYSCORE", slots_key, "-inf", now_ms)
local active = redis.call("ZCARD", slots_key)

if active < limit then
  redis.call("SET", lease_key, token, "PX", lease_ttl_ms, "NX")
  redis.call("ZADD", slots_key, expires_at, token)
  redis.call("PEXPIRE", slots_key, lease_ttl_ms)
  return {1, active + 1, limit, lease_ttl_ms, 0, "acquired"}
end

local retry_after_ms = 50
local next_slot = redis.call("ZRANGE", slots_key, 0, 0, "WITHSCORES")
if next_slot[2] ~= nil then
  retry_after_ms = math.max(10, tonumber(next_slot[2]) - now_ms)
end

return {0, active, limit, lease_ttl_ms, retry_after_ms, "saturated"}
"""

_RELEASE_SCRIPT = """
local slots_key = KEYS[1]
local lease_key = KEYS[2]
local token = ARGV[1]

local now_parts = redis.call("TIME")
local now_ms = tonumber(now_parts[1]) * 1000 + math.floor(tonumber(now_parts[2]) / 1000)
redis.call("ZREMRANGEBYSCORE", slots_key, "-inf", now_ms)

if redis.call("GET", lease_key) ~= token then
  return {0, token, redis.call("ZCARD", slots_key), "not_owner_or_expired"}
end

redis.call("DEL", lease_key)
local removed = redis.call("ZREM", slots_key, token)
return {removed, token, redis.call("ZCARD", slots_key), "released"}
"""


class VertexLimiterError(RuntimeError):
    """Base class for Vertex limiter failures."""


class VertexLimiterSaturationError(VertexLimiterError):
    """Raised when the shared limiter cannot acquire a slot within budget."""


class VertexLimiterBackendUnavailableError(VertexLimiterError):
    """Raised when the shared limiter backend is unavailable."""


class _RedisClient(Protocol):
    def script_load(self, script: str) -> Awaitable[str]: ...

    def evalsha(self, sha: str, numkeys: int, *keys_and_args: Any) -> Awaitable[list[Any]]: ...

    def aclose(self) -> Awaitable[None]: ...


@dataclass
class _LimiterState:
    limit: int
    loop: asyncio.AbstractEventLoop
    semaphore: asyncio.Semaphore
    active: int = 0
    pending: int = 0


@dataclass(frozen=True)
class _LimiterLease:
    token: str
    backend: str
    max_concurrency: int
    active: int
    pending: int
    local_state: _LimiterState | None = None


class _LimiterBackend(Protocol):
    backend_name: str

    async def acquire(self, settings: Settings) -> _LimiterLease: ...

    async def release(self, lease: _LimiterLease) -> None: ...


_state: _LimiterState | None = None
_state_lock = threading.Lock()
_backend: tuple[tuple[Any, ...], _LimiterBackend] | None = None
_backend_lock = threading.Lock()


def _limiter_state_for(limit: int, loop: asyncio.AbstractEventLoop) -> _LimiterState:
    global _state  # noqa: PLW0603
    if limit <= 0:
        raise ValueError("VERTEX_MAX_CONCURRENCY must be > 0")

    with _state_lock:
        if _state is None:
            _state = _LimiterState(limit=limit, loop=loop, semaphore=asyncio.Semaphore(limit))
        elif _state.loop is not loop:
            if _state.active or _state.pending:
                raise RuntimeError("Vertex limiter event loop changed while calls are active or waiting")
            _state = _LimiterState(limit=limit, loop=loop, semaphore=asyncio.Semaphore(limit))
        elif _state.limit != limit:
            if _state.active or _state.pending:
                raise RuntimeError(
                    "VERTEX_MAX_CONCURRENCY changed "
                    f"from {_state.limit} to {limit} while Vertex calls are active or waiting"
                )
            _state = _LimiterState(limit=limit, loop=loop, semaphore=asyncio.Semaphore(limit))
        _state.pending += 1
        return _state


class _LocalLimiterBackend:
    backend_name = "local"

    async def acquire(self, settings: Settings) -> _LimiterLease:
        limit = settings.VERTEX_MAX_CONCURRENCY
        state = _limiter_state_for(limit, asyncio.get_running_loop())
        pending = True
        try:
            await state.semaphore.acquire()
            with _state_lock:
                state.pending -= 1
                pending = False
                state.active += 1
                return _LimiterLease(
                    token="local",
                    backend=self.backend_name,
                    max_concurrency=limit,
                    active=state.active,
                    pending=state.pending,
                    local_state=state,
                )
        finally:
            if pending:
                with _state_lock:
                    state.pending -= 1

    async def release(self, lease: _LimiterLease) -> None:
        state = lease.local_state
        if state is None:
            return
        with _state_lock:
            state.active -= 1
        state.semaphore.release()


class _RedisLeaseBackend:
    backend_name = "redis"

    def __init__(
        self,
        redis_client: _RedisClient,
        *,
        key_prefix: str = "vibecheck:rl:vertex",
        sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
    ) -> None:
        self._redis = redis_client
        self._slots_key = f"{key_prefix}:slots"
        self._lease_key_prefix = f"{key_prefix}:lease"
        self._sleep = sleep
        self._script_lock = asyncio.Lock()
        self._acquire_sha: str | None = None
        self._release_sha: str | None = None
        self._pending = 0

    async def acquire(
        self,
        *,
        limit: int,
        lease_ttl_ms: int,
        acquire_timeout_ms: int,
        retry_min_ms: int,
        retry_max_ms: int,
    ) -> _LimiterLease:
        if limit <= 0:
            raise ValueError("VERTEX_MAX_CONCURRENCY must be > 0")

        token = secrets.token_urlsafe(24)
        deadline = time.monotonic() + (acquire_timeout_ms / 1000)
        self._pending += 1
        try:
            while True:
                response = await self._acquire_once(
                    token=token,
                    limit=limit,
                    lease_ttl_ms=lease_ttl_ms,
                    retry_min_ms=retry_min_ms,
                )
                acquired, active, max_concurrency, _ttl, retry_after_ms, reason = response
                if acquired:
                    return _LimiterLease(
                        token=token,
                        backend=self.backend_name,
                        max_concurrency=max_concurrency,
                        active=active,
                        pending=max(self._pending - 1, 0),
                    )

                remaining_s = deadline - time.monotonic()
                if remaining_s <= 0:
                    raise VertexLimiterSaturationError(
                        "Vertex limiter saturated before a shared Redis lease was acquired"
                    )

                sleep_ms = max(retry_min_ms, min(retry_after_ms, retry_max_ms))
                sleep_s = min(sleep_ms / 1000, remaining_s)
                if reason != "saturated":
                    raise VertexLimiterError(f"Unexpected Vertex limiter acquire result: {reason}")
                await self._sleep(sleep_s)
        finally:
            self._pending -= 1

    async def release(self, lease: _LimiterLease) -> None:
        await self._release_once(lease.token)

    async def _load_scripts(self) -> tuple[str, str]:
        if self._acquire_sha is not None and self._release_sha is not None:
            return self._acquire_sha, self._release_sha

        async with self._script_lock:
            if self._acquire_sha is None:
                self._acquire_sha = await self._redis.script_load(_ACQUIRE_SCRIPT)
            if self._release_sha is None:
                self._release_sha = await self._redis.script_load(_RELEASE_SCRIPT)
            return self._acquire_sha, self._release_sha

    async def _acquire_once(
        self,
        *,
        token: str,
        limit: int,
        lease_ttl_ms: int,
        retry_min_ms: int,
    ) -> tuple[bool, int, int, int, int, str]:
        acquire_sha, _release_sha = await self._load_scripts_with_retry(retry_min_ms)
        try:
            result = await self._redis.evalsha(
                acquire_sha,
                2,
                self._slots_key,
                f"{self._lease_key_prefix}:{token}",
                token,
                limit,
                lease_ttl_ms,
            )
        except Exception as exc:
            _log_backend_unavailable(exc)
            await self._sleep(retry_min_ms / 1000)
            try:
                result = await self._redis.evalsha(
                    acquire_sha,
                    2,
                    self._slots_key,
                    f"{self._lease_key_prefix}:{token}",
                    token,
                    limit,
                    lease_ttl_ms,
                )
            except Exception as retry_exc:
                _log_backend_unavailable(retry_exc)
                raise VertexLimiterBackendUnavailableError(
                    "Vertex limiter Redis backend unavailable"
                ) from retry_exc

        return _parse_acquire_result(result)

    async def _release_once(self, token: str) -> None:
        _acquire_sha, release_sha = await self._load_scripts_with_retry(0)
        try:
            await self._redis.evalsha(
                release_sha,
                2,
                self._slots_key,
                f"{self._lease_key_prefix}:{token}",
                token,
            )
        except Exception as exc:
            _log_backend_unavailable(exc)
            raise VertexLimiterBackendUnavailableError("Vertex limiter Redis release failed") from exc

    async def _load_scripts_with_retry(self, retry_min_ms: int) -> tuple[str, str]:
        try:
            return await self._load_scripts()
        except Exception as exc:
            _log_backend_unavailable(exc)
            if retry_min_ms > 0:
                await self._sleep(retry_min_ms / 1000)
            try:
                return await self._load_scripts()
            except Exception as retry_exc:
                _log_backend_unavailable(retry_exc)
                raise VertexLimiterBackendUnavailableError(
                    "Vertex limiter Redis backend unavailable"
                ) from retry_exc


class _RedisLimiterBackend:
    backend_name = "redis"

    def __init__(self, redis_client: _RedisClient) -> None:
        self._lease_backend = _RedisLeaseBackend(redis_client)

    async def acquire(self, settings: Settings) -> _LimiterLease:
        return await self._lease_backend.acquire(
            limit=settings.VERTEX_MAX_CONCURRENCY,
            lease_ttl_ms=settings.VERTEX_LEASE_TTL_MS,
            acquire_timeout_ms=settings.VERTEX_LEASE_ACQUIRE_TIMEOUT_MS,
            retry_min_ms=settings.VERTEX_LEASE_RETRY_MIN_MS,
            retry_max_ms=settings.VERTEX_LEASE_RETRY_MAX_MS,
        )

    async def release(self, lease: _LimiterLease) -> None:
        await self._lease_backend.release(lease)


def _parse_acquire_result(result: list[Any]) -> tuple[bool, int, int, int, int, str]:
    return (
        bool(int(result[0])),
        int(result[1]),
        int(result[2]),
        int(result[3]),
        int(result[4]),
        _decode_redis_string(result[5]),
    )


def _decode_redis_string(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def _new_redis_client(settings: Settings) -> _RedisClient:
    kwargs: dict[str, Any] = {
        "max_connections": settings.VIBECHECK_LIMITER_REDIS_MAX_CONNECTIONS,
        "socket_timeout": 0.01,
        "socket_connect_timeout": 0.01,
        "health_check_interval": 30,
    }
    if settings.VIBECHECK_LIMITER_REDIS_URL.startswith("rediss://"):
        kwargs["ssl_ca_certs"] = settings.VIBECHECK_LIMITER_REDIS_CA_CERT_PATH or None
    return cast(_RedisClient, cast(object, redis.from_url(settings.VIBECHECK_LIMITER_REDIS_URL, **kwargs)))


def _backend_for(settings: Settings, loop: asyncio.AbstractEventLoop) -> _LimiterBackend:
    global _backend  # noqa: PLW0603
    create_backend: Callable[[], _LimiterBackend]
    if settings.VIBECHECK_LIMITER_REDIS_URL:
        cache_key = (
            "redis",
            settings.VIBECHECK_LIMITER_REDIS_URL,
            settings.VIBECHECK_LIMITER_REDIS_CA_CERT_PATH,
            settings.VIBECHECK_LIMITER_REDIS_MAX_CONNECTIONS,
            loop,
        )

        def create_backend() -> _LimiterBackend:
            return _RedisLimiterBackend(_new_redis_client(settings))

    else:
        cache_key = ("local", loop)

        def create_backend() -> _LimiterBackend:
            return _LocalLimiterBackend()

    with _backend_lock:
        if _backend is None or _backend[0] != cache_key:
            _backend = (cache_key, create_backend())
        return _backend[1]


def _log_backend_unavailable(exc: BaseException) -> None:
    logfire.warning(
        "Vibecheck limiter Redis backend unavailable",
        alert_type="ratelimit_backend_unavailable",
        limiter_backend="vibecheck-limiter-redis",
        limiter_consumer="vertex_gemini",
        limiter_primitive="distributed_lease",
        limiter_result="backend_unavailable",
        fail_open=False,
        error_class=type(exc).__name__,
    )


@asynccontextmanager
async def vertex_slot(settings: Settings | None = None) -> AsyncIterator[None]:
    """Wait for a configured Vertex/Gemini execution slot."""
    resolved_settings = settings or get_settings()
    backend = _backend_for(resolved_settings, asyncio.get_running_loop())
    started = time.perf_counter()
    lease: _LimiterLease | None = None

    try:
        with logfire.span("vibecheck.vertex_limiter.wait") as span:
            lease = await backend.acquire(resolved_settings)
            wait_ms = (time.perf_counter() - started) * 1000
            span.set_attribute("vertex_limiter.wait_ms", wait_ms)
            span.set_attribute("vertex_limiter.max_concurrency", lease.max_concurrency)
            span.set_attribute("vertex_limiter.backend", lease.backend)
            span.set_attribute("vertex_limiter.active", lease.active)
            span.set_attribute("vertex_limiter.pending", lease.pending)

        yield
    finally:
        if lease is not None:
            await backend.release(lease)


def _reset_for_tests() -> None:
    global _state, _backend  # noqa: PLW0603
    with _state_lock:
        _state = None
    with _backend_lock:
        _backend = None
