"""
Integration tests for rate limiting using stateful Redis mock.

These tests verify that rate limiting actually works by using a stateful
Redis mock that simulates real Redis behavior with sorted sets.
"""

import asyncio
from unittest.mock import patch

import pytest

from src.webhooks.rate_limit import RateLimiter
from tests.redis_mock import create_stateful_redis_mock


@pytest.fixture
async def rate_limiter_with_stateful_mock():
    """Create a rate limiter with stateful Redis mock"""
    rl = RateLimiter()
    mock_redis = create_stateful_redis_mock()
    rl.redis_client = mock_redis
    return rl


class TestRateLimiterIntegration:
    """Integration tests that verify actual rate limiting behavior"""

    @pytest.mark.asyncio
    async def test_rate_limit_allows_requests_within_limit(self, rate_limiter_with_stateful_mock):
        """Test that requests are allowed when within rate limit"""
        limiter = rate_limiter_with_stateful_mock
        community_server_id = "community_server_integration_1"

        with patch("src.webhooks.rate_limit.settings") as mock_settings:
            mock_settings.WEBHOOK_RATE_LIMIT_PER_COMMUNITY_SERVER = 10
            mock_settings.WEBHOOK_RATE_LIMIT_WINDOW = 60

            # Make 5 requests - all should be allowed
            for i in range(5):
                allowed, remaining = await limiter.check_rate_limit(community_server_id)
                assert allowed is True, f"Request {i + 1} should be allowed"
                assert remaining >= 0, "Remaining count should be non-negative"

    @pytest.mark.asyncio
    async def test_rate_limit_rejects_requests_beyond_limit(self, rate_limiter_with_stateful_mock):
        """Test that requests are rejected when rate limit is exceeded"""
        limiter = rate_limiter_with_stateful_mock
        community_server_id = "community_server_integration_2"

        with patch("src.webhooks.rate_limit.settings") as mock_settings:
            mock_settings.WEBHOOK_RATE_LIMIT_PER_COMMUNITY_SERVER = 5
            mock_settings.WEBHOOK_RATE_LIMIT_WINDOW = 60

            # Make 5 requests - all should be allowed
            for i in range(5):
                allowed, remaining = await limiter.check_rate_limit(community_server_id)
                assert allowed is True, f"Request {i + 1} should be allowed"

            # The 6th request should be rejected
            allowed, remaining = await limiter.check_rate_limit(community_server_id)
            assert allowed is False, "Request beyond limit should be rejected"
            assert remaining == 0, "No remaining requests should be available"

    @pytest.mark.asyncio
    async def test_rate_limit_tracks_remaining_count_correctly(
        self, rate_limiter_with_stateful_mock
    ):
        """Test that remaining count decreases correctly with each request"""
        limiter = rate_limiter_with_stateful_mock
        community_server_id = "community_server_integration_3"

        with patch("src.webhooks.rate_limit.settings") as mock_settings:
            mock_settings.WEBHOOK_RATE_LIMIT_PER_COMMUNITY_SERVER = 10
            mock_settings.WEBHOOK_RATE_LIMIT_WINDOW = 60

            # First request
            allowed, remaining = await limiter.check_rate_limit(community_server_id)
            assert allowed is True
            assert remaining == 9, "Should have 9 remaining after first request"

            # Second request
            allowed, remaining = await limiter.check_rate_limit(community_server_id)
            assert allowed is True
            assert remaining == 8, "Should have 8 remaining after second request"

            # Third request
            allowed, remaining = await limiter.check_rate_limit(community_server_id)
            assert allowed is True
            assert remaining == 7, "Should have 7 remaining after third request"

    @pytest.mark.asyncio
    async def test_rate_limit_separate_tracking_per_guild(self, rate_limiter_with_stateful_mock):
        """Test that different servers have separate rate limits"""
        limiter = rate_limiter_with_stateful_mock
        community_server_id_1 = "community_server_integration_4a"
        community_server_id_2 = "community_server_integration_4b"

        with patch("src.webhooks.rate_limit.settings") as mock_settings:
            mock_settings.WEBHOOK_RATE_LIMIT_PER_COMMUNITY_SERVER = 5
            mock_settings.WEBHOOK_RATE_LIMIT_WINDOW = 60

            # Make 5 requests for server 1 - should hit limit
            for _ in range(5):
                allowed, _ = await limiter.check_rate_limit(community_server_id_1)
                assert allowed is True

            # Server 1 should be at limit
            allowed, remaining = await limiter.check_rate_limit(community_server_id_1)
            assert allowed is False
            assert remaining == 0

            # Server 2 should still have full quota
            allowed, remaining = await limiter.check_rate_limit(community_server_id_2)
            assert allowed is True
            assert remaining == 4  # 5 - 1 (current request)

    @pytest.mark.asyncio
    async def test_rate_limit_separate_tracking_per_user(self, rate_limiter_with_stateful_mock):
        """Test that different users within a server have separate rate limits"""
        limiter = rate_limiter_with_stateful_mock
        community_server_id = "community_server_integration_5"
        user_id_1 = "user_5a"
        user_id_2 = "user_5b"

        with patch("src.webhooks.rate_limit.settings") as mock_settings:
            mock_settings.WEBHOOK_RATE_LIMIT_PER_COMMUNITY_SERVER = 3
            mock_settings.WEBHOOK_RATE_LIMIT_WINDOW = 60

            # Make 3 requests for user 1 - should hit limit
            for _ in range(3):
                allowed, _ = await limiter.check_rate_limit(community_server_id, user_id_1)
                assert allowed is True

            # User 1 should be at limit
            allowed, remaining = await limiter.check_rate_limit(community_server_id, user_id_1)
            assert allowed is False
            assert remaining == 0

            # User 2 should still have full quota
            allowed, remaining = await limiter.check_rate_limit(community_server_id, user_id_2)
            assert allowed is True
            assert remaining == 2

    @pytest.mark.asyncio
    async def test_rate_limit_at_exact_limit(self, rate_limiter_with_stateful_mock):
        """Test behavior when exactly at the rate limit"""
        limiter = rate_limiter_with_stateful_mock
        community_server_id = "community_server_integration_6"

        with patch("src.webhooks.rate_limit.settings") as mock_settings:
            mock_settings.WEBHOOK_RATE_LIMIT_PER_COMMUNITY_SERVER = 3
            mock_settings.WEBHOOK_RATE_LIMIT_WINDOW = 60

            # Make 2 requests
            for _ in range(2):
                allowed, _ = await limiter.check_rate_limit(community_server_id)
                assert allowed is True

            # 3rd request should still be allowed (we're at limit - 1)
            allowed, remaining = await limiter.check_rate_limit(community_server_id)
            assert allowed is True
            assert remaining == 0

            # 4th request should be rejected
            allowed, remaining = await limiter.check_rate_limit(community_server_id)
            assert allowed is False
            assert remaining == 0

    @pytest.mark.asyncio
    async def test_get_rate_limit_info_reflects_actual_usage(self, rate_limiter_with_stateful_mock):
        """Test that get_rate_limit_info returns accurate information"""
        limiter = rate_limiter_with_stateful_mock
        community_server_id = "community_server_integration_7"

        with patch("src.webhooks.rate_limit.settings") as mock_settings:
            mock_settings.WEBHOOK_RATE_LIMIT_PER_COMMUNITY_SERVER = 10
            mock_settings.WEBHOOK_RATE_LIMIT_WINDOW = 60

            # Initially, should have full quota
            info = await limiter.get_rate_limit_info(community_server_id)
            assert info["limit"] == 10
            assert info["remaining"] == 10
            assert info["window"] == 60

            # Make 3 requests
            for _ in range(3):
                await limiter.check_rate_limit(community_server_id)

            # Should now have 7 remaining
            info = await limiter.get_rate_limit_info(community_server_id)
            assert info["remaining"] == 7

    @pytest.mark.asyncio
    async def test_rate_limit_concurrent_requests(self, rate_limiter_with_stateful_mock):
        """Test rate limiting with concurrent requests"""
        limiter = rate_limiter_with_stateful_mock
        community_server_id = "community_server_integration_8"

        with patch("src.webhooks.rate_limit.settings") as mock_settings:
            mock_settings.WEBHOOK_RATE_LIMIT_PER_COMMUNITY_SERVER = 10
            mock_settings.WEBHOOK_RATE_LIMIT_WINDOW = 60

            # Make 5 concurrent requests
            tasks = [limiter.check_rate_limit(community_server_id) for _ in range(5)]
            results = await asyncio.gather(*tasks)

            # All 5 should be allowed
            for allowed, _remaining in results:
                assert allowed is True

            # Make 5 more concurrent requests
            tasks = [limiter.check_rate_limit(community_server_id) for _ in range(5)]
            results = await asyncio.gather(*tasks)

            # All should still be allowed (total 10)
            for allowed, _remaining in results:
                assert allowed is True

            # One more should be rejected
            allowed, _remaining = await limiter.check_rate_limit(community_server_id)
            assert allowed is False

    @pytest.mark.asyncio
    async def test_rate_limit_zero_initial_count(self, rate_limiter_with_stateful_mock):
        """Test that a fresh server starts with zero count"""
        limiter = rate_limiter_with_stateful_mock
        community_server_id = "community_server_integration_9"

        with patch("src.webhooks.rate_limit.settings") as mock_settings:
            mock_settings.WEBHOOK_RATE_LIMIT_PER_COMMUNITY_SERVER = 100
            mock_settings.WEBHOOK_RATE_LIMIT_WINDOW = 60

            # First request should have maximum remaining count
            allowed, remaining = await limiter.check_rate_limit(community_server_id)
            assert allowed is True
            assert remaining == 99  # 100 - 1 (current request)
