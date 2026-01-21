"""
Unit tests for community server platform ID validation in get_community_server_by_platform_id.

Task-1028: Validates that existing CommunityServer UUIDs are rejected when passed as
platform IDs. This prevents circular reference bugs where the internal UUID is
accidentally used instead of the platform-specific ID (e.g., Discord guild snowflake).
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from fastapi import HTTPException


@pytest.mark.unit
@pytest.mark.asyncio
class TestCircularReferenceValidation:
    """Unit tests for circular reference prevention in platform ID validation."""

    async def test_existing_community_uuid_rejected(self):
        """UUID matching existing CommunityServer PK should be rejected."""
        from src.auth.community_dependencies import get_community_server_by_platform_id

        mock_db = AsyncMock()
        existing_uuid = "1ca684bc-1d2b-4266-b7a5-d1296ee71c65"

        mock_circular_check_result = MagicMock()
        mock_circular_check_result.scalar_one_or_none.return_value = UUID(existing_uuid)
        mock_db.execute.return_value = mock_circular_check_result

        with pytest.raises(HTTPException) as exc_info:
            await get_community_server_by_platform_id(
                db=mock_db,
                community_server_id=existing_uuid,
                platform="discord",
                auto_create=True,
            )

        assert exc_info.value.status_code == 400
        assert "matches an existing community server's internal UUID" in exc_info.value.detail
        assert existing_uuid in exc_info.value.detail

    async def test_existing_uuid_rejected_regardless_of_auto_create(self):
        """Existing UUID should be rejected even with auto_create=False."""
        from src.auth.community_dependencies import get_community_server_by_platform_id

        mock_db = AsyncMock()
        existing_uuid = "9194ebfb-b07c-4c1b-9b35-85c624f1625c"

        mock_circular_check_result = MagicMock()
        mock_circular_check_result.scalar_one_or_none.return_value = UUID(existing_uuid)
        mock_db.execute.return_value = mock_circular_check_result

        with pytest.raises(HTTPException) as exc_info:
            await get_community_server_by_platform_id(
                db=mock_db,
                community_server_id=existing_uuid,
                platform="discord",
                auto_create=False,
            )

        assert exc_info.value.status_code == 400
        assert "matches an existing community server's internal UUID" in exc_info.value.detail

    async def test_uppercase_existing_uuid_also_rejected(self):
        """Uppercase UUID matching existing CommunityServer PK should also be rejected."""
        from src.auth.community_dependencies import get_community_server_by_platform_id

        mock_db = AsyncMock()
        existing_uuid = "1CA684BC-1D2B-4266-B7A5-D1296EE71C65"

        mock_circular_check_result = MagicMock()
        mock_circular_check_result.scalar_one_or_none.return_value = UUID(existing_uuid)
        mock_db.execute.return_value = mock_circular_check_result

        with pytest.raises(HTTPException) as exc_info:
            await get_community_server_by_platform_id(
                db=mock_db,
                community_server_id=existing_uuid,
                platform="discord",
                auto_create=True,
            )

        assert exc_info.value.status_code == 400
        assert "matches an existing community server's internal UUID" in exc_info.value.detail

    async def test_non_existing_uuid_allowed(self):
        """UUID that doesn't match any existing CommunityServer PK should be allowed."""
        from src.auth.community_dependencies import get_community_server_by_platform_id

        mock_db = AsyncMock()
        non_existing_uuid = "1ca684bc-1d2b-4266-b7a5-d1296ee71c65"

        mock_circular_check_result = MagicMock()
        mock_circular_check_result.scalar_one_or_none.return_value = None
        mock_platform_lookup_result = MagicMock()
        mock_platform_lookup_result.scalar_one_or_none.return_value = None
        mock_db.execute.side_effect = [mock_circular_check_result, mock_platform_lookup_result]

        result = await get_community_server_by_platform_id(
            db=mock_db,
            community_server_id=non_existing_uuid,
            platform="slack",
            auto_create=False,
        )

        assert result is None
        assert mock_db.execute.call_count == 2

    async def test_discord_snowflake_accepted(self):
        """Valid Discord snowflake should be accepted (not a valid UUID)."""
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

    async def test_existing_uuid_rejected_for_any_platform(self):
        """Existing UUID should be rejected regardless of platform (not just discord)."""
        from src.auth.community_dependencies import get_community_server_by_platform_id

        mock_db = AsyncMock()
        existing_uuid = "1ca684bc-1d2b-4266-b7a5-d1296ee71c65"

        mock_circular_check_result = MagicMock()
        mock_circular_check_result.scalar_one_or_none.return_value = UUID(existing_uuid)
        mock_db.execute.return_value = mock_circular_check_result

        with pytest.raises(HTTPException) as exc_info:
            await get_community_server_by_platform_id(
                db=mock_db,
                community_server_id=existing_uuid,
                platform="slack",
                auto_create=True,
            )

        assert exc_info.value.status_code == 400
        assert "matches an existing community server's internal UUID" in exc_info.value.detail


@pytest.mark.unit
class TestIsUuidFormat:
    """Unit tests for _is_uuid_format helper function (kept for migration use)."""

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
