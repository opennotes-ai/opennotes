from unittest.mock import AsyncMock

import pytest

from tests.redis_mock import create_stateful_redis_mock

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


async def test_api_key_limit_breaches_and_emits_retry_after():
    from src.url_content_scan.rate_limiter import UrlScanRateLimiter

    limiter = UrlScanRateLimiter(
        redis_client=create_stateful_redis_mock(),
        api_key_limit=2,
        api_key_window_seconds=3600,
    )

    first = await limiter.check_api_key_limit("key-123")
    second = await limiter.check_api_key_limit("key-123")
    third = await limiter.check_api_key_limit("key-123")

    assert first.allowed is True
    assert second.allowed is True
    assert third.allowed is False
    assert third.remaining == 0
    assert third.retry_after_seconds > 0


async def test_ip_and_normalized_url_limit_breaches_only_with_same_bucket():
    from src.url_content_scan.rate_limiter import UrlScanRateLimiter

    limiter = UrlScanRateLimiter(
        redis_client=create_stateful_redis_mock(),
        ip_url_limit=2,
        ip_url_window_seconds=60,
    )

    allowed_a = await limiter.check_ip_url_limit("203.0.113.9", "https://example.com/post")
    allowed_b = await limiter.check_ip_url_limit("203.0.113.9", "https://example.com/post")
    blocked = await limiter.check_ip_url_limit("203.0.113.9", "https://example.com/post")
    different_url = await limiter.check_ip_url_limit("203.0.113.9", "https://example.com/other")

    assert allowed_a.allowed is True
    assert allowed_b.allowed is True
    assert blocked.allowed is False
    assert blocked.retry_after_seconds > 0
    assert different_url.allowed is True


async def test_rate_limiter_fails_open_when_redis_is_unavailable():
    from src.url_content_scan.rate_limiter import UrlScanRateLimiter

    broken_redis = AsyncMock()
    broken_redis.incr = AsyncMock(side_effect=RuntimeError("redis down"))

    limiter = UrlScanRateLimiter(redis_client=broken_redis)

    result = await limiter.check_api_key_limit("key-123")

    assert result.allowed is True
    assert result.failed_open is True
    assert result.retry_after_seconds == 0
