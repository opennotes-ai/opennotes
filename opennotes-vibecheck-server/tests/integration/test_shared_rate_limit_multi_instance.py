from __future__ import annotations

import os
import statistics
import time
from collections.abc import Iterator

import httpx
import pytest
from docker.errors import NotFound
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from limits import parse
from limits.aio.strategies import MovingWindowRateLimiter
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from testcontainers.redis import RedisContainer

from src.config import get_settings
from src.routes._rate_limit_keys import (
    server_poll_rate_key,
    server_retry_rate_key,
    server_submit_rate_key,
)
from src.services import limiter_storage
from src.services.limiter_storage import build_limiter_storage, build_slowapi_limiter


@pytest.fixture(scope="module")
def redis_container() -> Iterator[RedisContainer]:
    with RedisContainer("redis:7-alpine") as redis:
        yield redis


@pytest.fixture
def limiter_env(monkeypatch: pytest.MonkeyPatch, redis_container: RedisContainer) -> str:
    redis_url = _redis_url(redis_container)
    monkeypatch.setenv("VIBECHECK_LIMITER_REDIS_URL", redis_url)
    monkeypatch.setenv("VIBECHECK_LIMITER_KEY_SALT", "integration-salt")
    get_settings.cache_clear()
    return redis_url


def _redis_url(redis: RedisContainer) -> str:
    return f"redis://{redis.get_container_host_ip()}:{redis.get_exposed_port(6379)}/0"


def _make_app() -> FastAPI:
    limiter = build_slowapi_limiter(
        key_func=server_submit_rate_key,
        consumer_label="vibecheck_server_submit",
    )
    poll_storage = build_limiter_storage("vibecheck_server_poll")
    poll_strategy = MovingWindowRateLimiter(poll_storage)
    poll_limit = parse("2/minute")

    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # pyright: ignore[reportArgumentType]
    app.add_middleware(SlowAPIMiddleware)

    @app.post("/api/analyze")
    @limiter.shared_limit("2/minute", scope="vibecheck-submit")
    async def analyze(request: Request) -> dict[str, bool]:
        return {"ok": True}

    @app.get("/api/analyze/{job_id}")
    async def poll(request: Request, job_id: str) -> JSONResponse:
        del job_id
        allowed = await poll_strategy.hit(poll_limit, server_poll_rate_key(request))
        if not allowed:
            return JSONResponse({"error_code": "rate_limited"}, status_code=429)
        return JSONResponse({"ok": True})

    @app.post("/api/analyze/{job_id}/retry/{slug}")
    @limiter.limit("2/minute", key_func=server_retry_rate_key)
    async def retry(request: Request, job_id: str, slug: str) -> dict[str, bool]:
        del request, job_id, slug
        return {"ok": True}

    return app


def _client(app: FastAPI) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app, client=("203.0.113.99", 1234))
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_submit_bucket_is_shared_across_instances(limiter_env: str) -> None:
    del limiter_env
    async with _client(_make_app()) as client_a, _client(_make_app()) as client_b:
        first = await client_a.post("/api/analyze")
        second = await client_b.post("/api/analyze")
        third = await client_a.post("/api/analyze")

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429


@pytest.mark.asyncio
async def test_poll_bucket_is_shared_across_instances(limiter_env: str) -> None:
    del limiter_env
    job_id = "7f6d0f28-0a72-4c85-9117-6f376f222222"
    async with _client(_make_app()) as client_a, _client(_make_app()) as client_b:
        first = await client_a.get(f"/api/analyze/{job_id}")
        second = await client_b.get(f"/api/analyze/{job_id}")
        third = await client_a.get(f"/api/analyze/{job_id}")

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429


@pytest.mark.asyncio
async def test_retry_bucket_is_shared_across_instances(limiter_env: str) -> None:
    del limiter_env
    job_id = "7f6d0f28-0a72-4c85-9117-6f376f333333"
    async with _client(_make_app()) as client_a, _client(_make_app()) as client_b:
        first = await client_a.post(f"/api/analyze/{job_id}/retry/facts_claims")
        second = await client_b.post(f"/api/analyze/{job_id}/retry/facts_claims")
        third = await client_a.post(f"/api/analyze/{job_id}/retry/facts_claims")

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429


@pytest.mark.asyncio
async def test_poll_fail_open_when_redis_stops(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    warnings: list[dict[str, object]] = []

    def record_warning(message: str, **attrs: object) -> None:
        del message
        warnings.append(attrs)

    monkeypatch.setattr(limiter_storage.logfire, "warning", record_warning)
    redis = RedisContainer("redis:7-alpine")
    redis.start()
    try:
        monkeypatch.setenv("VIBECHECK_LIMITER_REDIS_URL", _redis_url(redis))
        monkeypatch.setenv("VIBECHECK_LIMITER_KEY_SALT", "integration-salt")
        get_settings.cache_clear()
        app = _make_app()
        redis.stop()

        async with _client(app) as client:
            response = await client.get("/api/analyze/stopped-redis")
    finally:
        get_settings.cache_clear()
        try:
            redis.stop()
        except NotFound:
            pass

    assert response.status_code == 200
    assert warnings
    assert warnings[0]["alert_type"] == "ratelimit_backend_unavailable"
    assert warnings[0]["limiter_consumer"] == "vibecheck_server_poll"
    assert warnings[0]["fail_open"] is True


@pytest.mark.asyncio
async def test_limiter_latency_p99_under_20ms_when_enabled(limiter_env: str) -> None:
    if os.getenv("RUN_LIMITER_LATENCY_TEST") != "1":
        pytest.skip("latency assertion is opt-in to avoid shared-runner noise")

    del limiter_env
    app = _make_app()
    durations_ms: list[float] = []

    async with _client(app) as client:
        for index in range(100):
            started = time.perf_counter_ns()
            response = await client.get(f"/api/analyze/latency-{index}")
            durations_ms.append((time.perf_counter_ns() - started) / 1_000_000)
            assert response.status_code == 200

    assert statistics.quantiles(durations_ms, n=100)[98] < 20
