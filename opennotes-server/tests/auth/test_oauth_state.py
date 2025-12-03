"""
Tests for OAuth2 state parameter validation.

Tests the CSRF protection mechanism for OAuth2 flows by validating
the state parameter generation, storage, and validation.
"""

import time
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.unit


class TestGenerateOAuthState:
    """Tests for generate_oauth_state function."""

    def test_generates_url_safe_string(self):
        """State should be URL-safe base64 encoded."""
        from src.auth.oauth_state import generate_oauth_state

        state = generate_oauth_state()

        assert isinstance(state, str)
        assert len(state) > 0
        for char in state:
            assert char.isalnum() or char in "-_="

    def test_generates_unique_states(self):
        """Each call should generate a unique state value."""
        from src.auth.oauth_state import generate_oauth_state

        states = [generate_oauth_state() for _ in range(100)]

        assert len(set(states)) == 100

    def test_generates_sufficient_entropy(self):
        """State should have at least 256 bits of entropy (32 bytes)."""
        from src.auth.oauth_state import generate_oauth_state

        state = generate_oauth_state()

        assert len(state) >= 32


class TestStoreOAuthState:
    """Tests for store_oauth_state function."""

    @pytest.mark.asyncio
    async def test_stores_state_in_redis(self):
        """State should be stored in Redis with correct key format."""
        from tests.redis_mock import create_stateful_redis_mock

        mock_redis = create_stateful_redis_mock()

        with patch("src.auth.oauth_state.redis_client") as mock_client:
            mock_client.client = mock_redis

            from src.auth.oauth_state import store_oauth_state

            state = "test-state-value"
            await store_oauth_state(state)

            mock_redis.setex.assert_called_once()
            call_args = mock_redis.setex.call_args
            key = call_args[0][0]
            ttl = call_args[0][1]

            assert key == "oauth:state:test-state-value"
            assert ttl == 600

    @pytest.mark.asyncio
    async def test_stores_state_with_custom_ttl(self):
        """State can be stored with custom TTL."""
        from tests.redis_mock import create_stateful_redis_mock

        mock_redis = create_stateful_redis_mock()

        with patch("src.auth.oauth_state.redis_client") as mock_client:
            mock_client.client = mock_redis

            from src.auth.oauth_state import store_oauth_state

            await store_oauth_state("test-state", ttl=300)

            call_args = mock_redis.setex.call_args
            ttl = call_args[0][1]
            assert ttl == 300

    @pytest.mark.asyncio
    async def test_raises_error_when_redis_unavailable(self):
        """Should raise OAuthStateError when Redis is unavailable."""
        with patch("src.auth.oauth_state.redis_client") as mock_client:
            mock_client.client = None

            from src.auth.oauth_state import OAuthStateError, store_oauth_state

            with pytest.raises(OAuthStateError, match="Redis not available"):
                await store_oauth_state("test-state")


class TestValidateOAuthState:
    """Tests for validate_oauth_state function."""

    @pytest.mark.asyncio
    async def test_validates_existing_state(self):
        """Valid state should return True and be consumed."""
        from tests.redis_mock import create_stateful_redis_mock

        mock_redis = create_stateful_redis_mock()
        await mock_redis._setex("oauth:state:valid-state", 600, "1")

        with patch("src.auth.oauth_state.redis_client") as mock_client:
            mock_client.client = mock_redis

            from src.auth.oauth_state import validate_oauth_state

            result = await validate_oauth_state("valid-state")

            assert result is True
            assert await mock_redis._exists("oauth:state:valid-state") == 0

    @pytest.mark.asyncio
    async def test_rejects_nonexistent_state(self):
        """Invalid state should return False."""
        from tests.redis_mock import create_stateful_redis_mock

        mock_redis = create_stateful_redis_mock()

        with patch("src.auth.oauth_state.redis_client") as mock_client:
            mock_client.client = mock_redis

            from src.auth.oauth_state import validate_oauth_state

            result = await validate_oauth_state("nonexistent-state")

            assert result is False

    @pytest.mark.asyncio
    async def test_state_can_only_be_used_once(self):
        """State should be consumed after validation (one-time use)."""
        from tests.redis_mock import create_stateful_redis_mock

        mock_redis = create_stateful_redis_mock()
        await mock_redis._setex("oauth:state:one-time-state", 600, "1")

        with patch("src.auth.oauth_state.redis_client") as mock_client:
            mock_client.client = mock_redis

            from src.auth.oauth_state import validate_oauth_state

            first_result = await validate_oauth_state("one-time-state")
            second_result = await validate_oauth_state("one-time-state")

            assert first_result is True
            assert second_result is False

    @pytest.mark.asyncio
    async def test_rejects_expired_state(self):
        """Expired state should be rejected."""
        from tests.redis_mock import create_stateful_redis_mock

        mock_redis = create_stateful_redis_mock()
        await mock_redis._setex("oauth:state:expired-state", 1, "1")

        with patch("src.auth.oauth_state.redis_client") as mock_client:
            mock_client.client = mock_redis

            time.sleep(1.5)

            from src.auth.oauth_state import validate_oauth_state

            result = await validate_oauth_state("expired-state")

            assert result is False

    @pytest.mark.asyncio
    async def test_rejects_empty_state(self):
        """Empty state should be rejected."""
        from tests.redis_mock import create_stateful_redis_mock

        mock_redis = create_stateful_redis_mock()

        with patch("src.auth.oauth_state.redis_client") as mock_client:
            mock_client.client = mock_redis

            from src.auth.oauth_state import validate_oauth_state

            result = await validate_oauth_state("")

            assert result is False

    @pytest.mark.asyncio
    async def test_rejects_none_state(self):
        """None state should be rejected."""
        from tests.redis_mock import create_stateful_redis_mock

        mock_redis = create_stateful_redis_mock()

        with patch("src.auth.oauth_state.redis_client") as mock_client:
            mock_client.client = mock_redis

            from src.auth.oauth_state import validate_oauth_state

            result = await validate_oauth_state(None)

            assert result is False

    @pytest.mark.asyncio
    async def test_raises_error_when_redis_unavailable(self):
        """Should raise OAuthStateError when Redis is unavailable."""
        with patch("src.auth.oauth_state.redis_client") as mock_client:
            mock_client.client = None

            from src.auth.oauth_state import OAuthStateError, validate_oauth_state

            with pytest.raises(OAuthStateError, match="Redis not available"):
                await validate_oauth_state("test-state")


class TestCreateOAuthStateWithUrl:
    """Tests for create_oauth_state_with_url function."""

    @pytest.mark.asyncio
    async def test_creates_state_and_returns_url(self):
        """Should generate state, store it, and return Discord OAuth URL."""
        from tests.redis_mock import create_stateful_redis_mock

        mock_redis = create_stateful_redis_mock()

        with (
            patch("src.auth.oauth_state.redis_client") as mock_client,
            patch("src.auth.oauth_state.settings") as mock_settings,
        ):
            mock_client.client = mock_redis
            mock_settings.DISCORD_CLIENT_ID = "test-client-id"
            mock_settings.DISCORD_OAUTH_REDIRECT_URI = "http://localhost/callback"

            from src.auth.oauth_state import create_oauth_state_with_url

            state, url = await create_oauth_state_with_url()

            assert isinstance(state, str)
            assert len(state) >= 32

            assert "https://discord.com/oauth2/authorize" in url
            assert "client_id=test-client-id" in url
            assert f"state={state}" in url
            assert "response_type=code" in url
            assert "scope=" in url

    @pytest.mark.asyncio
    async def test_url_contains_correct_redirect_uri(self):
        """OAuth URL should contain the configured redirect URI."""
        from urllib.parse import quote

        from tests.redis_mock import create_stateful_redis_mock

        mock_redis = create_stateful_redis_mock()

        with (
            patch("src.auth.oauth_state.redis_client") as mock_client,
            patch("src.auth.oauth_state.settings") as mock_settings,
        ):
            mock_client.client = mock_redis
            mock_settings.DISCORD_CLIENT_ID = "test-client-id"
            mock_settings.DISCORD_OAUTH_REDIRECT_URI = "https://example.com/auth/callback"

            from src.auth.oauth_state import create_oauth_state_with_url

            _, url = await create_oauth_state_with_url()

            expected_redirect = quote("https://example.com/auth/callback", safe="")
            assert f"redirect_uri={expected_redirect}" in url
