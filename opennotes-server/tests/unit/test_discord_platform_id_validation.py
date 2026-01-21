"""
Unit tests for Discord platform ID validation in get_community_server_by_platform_id.

Task-1028: Validates that UUIDs are rejected for Discord platform since Discord IDs
are numeric snowflakes, not UUIDs. This prevents duplicate community server rows
caused by accidentally passing a UUID instead of the Discord guild ID.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException


@pytest.mark.unit
@pytest.mark.asyncio
class TestDiscordPlatformIdValidation:
    """Unit tests for Discord platform ID validation."""

    async def test_uuid_rejected_for_discord_platform(self):
        """UUID format should be rejected for Discord platform."""
        from src.auth.community_dependencies import get_community_server_by_platform_id

        mock_db = AsyncMock()
        uuid_value = "1ca684bc-1d2b-4266-b7a5-d1296ee71c65"

        with pytest.raises(HTTPException) as exc_info:
            await get_community_server_by_platform_id(
                db=mock_db,
                community_server_id=uuid_value,
                platform="discord",
                auto_create=True,
            )

        assert exc_info.value.status_code == 400
        assert "Invalid Discord community server ID" in exc_info.value.detail
        assert "numeric snowflakes" in exc_info.value.detail
        mock_db.execute.assert_not_called()

    async def test_uuid_rejected_regardless_of_auto_create(self):
        """UUID should be rejected even with auto_create=False."""
        from src.auth.community_dependencies import get_community_server_by_platform_id

        mock_db = AsyncMock()
        uuid_value = "9194ebfb-b07c-4c1b-9b35-85c624f1625c"

        with pytest.raises(HTTPException) as exc_info:
            await get_community_server_by_platform_id(
                db=mock_db,
                community_server_id=uuid_value,
                platform="discord",
                auto_create=False,
            )

        assert exc_info.value.status_code == 400
        mock_db.execute.assert_not_called()

    async def test_uppercase_uuid_also_rejected(self):
        """Uppercase UUID should also be rejected."""
        from src.auth.community_dependencies import get_community_server_by_platform_id

        mock_db = AsyncMock()
        uuid_value = "1CA684BC-1D2B-4266-B7A5-D1296EE71C65"

        with pytest.raises(HTTPException) as exc_info:
            await get_community_server_by_platform_id(
                db=mock_db,
                community_server_id=uuid_value,
                platform="discord",
                auto_create=True,
            )

        assert exc_info.value.status_code == 400

    async def test_discord_snowflake_accepted(self):
        """Valid Discord snowflake should be accepted."""
        from src.auth.community_dependencies import get_community_server_by_platform_id

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await get_community_server_by_platform_id(
            db=mock_db,
            community_server_id="738146839441965267",
            platform="discord",
            auto_create=False,
        )

        assert result is None
        mock_db.execute.assert_called_once()

    async def test_uuid_allowed_for_non_discord_platform(self):
        """UUID should be allowed for non-Discord platforms (future compatibility)."""
        from src.auth.community_dependencies import get_community_server_by_platform_id

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        uuid_value = "1ca684bc-1d2b-4266-b7a5-d1296ee71c65"

        result = await get_community_server_by_platform_id(
            db=mock_db,
            community_server_id=uuid_value,
            platform="slack",
            auto_create=False,
        )

        assert result is None
        mock_db.execute.assert_called_once()

    async def test_discord_snowflake_auto_create_enabled(self):
        """Valid Discord snowflake with auto_create=True should create new server."""
        from src.auth.community_dependencies import get_community_server_by_platform_id

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        snowflake_id = "738146839441965267"

        result = await get_community_server_by_platform_id(
            db=mock_db,
            community_server_id=snowflake_id,
            platform="discord",
            auto_create=True,
        )

        mock_db.execute.assert_called_once()
        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()
        mock_db.refresh.assert_called_once()
        assert result is not None


@pytest.mark.unit
class TestIsUuidFormat:
    """Unit tests for _is_uuid_format helper function."""

    def test_valid_uuid_lowercase(self):
        """Valid lowercase UUID should be detected."""
        from src.auth.community_dependencies import _is_uuid_format

        assert _is_uuid_format("1ca684bc-1d2b-4266-b7a5-d1296ee71c65") is True

    def test_valid_uuid_uppercase(self):
        """Valid uppercase UUID should be detected."""
        from src.auth.community_dependencies import _is_uuid_format

        assert _is_uuid_format("1CA684BC-1D2B-4266-B7A5-D1296EE71C65") is True

    def test_valid_uuid_mixed_case(self):
        """Valid mixed case UUID should be detected."""
        from src.auth.community_dependencies import _is_uuid_format

        assert _is_uuid_format("1Ca684bC-1D2b-4266-B7a5-d1296Ee71c65") is True

    def test_discord_snowflake_not_uuid(self):
        """Discord snowflake should not be detected as UUID."""
        from src.auth.community_dependencies import _is_uuid_format

        assert _is_uuid_format("738146839441965267") is False

    def test_empty_string_not_uuid(self):
        """Empty string should not be detected as UUID."""
        from src.auth.community_dependencies import _is_uuid_format

        assert _is_uuid_format("") is False

    def test_uuid_without_hyphens_not_detected(self):
        """UUID without hyphens should not be detected (strict format)."""
        from src.auth.community_dependencies import _is_uuid_format

        assert _is_uuid_format("1ca684bc1d2b4266b7a5d1296ee71c65") is False

    def test_partial_uuid_not_detected(self):
        """Partial UUID should not be detected."""
        from src.auth.community_dependencies import _is_uuid_format

        assert _is_uuid_format("1ca684bc-1d2b-4266") is False

    def test_uuid_with_whitespace_not_detected(self):
        """UUID with leading/trailing whitespace should not be detected."""
        from src.auth.community_dependencies import _is_uuid_format

        assert _is_uuid_format(" 1ca684bc-1d2b-4266-b7a5-d1296ee71c65 ") is False

    def test_uuid_with_prefix_not_detected(self):
        """UUID with prefix text should not be detected."""
        from src.auth.community_dependencies import _is_uuid_format

        assert _is_uuid_format("prefix-1ca684bc-1d2b-4266-b7a5-d1296ee71c65") is False

    def test_uuid_with_suffix_not_detected(self):
        """UUID with suffix text should not be detected."""
        from src.auth.community_dependencies import _is_uuid_format

        assert _is_uuid_format("1ca684bc-1d2b-4266-b7a5-d1296ee71c65-suffix") is False

    def test_uuid_with_invalid_hex_not_detected(self):
        """UUID with non-hex characters (gg) should not be detected."""
        from src.auth.community_dependencies import _is_uuid_format

        assert _is_uuid_format("1ca684bc-1d2b-42gg-b7a5-d1296ee71c65") is False

    def test_uuid_wrong_segment_length_not_detected(self):
        """UUID with wrong segment length should not be detected."""
        from src.auth.community_dependencies import _is_uuid_format

        assert _is_uuid_format("1ca684bc-1d2b-42666-b7a5-d1296ee71c65") is False

    def test_uuid_extra_segment_not_detected(self):
        """UUID with extra segment should not be detected."""
        from src.auth.community_dependencies import _is_uuid_format

        assert _is_uuid_format("1ca684bc-1d2b-4266-b7a5-d1296ee71c65-aaaa") is False
