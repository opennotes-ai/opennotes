"""Redis-backed slowapi storage with local fail-open fallback."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from inspect import isawaitable
from typing import Any, ClassVar, TypeVar, cast

import logfire
from limits.aio.storage import MemoryStorage, MovingWindowSupport, RedisStorage, Storage
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError
from slowapi import Limiter

from src.config import Settings, get_settings
from src.monitoring_metrics import LIMITER_FAILOPEN_COUNT

_T = TypeVar("_T")
_REDIS_COMMAND_TIMEOUT_SECONDS = 0.01
_REDIS_TRANSPORT_ERRORS = (
    RedisConnectionError,
    RedisTimeoutError,
    TimeoutError,
    OSError,
)


class FailOpenRedisStorage(Storage, MovingWindowSupport):
    """Wrap Redis limits storage and degrade to memory on transport failure."""

    STORAGE_SCHEME: ClassVar[list[str] | None] = ["failopen+redis"]  # pyright: ignore[reportIncompatibleVariableOverride]

    def __init__(
        self,
        settings: Settings,
        *,
        consumer_label: str,
        primary_storage: Any | None = None,
    ) -> None:
        super().__init__(settings.VIBECHECK_LIMITER_REDIS_URL)
        self._consumer_label = consumer_label
        self._primary: Any = primary_storage or _build_redis_storage(settings)
        self._fallback = MemoryStorage()

    @property
    def base_exceptions(self) -> type[Exception] | tuple[type[Exception], ...]:
        return _REDIS_TRANSPORT_ERRORS

    async def incr(self, key: str, expiry: int, amount: int = 1) -> int:
        return await self._call_with_fallback(
            lambda storage: storage.incr(key, expiry, amount=amount),
            lambda fallback: fallback.incr(key, expiry, amount=amount),
        )

    async def get(self, key: str) -> int:
        return await self._call_with_fallback(
            lambda storage: storage.get(key),
            lambda fallback: fallback.get(key),
        )

    async def get_expiry(self, key: str) -> float:
        return await self._call_with_fallback(
            lambda storage: storage.get_expiry(key),
            lambda fallback: fallback.get_expiry(key),
        )

    async def reset(self) -> int | None:
        return await self._call_with_fallback(
            lambda storage: storage.reset(),
            lambda fallback: fallback.reset(),
        )

    async def clear(self, key: str) -> None:
        return await self._call_with_fallback(
            lambda storage: storage.clear(key),
            lambda fallback: fallback.clear(key),
        )

    async def check(self) -> bool:
        try:
            return bool(await _await_maybe(self._primary.check()))
        except _REDIS_TRANSPORT_ERRORS:
            return False

    async def acquire_entry(
        self, key: str, limit: int, expiry: int, amount: int = 1
    ) -> bool:
        return await self._call_with_fallback(
            lambda storage: storage.acquire_entry(key, limit, expiry, amount=amount),
            lambda fallback: fallback.acquire_entry(key, limit, expiry, amount=amount),
        )

    async def get_moving_window(self, key: str, limit: int, expiry: int) -> tuple[float, int]:
        return await self._call_with_fallback(
            lambda storage: storage.get_moving_window(key, limit, expiry),
            lambda fallback: fallback.get_moving_window(key, limit, expiry),
        )

    async def _call_with_fallback(
        self,
        primary_call: Callable[[Any], Awaitable[_T] | _T],
        fallback_call: Callable[[MemoryStorage], Awaitable[_T] | _T],
    ) -> _T:
        last_error: BaseException | None = None
        for _attempt in range(2):
            try:
                return await _await_maybe(primary_call(self._primary))
            except _REDIS_TRANSPORT_ERRORS as exc:
                last_error = exc

        if last_error is not None:
            self._record_failopen(last_error)
        return await _await_maybe(fallback_call(self._fallback))

    def _record_failopen(self, exc: BaseException) -> None:
        LIMITER_FAILOPEN_COUNT.labels(consumer=self._consumer_label).inc()
        logfire.warning(
            "Vibecheck limiter Redis backend unavailable; using local fallback",
            alert_type="ratelimit_backend_unavailable",
            limiter_backend="vibecheck-limiter-redis",
            limiter_consumer=self._consumer_label,
            limiter_primitive="moving_window_bucket",
            limiter_result="degraded_local_fallback",
            fail_open=True,
            error_class=type(exc).__name__,
        )


def build_limiter_storage(consumer_label: str) -> FailOpenRedisStorage | MemoryStorage:
    settings = get_settings()
    if not settings.VIBECHECK_LIMITER_REDIS_URL:
        return MemoryStorage()
    return FailOpenRedisStorage(settings, consumer_label=consumer_label)


def clear_memory_storage_state(storage: object) -> None:
    """Clear in-process limiter state used by local tests."""
    memory_storage: MemoryStorage | None = None
    if isinstance(storage, FailOpenRedisStorage):
        memory_storage = storage._fallback
    elif isinstance(storage, MemoryStorage):
        memory_storage = storage

    if memory_storage is None:
        return

    memory_storage_any = cast(Any, memory_storage)
    memory_storage_any.storage.clear()
    memory_storage_any.events.clear()


class ContractLoggingLimiter(Limiter):
    """Slowapi Limiter that records contract metrics when fallback engages."""

    def __init__(self, *args: Any, consumer_label: str, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._consumer_label = consumer_label

    def _check_request_limit(self, *args: Any, **kwargs: Any) -> None:
        was_dead = self._storage_dead
        super()._check_request_limit(*args, **kwargs)
        if not was_dead and self._storage_dead:
            LIMITER_FAILOPEN_COUNT.labels(consumer=self._consumer_label).inc()
            logfire.warning(
                "Vibecheck limiter Redis backend unavailable; using slowapi fallback",
                alert_type="ratelimit_backend_unavailable",
                limiter_backend="vibecheck-limiter-redis",
                limiter_consumer=self._consumer_label,
                limiter_primitive="moving_window_bucket",
                limiter_result="degraded_local_fallback",
                fail_open=True,
                error_class="StorageError",
            )


def build_slowapi_limiter(
    *,
    key_func: Callable[..., str],
    consumer_label: str,
) -> Limiter:
    settings = get_settings()
    if not settings.VIBECHECK_LIMITER_REDIS_URL:
        return ContractLoggingLimiter(
            key_func=key_func,
            consumer_label=consumer_label,
            strategy="moving-window",
        )
    return ContractLoggingLimiter(
        key_func=key_func,
        consumer_label=consumer_label,
        strategy="moving-window",
        storage_uri=settings.VIBECHECK_LIMITER_REDIS_URL,
        storage_options=_redis_storage_options(settings),
        in_memory_fallback_enabled=True,
    )


async def _await_maybe(value: Awaitable[_T] | _T) -> _T:
    if isawaitable(value):
        return await cast(Awaitable[_T], value)
    return cast(_T, value)


def _build_redis_storage(settings: Settings) -> RedisStorage:
    return RedisStorage(
        settings.VIBECHECK_LIMITER_REDIS_URL,
        implementation="redispy",
        **_redis_storage_options(settings),
    )


def _redis_storage_options(settings: Settings) -> dict[str, Any]:
    options: dict[str, Any] = {
        "socket_timeout": _REDIS_COMMAND_TIMEOUT_SECONDS,
        "socket_connect_timeout": _REDIS_COMMAND_TIMEOUT_SECONDS,
        "retry_on_timeout": True,
        "retry_on_error": [RedisConnectionError, RedisTimeoutError],
        "max_connections": settings.VIBECHECK_LIMITER_REDIS_MAX_CONNECTIONS,
        "key_prefix": "",
    }
    if settings.VIBECHECK_LIMITER_REDIS_URL.startswith("rediss://"):
        options["ssl_ca_certs"] = settings.VIBECHECK_LIMITER_REDIS_CA_CERT_PATH or None
    return options
