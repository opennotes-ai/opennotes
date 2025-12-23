"""
Integration tests for vibecheck debug mode configuration.

Tests database persistence and API interactions for vibecheck_debug_mode.
"""

import pytest

from src.llm_config.models import CommunityServer


class TestVibecheckDebugModePersistence:
    """Integration tests for vibecheck_debug_mode database persistence."""

    @pytest.mark.asyncio
    async def test_vibecheck_debug_mode_persists_true(self, db):
        """vibecheck_debug_mode=True should be persisted to the database."""
        server = CommunityServer(
            platform="discord",
            platform_id="test_debug_mode_true",
            name="Test Server Debug Mode True",
            vibecheck_debug_mode=True,
        )
        db.add(server)
        await db.commit()
        await db.refresh(server)

        assert server.vibecheck_debug_mode is True

    @pytest.mark.asyncio
    async def test_vibecheck_debug_mode_default_persists_false(self, db):
        """Default vibecheck_debug_mode=False should persist correctly."""
        server = CommunityServer(
            platform="discord",
            platform_id="test_debug_mode_false",
            name="Test Server Debug Mode Default",
        )
        db.add(server)
        await db.commit()
        await db.refresh(server)

        assert server.vibecheck_debug_mode is False

    @pytest.mark.asyncio
    async def test_vibecheck_debug_mode_can_be_toggled(self, db):
        """vibecheck_debug_mode can be toggled without restart."""
        server = CommunityServer(
            platform="discord",
            platform_id="test_debug_mode_toggle",
            name="Test Server Toggle",
            vibecheck_debug_mode=False,
        )
        db.add(server)
        await db.commit()

        server.vibecheck_debug_mode = True
        await db.commit()
        await db.refresh(server)

        assert server.vibecheck_debug_mode is True

        server.vibecheck_debug_mode = False
        await db.commit()
        await db.refresh(server)

        assert server.vibecheck_debug_mode is False
