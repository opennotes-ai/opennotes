from __future__ import annotations

import pytest
from limits.aio.storage import MemoryStorage
from prometheus_client import REGISTRY
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

from src.config import Settings
from src.services import limiter_storage


class _FakePrimaryStorage:
    def __init__(self) -> None:
        self.fail = False
        self.entries: list[tuple[str, int, int, int]] = []

    async def acquire_entry(
        self, key: str, limit: int, expiry: int, amount: int = 1
    ) -> bool:
        if self.fail:
            raise RedisConnectionError("redis unavailable")
        self.entries.append((key, limit, expiry, amount))
        return True

    async def get_moving_window(self, key: str, limit: int, expiry: int) -> tuple[float, int]:
        if self.fail:
            raise RedisConnectionError("redis unavailable")
        return (0.0, len(self.entries))

    async def incr(self, key: str, expiry: int, amount: int = 1) -> int:
        if self.fail:
            raise RedisConnectionError("redis unavailable")
        return amount

    async def get(self, key: str) -> int:
        if self.fail:
            raise RedisConnectionError("redis unavailable")
        return len(self.entries)

    async def get_expiry(self, key: str) -> float:
        if self.fail:
            raise RedisConnectionError("redis unavailable")
        return 1.0

    async def reset(self) -> int:
        self.entries.clear()
        return 1

    async def clear(self, key: str) -> None:
        self.entries = [entry for entry in self.entries if entry[0] != key]

    async def check(self) -> bool:
        return not self.fail


@pytest.fixture
def fake_primary() -> _FakePrimaryStorage:
    return _FakePrimaryStorage()


@pytest.fixture
def storage(fake_primary: _FakePrimaryStorage) -> limiter_storage.FailOpenRedisStorage:
    return limiter_storage.FailOpenRedisStorage(
        Settings(VIBECHECK_LIMITER_REDIS_URL="redis://localhost:6379/0"),
        consumer_label="vibecheck_server_submit",
        primary_storage=fake_primary,
    )


@pytest.mark.asyncio
async def test_fail_open_storage_uses_primary_when_redis_is_available(
    storage: limiter_storage.FailOpenRedisStorage,
    fake_primary: _FakePrimaryStorage,
):
    assert await storage.acquire_entry("bucket", 2, 60)
    assert fake_primary.entries == [("bucket", 2, 60, 1)]


@pytest.mark.asyncio
async def test_fail_open_storage_delegates_to_memory_and_logs_on_redis_error(
    storage: limiter_storage.FailOpenRedisStorage,
    fake_primary: _FakePrimaryStorage,
    monkeypatch: pytest.MonkeyPatch,
):
    warnings: list[tuple[str, dict[str, object]]] = []

    def record_warning(message: str, **attrs: object) -> None:
        warnings.append((message, attrs))

    monkeypatch.setattr(limiter_storage.logfire, "warning", record_warning)
    fake_primary.fail = True

    before = REGISTRY.get_sample_value(
        "vibecheck_limiter_failopen_total",
        labels={"consumer": "vibecheck_server_submit"},
    ) or 0.0

    assert await storage.acquire_entry("bucket", 2, 60)

    after = REGISTRY.get_sample_value(
        "vibecheck_limiter_failopen_total",
        labels={"consumer": "vibecheck_server_submit"},
    )
    assert after == before + 1
    assert warnings
    assert warnings[0][1] == {
        "alert_type": "ratelimit_backend_unavailable",
        "limiter_backend": "vibecheck-limiter-redis",
        "limiter_consumer": "vibecheck_server_submit",
        "limiter_primitive": "moving_window_bucket",
        "limiter_result": "degraded_local_fallback",
        "fail_open": True,
        "error_class": "ConnectionError",
    }


@pytest.mark.asyncio
async def test_fail_open_storage_recovers_to_primary_after_error(
    storage: limiter_storage.FailOpenRedisStorage,
    fake_primary: _FakePrimaryStorage,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(limiter_storage.logfire, "warning", lambda *args, **kwargs: None)
    fake_primary.fail = True
    assert await storage.acquire_entry("bucket", 2, 60)

    fake_primary.fail = False
    assert await storage.acquire_entry("bucket", 2, 60)

    assert fake_primary.entries == [("bucket", 2, 60, 1)]


def test_build_limiter_storage_uses_memory_when_redis_url_is_empty(monkeypatch):
    monkeypatch.delenv("VIBECHECK_LIMITER_REDIS_URL", raising=False)
    from src.config import get_settings

    get_settings.cache_clear()
    try:
        storage = limiter_storage.build_limiter_storage("vibecheck_server_poll")
    finally:
        get_settings.cache_clear()

    assert isinstance(storage, MemoryStorage)


def test_build_limiter_storage_uses_redis_wrapper_when_url_is_set(monkeypatch):
    monkeypatch.setenv("VIBECHECK_LIMITER_REDIS_URL", "redis://localhost:6379/0")
    from src.config import get_settings

    get_settings.cache_clear()
    try:
        storage = limiter_storage.build_limiter_storage("vibecheck_server_poll")
    finally:
        get_settings.cache_clear()

    assert isinstance(storage, limiter_storage.FailOpenRedisStorage)


def test_redis_storage_options_uses_configured_socket_timeout():
    """Verify socket_timeout comes from settings, not hardcoded 0.01."""
    settings = Settings(
        VIBECHECK_LIMITER_REDIS_URL="redis://localhost:6379/0",
        VIBECHECK_LIMITER_REDIS_REQUEST_SOCKET_TIMEOUT_SECONDS=1.5,
    )
    options = limiter_storage._redis_storage_options(settings)
    assert options["socket_timeout"] == 1.5
    assert options["socket_timeout"] != 0.01


def test_redis_storage_options_uses_configured_connect_timeout():
    """Verify socket_connect_timeout comes from settings, not hardcoded 0.01."""
    settings = Settings(
        VIBECHECK_LIMITER_REDIS_URL="redis://localhost:6379/0",
        VIBECHECK_LIMITER_REDIS_REQUEST_CONNECT_TIMEOUT_SECONDS=2.0,
    )
    options = limiter_storage._redis_storage_options(settings)
    assert options["socket_connect_timeout"] == 2.0
    assert options["socket_connect_timeout"] != 0.01


def test_redis_storage_options_preserves_other_settings():
    """Verify that other Redis storage options are preserved."""
    settings = Settings(
        VIBECHECK_LIMITER_REDIS_URL="redis://localhost:6379/0",
        VIBECHECK_LIMITER_REDIS_MAX_CONNECTIONS=50,
        VIBECHECK_LIMITER_REDIS_REQUEST_SOCKET_TIMEOUT_SECONDS=1.5,
        VIBECHECK_LIMITER_REDIS_REQUEST_CONNECT_TIMEOUT_SECONDS=2.0,
    )
    options = limiter_storage._redis_storage_options(settings)
    assert options["retry_on_timeout"] is True
    assert options["retry_on_error"] == [RedisConnectionError, RedisTimeoutError]
    assert options["max_connections"] == 50
    assert options["key_prefix"] == ""


def test_redis_storage_options_with_rediss_includes_ca_certs():
    """Verify CA certs are included for rediss:// URLs."""
    settings = Settings(
        VIBECHECK_LIMITER_REDIS_URL="rediss://localhost:6379/0",
        VIBECHECK_LIMITER_REDIS_CA_CERT_PATH="/path/to/ca.pem",
        VIBECHECK_LIMITER_REDIS_REQUEST_SOCKET_TIMEOUT_SECONDS=1.5,
        VIBECHECK_LIMITER_REDIS_REQUEST_CONNECT_TIMEOUT_SECONDS=2.0,
    )
    options = limiter_storage._redis_storage_options(settings)
    assert options["ssl_ca_certs"] == "/path/to/ca.pem"


def test_build_slowapi_limiter_uses_configured_timeouts(monkeypatch):
    """Verify build_slowapi_limiter passes configured timeouts to storage_options."""
    monkeypatch.setenv("VIBECHECK_LIMITER_REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("VIBECHECK_LIMITER_REDIS_REQUEST_SOCKET_TIMEOUT_SECONDS", "1.5")
    monkeypatch.setenv("VIBECHECK_LIMITER_REDIS_REQUEST_CONNECT_TIMEOUT_SECONDS", "2.0")
    from src.config import get_settings

    get_settings.cache_clear()
    try:
        limiter = limiter_storage.build_slowapi_limiter(
            key_func=lambda: "test",
            consumer_label="test_limiter",
        )
        assert limiter._storage_options["socket_timeout"] == 1.5
        assert limiter._storage_options["socket_connect_timeout"] == 2.0
    finally:
        get_settings.cache_clear()
