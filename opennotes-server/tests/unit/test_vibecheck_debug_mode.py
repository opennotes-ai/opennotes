"""
Tests for vibecheck debug mode configuration.

Tests that CommunityServer has a vibecheck_debug_mode field that can be
toggled to enable verbose progress reporting during vibecheck operations.
"""

from src.llm_config.models import CommunityServer


class TestCommunityServerVibecheckDebugMode:
    """Unit tests for vibecheck_debug_mode field on CommunityServer model."""

    def test_community_server_has_vibecheck_debug_mode_attribute(self):
        """CommunityServer should have vibecheck_debug_mode attribute."""
        server = CommunityServer(
            platform="discord",
            platform_id="123456789",
            name="Test Server",
        )
        assert hasattr(server, "vibecheck_debug_mode")

    def test_vibecheck_debug_mode_defaults_to_falsy(self):
        """vibecheck_debug_mode should default to a falsy value before persistence."""
        server = CommunityServer(
            platform="discord",
            platform_id="123456789",
            name="Test Server",
        )
        assert not server.vibecheck_debug_mode

    def test_vibecheck_debug_mode_can_be_set_to_true(self):
        """vibecheck_debug_mode can be explicitly set to True."""
        server = CommunityServer(
            platform="discord",
            platform_id="123456789",
            name="Test Server",
            vibecheck_debug_mode=True,
        )
        assert server.vibecheck_debug_mode is True
