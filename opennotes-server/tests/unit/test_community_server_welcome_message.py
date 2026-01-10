"""
Tests for CommunityServer welcome_message_id field.

TDD: RED phase - these tests should fail until the field is implemented.
"""

from uuid import uuid4

from src.llm_config.models import CommunityServer


class TestCommunityServerWelcomeMessageId:
    """Tests for welcome_message_id field on CommunityServer model."""

    def test_community_server_has_welcome_message_id_attribute(self):
        """CommunityServer should have welcome_message_id attribute."""
        server = CommunityServer(
            id=uuid4(),
            platform="discord",
            platform_community_server_id="123456789",
            name="Test Server",
        )
        assert hasattr(server, "welcome_message_id")

    def test_welcome_message_id_defaults_to_none(self):
        """welcome_message_id should default to None (nullable)."""
        server = CommunityServer(
            id=uuid4(),
            platform="discord",
            platform_community_server_id="123456789",
            name="Test Server",
        )
        assert server.welcome_message_id is None

    def test_welcome_message_id_can_be_set(self):
        """welcome_message_id can be set to a Discord message ID string."""
        message_id = "1234567890123456789"
        server = CommunityServer(
            id=uuid4(),
            platform="discord",
            platform_community_server_id="123456789",
            name="Test Server",
            welcome_message_id=message_id,
        )
        assert server.welcome_message_id == message_id

    def test_welcome_message_id_accepts_long_discord_ids(self):
        """welcome_message_id should accept Discord snowflake IDs (up to 20 digits)."""
        long_id = "12345678901234567890"
        server = CommunityServer(
            id=uuid4(),
            platform="discord",
            platform_community_server_id="123456789",
            name="Test Server",
            welcome_message_id=long_id,
        )
        assert server.welcome_message_id == long_id
