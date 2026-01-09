"""
Integration tests for vibecheck debug mode configuration.

Tests that vibecheck_debug_mode setting stored in community_config table
(set via Discord bot's /config opennotes set) properly affects bulk scan
behavior via the get_vibecheck_debug_mode() function.
"""

from uuid import uuid4

import pytest

from src.bulk_content_scan.nats_handler import get_vibecheck_debug_mode
from src.community_config.models import CommunityConfig
from src.llm_config.models import CommunityServer
from src.users.models import User


class TestVibecheckDebugModeFromCommunityConfig:
    """Integration tests for vibecheck_debug_mode read from community_config."""

    @pytest.fixture
    async def test_user(self, db):
        """Create a test user for the updated_by field."""
        user = User(
            id=uuid4(),
            username="vibecheck_test_user",
            email="vibecheck_test@test.local",
            hashed_password="hashed_password_placeholder",
            role="user",
            is_active=True,
            is_superuser=False,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user

    @pytest.fixture
    async def community_server(self, db):
        """Create a community server for testing."""
        server = CommunityServer(
            id=uuid4(),
            platform="discord",
            platform_community_server_id="test_vibecheck_config_community",
            name="Vibecheck Config Test Community",
            is_active=True,
            is_public=True,
        )
        db.add(server)
        await db.commit()
        await db.refresh(server)
        return server

    @pytest.mark.asyncio
    async def test_get_vibecheck_debug_mode_returns_true_when_config_set(
        self, db, community_server, test_user
    ):
        """get_vibecheck_debug_mode returns True when config is set to 'true'."""
        config = CommunityConfig(
            community_server_id=community_server.id,
            config_key="vibecheck_debug_mode",
            config_value="true",
            updated_by=test_user.id,
        )
        db.add(config)
        await db.commit()

        result = await get_vibecheck_debug_mode(db, community_server.id)

        assert result is True

    @pytest.mark.asyncio
    async def test_get_vibecheck_debug_mode_returns_false_when_config_false(
        self, db, community_server, test_user
    ):
        """get_vibecheck_debug_mode returns False when config is set to 'false'."""
        config = CommunityConfig(
            community_server_id=community_server.id,
            config_key="vibecheck_debug_mode",
            config_value="false",
            updated_by=test_user.id,
        )
        db.add(config)
        await db.commit()

        result = await get_vibecheck_debug_mode(db, community_server.id)

        assert result is False

    @pytest.mark.asyncio
    async def test_get_vibecheck_debug_mode_returns_false_when_no_config(
        self, db, community_server
    ):
        """get_vibecheck_debug_mode returns False when no config exists."""
        result = await get_vibecheck_debug_mode(db, community_server.id)

        assert result is False

    @pytest.mark.asyncio
    async def test_get_vibecheck_debug_mode_accepts_1_as_true(
        self, db, community_server, test_user
    ):
        """get_vibecheck_debug_mode accepts '1' as truthy value."""
        config = CommunityConfig(
            community_server_id=community_server.id,
            config_key="vibecheck_debug_mode",
            config_value="1",
            updated_by=test_user.id,
        )
        db.add(config)
        await db.commit()

        result = await get_vibecheck_debug_mode(db, community_server.id)

        assert result is True

    @pytest.mark.asyncio
    async def test_get_vibecheck_debug_mode_accepts_yes_as_true(
        self, db, community_server, test_user
    ):
        """get_vibecheck_debug_mode accepts 'yes' as truthy value."""
        config = CommunityConfig(
            community_server_id=community_server.id,
            config_key="vibecheck_debug_mode",
            config_value="yes",
            updated_by=test_user.id,
        )
        db.add(config)
        await db.commit()

        result = await get_vibecheck_debug_mode(db, community_server.id)

        assert result is True

    @pytest.mark.asyncio
    async def test_vibecheck_debug_mode_can_be_toggled(self, db, community_server, test_user):
        """vibecheck_debug_mode can be toggled via community_config updates."""
        config = CommunityConfig(
            community_server_id=community_server.id,
            config_key="vibecheck_debug_mode",
            config_value="false",
            updated_by=test_user.id,
        )
        db.add(config)
        await db.commit()

        result = await get_vibecheck_debug_mode(db, community_server.id)
        assert result is False

        config.config_value = "true"
        await db.commit()

        result = await get_vibecheck_debug_mode(db, community_server.id)
        assert result is True

        config.config_value = "false"
        await db.commit()

        result = await get_vibecheck_debug_mode(db, community_server.id)
        assert result is False
