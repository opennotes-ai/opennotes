from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from src.users.models import APIKey
from tests.redis_mock import create_stateful_redis_mock

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


def _make_api_key(key_id: str = "00000000-0000-0000-0000-000000000123") -> APIKey:
    api_key = APIKey()
    api_key.id = UUID(key_id)
    api_key.key_prefix = "prefix"
    api_key.name = "Vibecheck"
    return api_key


async def test_api_key_limit_breaches_and_emits_retry_after():
    from src.url_content_scan.rate_limiter import UrlScanRateLimiter

    limiter = UrlScanRateLimiter(
        redis_client=create_stateful_redis_mock(),
        api_key_limit=2,
        api_key_window_seconds=3600,
    )

    api_key = _make_api_key()

    first = await limiter.check_api_key_limit(api_key)
    second = await limiter.check_api_key_limit(api_key)
    third = await limiter.check_api_key_limit(api_key)

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

    result = await limiter.check_api_key_limit(_make_api_key())

    assert result.allowed is True
    assert result.failed_open is True
    assert result.retry_after_seconds == 0


async def test_rate_limiter_rejects_unpersisted_api_key_identifier() -> None:
    from src.url_content_scan.rate_limiter import UrlScanRateLimiter

    api_key = APIKey()
    api_key.id = None
    api_key.key_prefix = None
    api_key.name = None
    limiter = UrlScanRateLimiter(redis_client=create_stateful_redis_mock())

    with pytest.raises(ValueError, match="persisted APIKey identifier"):
        await limiter.check_api_key_limit(api_key)
