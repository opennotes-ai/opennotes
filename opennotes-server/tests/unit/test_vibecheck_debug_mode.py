"""
Tests for vibecheck debug mode configuration lookup.

Tests that get_vibecheck_debug_mode reads from the community_config table
which is the source of truth for this setting (set via Discord bot's
/config opennotes set command).
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest


class TestGetVibecheckDebugMode:
    """Unit tests for get_vibecheck_debug_mode function."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_returns_true_when_config_is_true(self, mock_session):
        """get_vibecheck_debug_mode returns True when config value is 'true'."""
        from src.bulk_content_scan.nats_handler import get_vibecheck_debug_mode

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = "true"
        mock_session.execute.return_value = mock_result

        result = await get_vibecheck_debug_mode(mock_session, uuid4())

        assert result is True

    @pytest.mark.asyncio
    async def test_returns_true_when_config_is_1(self, mock_session):
        """get_vibecheck_debug_mode returns True when config value is '1'."""
        from src.bulk_content_scan.nats_handler import get_vibecheck_debug_mode

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = "1"
        mock_session.execute.return_value = mock_result

        result = await get_vibecheck_debug_mode(mock_session, uuid4())

        assert result is True

    @pytest.mark.asyncio
    async def test_returns_true_when_config_is_yes(self, mock_session):
        """get_vibecheck_debug_mode returns True when config value is 'yes'."""
        from src.bulk_content_scan.nats_handler import get_vibecheck_debug_mode

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = "yes"
        mock_session.execute.return_value = mock_result

        result = await get_vibecheck_debug_mode(mock_session, uuid4())

        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_config_is_false(self, mock_session):
        """get_vibecheck_debug_mode returns False when config value is 'false'."""
        from src.bulk_content_scan.nats_handler import get_vibecheck_debug_mode

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = "false"
        mock_session.execute.return_value = mock_result

        result = await get_vibecheck_debug_mode(mock_session, uuid4())

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_when_config_is_0(self, mock_session):
        """get_vibecheck_debug_mode returns False when config value is '0'."""
        from src.bulk_content_scan.nats_handler import get_vibecheck_debug_mode

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = "0"
        mock_session.execute.return_value = mock_result

        result = await get_vibecheck_debug_mode(mock_session, uuid4())

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_when_config_not_set(self, mock_session):
        """get_vibecheck_debug_mode returns False when no config exists."""
        from src.bulk_content_scan.nats_handler import get_vibecheck_debug_mode

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await get_vibecheck_debug_mode(mock_session, uuid4())

        assert result is False

    @pytest.mark.asyncio
    async def test_case_insensitive_true(self, mock_session):
        """get_vibecheck_debug_mode handles case-insensitive 'TRUE'."""
        from src.bulk_content_scan.nats_handler import get_vibecheck_debug_mode

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = "TRUE"
        mock_session.execute.return_value = mock_result

        result = await get_vibecheck_debug_mode(mock_session, uuid4())

        assert result is True
