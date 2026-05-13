"""Shared limiter for Vertex/Gemini calls."""

from __future__ import annotations

import asyncio
import inspect
import secrets
import socket
import threading
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, NoReturn, Protocol, cast

import logfire
from redis import asyncio as redis_asyncio
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

from src.config import Settings, get_settings

VERTEX_LIMITER_WAIT_MS = logfire.metric_histogram(
    "vibecheck.vertex_limiter.wait_ms",
    unit="ms",
)

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
  redis.call("SET", lease_key, token, "PX", lease_ttl_ms)
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

    async def aclose(self) -> None: ...


_state: _LimiterState | None = None
_state_lock = threading.Lock()
_backend: tuple[tuple[Any, ...], _LimiterBackend] | None = None
_backend_lock = threading.Lock()
_FALLBACK_FAILURE_THRESHOLD = 2
_FALLBACK_COOLDOWN_SECONDS = 10.0


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


def _local_vertex_fallback_limit(settings: Settings) -> int:
    # TASK-1483.16.08: floor at one to guarantee forward progress while local fallback is active.
    # TASK-1483.16.08.17 wires this cap as a deploy-time environment value.
    return max(settings.VERTEX_MAX_CONCURRENCY // settings.VIBECHECK_MAX_INSTANCES, 1)


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

    async def aclose(self) -> None:
        return None


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
        # `_owner_loop` is only safe under a single event-loop usage contract. We capture
        # the first caller loop on first acquire and enforce same-loop use to avoid
        # unsafely shared cross-loop operations. This does not close races where two
        # different loops call first concurrently.
        self._owner_loop: asyncio.AbstractEventLoop | None = None

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

        loop = asyncio.get_running_loop()
        if self._owner_loop is None:
            self._owner_loop = loop
        elif self._owner_loop is not loop:
            raise RuntimeError(
                "Redis Vertex limiter backend instance used from multiple event loops after first acquire"
            )

        token = secrets.token_urlsafe(24)
        deadline = time.monotonic() + (acquire_timeout_ms / 1000)
        while True:
            response = await self._acquire_once(
                token=token,
                limit=limit,
                lease_ttl_ms=lease_ttl_ms,
                retry_min_ms=retry_min_ms,
            )
            acquired, _active, max_concurrency, _ttl, retry_after_ms, reason = response
            if acquired:
                return _LimiterLease(
                    token=token,
                    backend=self.backend_name,
                    max_concurrency=max_concurrency,
                    active=_active,
                    pending=0,
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

    async def release(self, lease: _LimiterLease) -> None:
        await self._release_once(lease.token)

    async def probe(self) -> None:
        # Load scripts as a lightweight connectivity/protocol probe.
        await self._load_scripts_with_retry(0)

    async def aclose(self) -> None:
        await self._redis.aclose()

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
            _log_backend_unavailable(exc, final_attempt=False, will_raise=False)
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
                _log_backend_unavailable(
                    retry_exc,
                    final_attempt=True,
                    will_raise=True,
                )
                raise VertexLimiterBackendUnavailableError(
                    "Vertex limiter Redis backend unavailable"
                ) from retry_exc

        return _parse_acquire_result(result)

    async def _release_once(self, token: str) -> None:
        _acquire_sha, release_sha = await self._load_scripts_with_retry(0)
        try:
            redis_result = await self._redis.evalsha(
                release_sha,
                2,
                self._slots_key,
                f"{self._lease_key_prefix}:{token}",
                token,
            )
        except Exception as exc:
            _log_backend_unavailable(
                exc,
                final_attempt=True,
                will_raise=True,
            )
            raise VertexLimiterBackendUnavailableError("Vertex limiter Redis release failed") from exc

        release_result = _parse_release_result(redis_result)
        if release_result.status == "not_owner_or_expired":
            logfire.warning(
                "Vibecheck limiter Redis lease expired before release",
                alert_type="ratelimit_lease_expired_before_release",
                limiter_backend="vibecheck-limiter-redis",
                limiter_consumer="vertex_gemini",
                limiter_primitive="distributed_lease",
                limiter_result="lease_expired_before_release",
                fail_open=True,
                lease_token=token,
                release_token=release_result.token,
                lease_active=release_result.remaining,
                lease_status=release_result.status,
            )

    async def _load_scripts_with_retry(self, retry_min_ms: int) -> tuple[str, str]:
        try:
            return await self._load_scripts()
        except Exception as exc:
            _log_backend_unavailable(
                exc,
                final_attempt=False,
                will_raise=False,
            )
            if retry_min_ms > 0:
                await self._sleep(retry_min_ms / 1000)
            try:
                return await self._load_scripts()
            except Exception as retry_exc:
                _log_backend_unavailable(
                    retry_exc,
                    final_attempt=True,
                    will_raise=True,
                )
                raise VertexLimiterBackendUnavailableError(
                    "Vertex limiter Redis backend unavailable"
                ) from retry_exc


@dataclass(frozen=True)
class _ReleaseResult:
    removed: bool
    token: str
    remaining: int
    status: str


def _parse_release_result(result: list[Any]) -> _ReleaseResult:
    _validate_result_length(result, expected_length=4, parser="release")
    return _ReleaseResult(
        removed=bool(_parse_int_result_field(result, 0, "removed", "release")),
        token=_decode_redis_string(result[1], "token", 1, result, "release"),
        remaining=_parse_int_result_field(result, 2, "remaining", "release"),
        status=_decode_redis_string(result[3], "status", 3, result, "release"),
    )


def _parse_acquire_result(result: list[Any]) -> tuple[bool, int, int, int, int, str]:
    _validate_result_length(result, expected_length=6, parser="acquire")
    acquired = _parse_int_result_field(result, 0, "acquired", "acquire")
    if acquired not in (0, 1):
        _raise_parse_error(
            result,
            parser="acquire",
            field="acquired",
            index=0,
        )
    return (
        bool(acquired),
        _parse_int_result_field(result, 1, "active", "acquire"),
        _parse_int_result_field(result, 2, "limit", "acquire"),
        _parse_int_result_field(result, 3, "lease_ttl_ms", "acquire"),
        _parse_int_result_field(result, 4, "retry_after_ms", "acquire"),
        _decode_redis_string(result[5], "reason", 5, result, "acquire"),
    )


def _parse_int_result_field(result: list[Any], index: int, field: str, parser: str) -> int:
    try:
        return int(result[index])
    except (ValueError, TypeError, IndexError) as exc:
        _raise_parse_error(
            result,
            parser=parser,
            field=field,
            index=index,
            cause=exc,
        )


def _decode_redis_string(
    value: Any,
    field: str,
    index: int,
    result: list[Any],
    parser: str,
) -> str:
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError as exc:
            _raise_parse_error(
                result,
                parser=parser,
                field=field,
                index=index,
                cause=exc,
            )
    if isinstance(value, str):
        return value

    _raise_parse_error(
        result,
        parser=parser,
        field=field,
        index=index,
    )
    return ""


def _validate_result_length(result: list[Any], *, expected_length: int, parser: str) -> None:
    if len(result) != expected_length:
        raise VertexLimiterError(
            f"Invalid Vertex limiter {parser} result shape: expected {expected_length}, got {len(result)}; "
            f"result={result!r}"
        )


def _raise_parse_error(
    result: list[Any],
    *,
    parser: str,
    field: str,
    index: int,
    cause: BaseException | None = None,
) -> NoReturn:
    message = (
        f"Invalid Vertex limiter {parser} result field={field} index={index}: result={result!r}"
    )
    if cause is None:
        raise VertexLimiterError(message)
    raise VertexLimiterError(message) from cause


def _redis_keepalive_options() -> dict[int, int]:
    options: dict[int, int] = {}
    for name, value in (
        ("TCP_KEEPIDLE", 60),
        ("TCP_KEEPINTVL", 10),
        ("TCP_KEEPCNT", 5),
    ):
        option = getattr(socket, name, None)
        if isinstance(option, int):
            options[option] = value
    return options


class _RedisLimiterBackend:
    backend_name = "redis"

    def __init__(self, redis_client: _RedisClient) -> None:
        self._lease_backend = _RedisLeaseBackend(redis_client)
        self._state_lock = threading.Lock()
        self._active_leases = 0
        self._pending_acquires = 0
        self._close_requested = False
        self._is_closed = False
        self._close_in_progress = False

    async def acquire(self, settings: Settings) -> _LimiterLease:
        with self._state_lock:
            self._pending_acquires += 1

        try:
            lease = await self._lease_backend.acquire(
                limit=settings.VERTEX_MAX_CONCURRENCY,
                lease_ttl_ms=settings.VERTEX_LEASE_TTL_MS,
                acquire_timeout_ms=settings.VERTEX_LEASE_ACQUIRE_TIMEOUT_MS,
                retry_min_ms=settings.VERTEX_LEASE_RETRY_MIN_MS,
                retry_max_ms=settings.VERTEX_LEASE_RETRY_MAX_MS,
            )
            with self._state_lock:
                self._active_leases += 1
                active = self._active_leases
                pending = max(self._pending_acquires - 1, 0)
                return _LimiterLease(
                    token=lease.token,
                    backend=self.backend_name,
                    max_concurrency=lease.max_concurrency,
                    active=active,
                    pending=pending,
                )
        finally:
            with self._state_lock:
                self._pending_acquires -= 1
            # Keep the close path unified and ensure close completion checks run even
            # if acquire fails or succeeds.
            await self._finalize_close_if_needed()

    async def release(self, lease: _LimiterLease) -> None:
        try:
            await self._lease_backend.release(lease)
        finally:
            with self._state_lock:
                self._active_leases = max(self._active_leases - 1, 0)
        await self._finalize_close_if_needed()

    async def probe(self) -> None:
        await self._lease_backend.probe()

    async def aclose(self) -> None:
        with self._state_lock:
            self._close_requested = True
        await self._finalize_close_if_needed()

    async def _finalize_close_if_needed(self) -> None:
        with self._state_lock:
            if (
                not self._close_requested
                or self._is_closed
                or self._close_in_progress
                or self._active_leases
                or self._pending_acquires
            ):
                return
            self._close_in_progress = True

        try:
            await self._lease_backend.aclose()
        finally:
            with self._state_lock:
                self._is_closed = True
                self._close_in_progress = False


def _log_backend_fallback_recovered(settings: Settings) -> None:
    logfire.warning(
        "Vibecheck limiter Redis backend recovered from fallback",
        alert_type="ratelimit_fallback_recovered",
        limiter_backend="vibecheck-limiter-redis",
        limiter_consumer="vertex_gemini",
        limiter_primitive="distributed_lease",
        limiter_result="fallback_recovered",
        fail_open=False,
        per_instance_cap=_local_vertex_fallback_limit(settings),
        vibecheck_max_instances=settings.VIBECHECK_MAX_INSTANCES,
    )


def _log_backend_fallback_engaged(settings: Settings) -> None:
    logfire.warning(
        "Vibecheck limiter fallback engaged",
        alert_type="ratelimit_backend_unavailable",
        limiter_backend="vibecheck-limiter-redis",
        limiter_consumer="vertex_gemini",
        limiter_primitive="distributed_lease",
        limiter_result="fallback_engaged",
        fail_open=False,
        per_instance_cap=_local_vertex_fallback_limit(settings),
        vibecheck_max_instances=settings.VIBECHECK_MAX_INSTANCES,
    )


class _FallbackingBackend:
    backend_name = "fallbacking"

    def __init__(self, redis_backend: _RedisLimiterBackend, local_backend: _LocalLimiterBackend) -> None:
        self._redis_backend = redis_backend
        self._local_backend = local_backend
        self._state_lock = threading.Lock()
        self._backend_failures = 0
        self._fallback_active = False
        self._fallback_cooldown_until = 0.0
        self._probe_in_progress = False

    async def acquire(self, settings: Settings) -> _LimiterLease:
        if await self._probe_recovery_if_needed(settings):
            try:
                lease = await self._acquire_with_redis_backend(settings)
                self._on_redis_success(settings)
                return lease
            except VertexLimiterBackendUnavailableError:
                if self._on_redis_unavailable(settings):
                    return await self._acquire_with_local_backend(settings)
                raise

        if self._should_use_local():
            return await self._acquire_with_local_backend(settings)

        try:
            lease = await self._acquire_with_redis_backend(settings)
        except VertexLimiterBackendUnavailableError:
            if self._on_redis_unavailable(settings):
                return await self._acquire_with_local_backend(settings)
            raise

        self._on_redis_success(settings)
        return lease

    async def release(self, lease: _LimiterLease) -> None:
        if lease.backend == self._redis_backend.backend_name:
            await self._redis_backend.release(lease)
            return
        if lease.backend == self._local_backend.backend_name:
            await self._local_backend.release(lease)
            return
        raise ValueError(f"Invalid limiter lease backend: {lease.backend}")

    async def aclose(self) -> None:
        await self._redis_backend.aclose()
        await self._local_backend.aclose()

    async def _acquire_with_local_backend(self, settings: Settings) -> _LimiterLease:
        local_limit = _local_vertex_fallback_limit(settings)
        local_settings = settings.model_copy(update={"VERTEX_MAX_CONCURRENCY": local_limit})
        return await self._local_backend.acquire(local_settings)

    async def _acquire_with_redis_backend(self, settings: Settings) -> _LimiterLease:
        return await self._redis_backend.acquire(
            settings=settings,
        )

    def _should_use_local(self) -> bool:
        now = time.monotonic()
        with self._state_lock:
            return self._fallback_active and self._fallback_cooldown_until > now

    async def _probe_recovery_if_needed(self, settings: Settings) -> bool:
        if not self._fallback_active:
            return False

        now = time.monotonic()
        should_probe = False
        with self._state_lock:
            if (
                self._fallback_active
                and not self._probe_in_progress
                and self._fallback_cooldown_until <= now
            ):
                self._probe_in_progress = True
                should_probe = True

        if not should_probe:
            return False

        try:
            try:
                await self._redis_backend.probe()
            except VertexLimiterBackendUnavailableError:
                with self._state_lock:
                    self._backend_failures += 1
                    self._fallback_cooldown_until = time.monotonic() + _FALLBACK_COOLDOWN_SECONDS
                return False

            was_fallback = False
            with self._state_lock:
                was_fallback = self._fallback_active
                self._fallback_active = False
                self._backend_failures = 0
                self._fallback_cooldown_until = 0.0
            if was_fallback:
                _log_backend_fallback_recovered(settings)
            return True
        finally:
            with self._state_lock:
                self._probe_in_progress = False

    def _on_redis_unavailable(self, settings: Settings) -> bool:
        now = time.monotonic()
        became_fallback = False
        with self._state_lock:
            self._backend_failures += 1
            if self._fallback_active:
                self._fallback_cooldown_until = now + _FALLBACK_COOLDOWN_SECONDS
                return True
            if self._backend_failures >= _FALLBACK_FAILURE_THRESHOLD:
                if not self._fallback_active:
                    became_fallback = True
                    self._fallback_active = True
                    _log_backend_fallback_engaged(settings)

                self._fallback_cooldown_until = now + _FALLBACK_COOLDOWN_SECONDS

        return became_fallback or self._fallback_active

    def _on_redis_success(self, settings: Settings) -> None:
        with self._state_lock:
            was_fallback = self._fallback_active
            self._backend_failures = 0
            self._fallback_active = False
            self._fallback_cooldown_until = 0.0
            self._probe_in_progress = False
        if was_fallback:
            _log_backend_fallback_recovered(settings)



def _schedule_backend_close(
    backend: _LimiterBackend,
    loop: asyncio.AbstractEventLoop | None = None,
) -> None:
    close_request = backend.aclose()
    if not inspect.isawaitable(close_request):
        return

    if loop is not None and not loop.is_closed() and loop.is_running():
        loop.create_task(close_request)
        return

    try:
        running_loop = asyncio.get_running_loop()
    except RuntimeError:
        running_loop = None

    if running_loop is not None:
        # If called from inside a running event loop, a sync call-site can't
        # safely await directly. Best effort is to schedule it in-place.
        running_loop.create_task(close_request)
        return

    new_loop = asyncio.new_event_loop()
    try:
        new_loop.run_until_complete(close_request)
    finally:
        new_loop.close()


def _new_redis_client(settings: Settings) -> _RedisClient:
    # These timeouts intentionally exceed 10ms for Memorystore TLS+rediss paths:
    # a single TLS handshake/RTT on GCP can take >10ms under load and causes
    # spurious evalsha socket timeouts; these values preserve normal latency headroom
    # without waiting indefinitely on hung connections.
    kwargs: dict[str, Any] = {
        "max_connections": settings.VIBECHECK_LIMITER_REDIS_MAX_CONNECTIONS,
        "socket_timeout": 1.5,
        "socket_connect_timeout": 2.0,
        "health_check_interval": 30,
        "retry_on_timeout": True,
        "retry_on_error": [RedisConnectionError, RedisTimeoutError],
        "socket_keepalive": True,
    }
    keepalive_options = _redis_keepalive_options()
    if keepalive_options:
        kwargs["socket_keepalive_options"] = keepalive_options
    if settings.VIBECHECK_LIMITER_REDIS_URL.startswith("rediss://"):
        kwargs["ssl_ca_certs"] = settings.VIBECHECK_LIMITER_REDIS_CA_CERT_PATH or None
    return cast(_RedisClient, cast(object, redis_asyncio.from_url(settings.VIBECHECK_LIMITER_REDIS_URL, **kwargs)))


def _backend_for(settings: Settings, loop: asyncio.AbstractEventLoop) -> _LimiterBackend:
    global _backend  # noqa: PLW0603
    create_backend: Callable[[], _LimiterBackend]
    if settings.VIBECHECK_LIMITER_REDIS_URL:
        cache_key = (
            "redis",
            settings.VIBECHECK_LIMITER_REDIS_URL,
            settings.VIBECHECK_LIMITER_REDIS_CA_CERT_PATH,
            settings.VIBECHECK_LIMITER_REDIS_MAX_CONNECTIONS,
            settings.VIBECHECK_MAX_INSTANCES,
            settings.VERTEX_MAX_CONCURRENCY,
            loop,
        )

        def create_backend() -> _LimiterBackend:
            return _FallbackingBackend(
                _RedisLimiterBackend(_new_redis_client(settings)),
                _LocalLimiterBackend(),
            )

    else:
        cache_key = ("local", loop)

        def create_backend() -> _LimiterBackend:
            return _LocalLimiterBackend()

    with _backend_lock:
        if _backend is None or _backend[0] != cache_key:
            old_backend = _backend[1] if _backend is not None else None
            _backend = (cache_key, create_backend())
            if old_backend is not None:
                _schedule_backend_close(old_backend, loop)
        return _backend[1]


def _log_backend_unavailable(
    exc: BaseException,
    *,
    final_attempt: bool = False,
    will_raise: bool = False,
) -> None:
    log_kwargs: dict[str, Any] = {
        "alert_type": "ratelimit_backend_unavailable",
        "limiter_backend": "vibecheck-limiter-redis",
        "limiter_consumer": "vertex_gemini",
        "limiter_primitive": "distributed_lease",
        "limiter_result": "backend_unavailable",
        "fail_open": False,
        "error_class": type(exc).__name__,
    }

    if final_attempt or will_raise:
        logfire.warning(
            "Vibecheck limiter Redis backend unavailable",
            **log_kwargs,
        )
        return

    logfire.debug(
        "Vibecheck limiter Redis backend unavailable",
        **log_kwargs,
    )


@asynccontextmanager
async def vertex_slot(settings: Settings | None = None) -> AsyncIterator[None]:
    """Wait for a configured Vertex/Gemini execution slot."""
    resolved_settings = settings or get_settings()
    backend = _backend_for(resolved_settings, asyncio.get_running_loop())
    started = time.perf_counter()
    lease: _LimiterLease | None = None
    body_raised = False

    try:
        with logfire.span("vibecheck.vertex_limiter.wait") as span:
            lease = await backend.acquire(resolved_settings)
            wait_ms = (time.perf_counter() - started) * 1000
            VERTEX_LIMITER_WAIT_MS.record(
                wait_ms,
                {"vertex_limiter.backend": lease.backend},
            )
            span.set_attribute("vertex_limiter.wait_ms", wait_ms)
            span.set_attribute("vertex_limiter.max_concurrency", lease.max_concurrency)
            span.set_attribute("vertex_limiter.backend", lease.backend)
            span.set_attribute("vertex_limiter.active", lease.active)
            span.set_attribute("vertex_limiter.pending", lease.pending)

        yield
    except BaseException:
        body_raised = True
        raise
    finally:
        if lease is not None:
            try:
                await backend.release(lease)
            except VertexLimiterBackendUnavailableError:
                if body_raised:
                    pass
                else:
                    raise


def _reset_for_tests() -> None:
    global _state, _backend  # noqa: PLW0603
    old_backend: _LimiterBackend | None = None
    with _state_lock:
        _state = None
    with _backend_lock:
        if _backend is not None:
            old_backend = _backend[1]
        _backend = None
    if old_backend is not None:
        _schedule_backend_close(old_backend)
