"""Unit tests for the OpenAI content moderation capability."""

from unittest.mock import AsyncMock

import pendulum
import pytest

from src.bulk_content_scan.openai_moderation_service import ModerationResult
from src.bulk_content_scan.schemas import ContentItem, OpenAIModerationMatch


def make_content_item(
    content_id: str = "msg_1",
    content_text: str = "test message",
    attachment_urls: list[str] | None = None,
) -> ContentItem:
    return ContentItem(
        content_id=content_id,
        platform="discord",
        content_text=content_text,
        author_id="user_1",
        author_username="testuser",
        timestamp=pendulum.now("UTC"),
        channel_id="ch_1",
        community_server_id="server_1",
        attachment_urls=attachment_urls,
    )


def make_moderation_result(
    flagged: bool = False,
    max_score: float = 0.0,
    categories: dict | None = None,
    scores: dict | None = None,
    flagged_categories: list[str] | None = None,
) -> ModerationResult:
    return ModerationResult(
        flagged=flagged,
        categories=categories or {"violence": False, "sexual": False},
        scores=scores or {"violence": 0.01, "sexual": 0.02},
        max_score=max_score,
        flagged_categories=flagged_categories or [],
    )


class TestCheckContentModeration:
    """Tests for the check_content_moderation capability function."""

    def test_function_importable(self):
        """check_content_moderation should be importable from capabilities.moderation."""
        from src.bulk_content_scan.capabilities.moderation import check_content_moderation

        assert callable(check_content_moderation)

    @pytest.mark.asyncio
    async def test_returns_none_when_service_not_configured(self):
        """Returns None when moderation_service is None."""
        from src.bulk_content_scan.capabilities.moderation import check_content_moderation

        content_item = make_content_item()
        result = await check_content_moderation(
            content_item=content_item,
            moderation_service=None,
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_not_flagged(self):
        """Returns None when moderation result is not flagged."""
        from src.bulk_content_scan.capabilities.moderation import check_content_moderation

        mock_service = AsyncMock()
        mock_service.moderate_text = AsyncMock(return_value=make_moderation_result(flagged=False))

        content_item = make_content_item(content_text="harmless message")
        result = await check_content_moderation(
            content_item=content_item,
            moderation_service=mock_service,
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_match_when_flagged(self):
        """Returns OpenAIModerationMatch when content is flagged."""
        from src.bulk_content_scan.capabilities.moderation import check_content_moderation

        flagged_result = make_moderation_result(
            flagged=True,
            max_score=0.95,
            categories={"violence": True, "sexual": False},
            scores={"violence": 0.95, "sexual": 0.02},
            flagged_categories=["violence"],
        )
        mock_service = AsyncMock()
        mock_service.moderate_text = AsyncMock(return_value=flagged_result)

        content_item = make_content_item(content_text="violent content")
        result = await check_content_moderation(
            content_item=content_item,
            moderation_service=mock_service,
        )

        assert result is not None
        assert isinstance(result, OpenAIModerationMatch)
        assert result.max_score == 0.95
        assert result.categories == {"violence": True, "sexual": False}
        assert result.scores == {"violence": 0.95, "sexual": 0.02}
        assert result.flagged_categories == ["violence"]

    @pytest.mark.asyncio
    async def test_uses_moderate_text_for_text_only(self):
        """Calls moderate_text when no attachment_urls."""
        from src.bulk_content_scan.capabilities.moderation import check_content_moderation

        mock_service = AsyncMock()
        mock_service.moderate_text = AsyncMock(return_value=make_moderation_result(flagged=False))

        content_item = make_content_item(content_text="hello world", attachment_urls=None)
        await check_content_moderation(
            content_item=content_item,
            moderation_service=mock_service,
        )

        mock_service.moderate_text.assert_called_once_with("hello world")
        mock_service.moderate_multimodal.assert_not_called()

    @pytest.mark.asyncio
    async def test_uses_moderate_multimodal_for_attachments(self):
        """Calls moderate_multimodal when attachment_urls are present."""
        from src.bulk_content_scan.capabilities.moderation import check_content_moderation

        mock_service = AsyncMock()
        mock_service.moderate_multimodal = AsyncMock(
            return_value=make_moderation_result(flagged=False)
        )

        content_item = make_content_item(
            content_text="check this image",
            attachment_urls=["https://example.com/img.jpg"],
        )
        await check_content_moderation(
            content_item=content_item,
            moderation_service=mock_service,
        )

        mock_service.moderate_multimodal.assert_called_once_with(
            text="check this image",
            image_urls=["https://example.com/img.jpg"],
        )
        mock_service.moderate_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_none_on_exception(self):
        """Returns None when moderation service raises an exception."""
        from src.bulk_content_scan.capabilities.moderation import check_content_moderation

        mock_service = AsyncMock()
        mock_service.moderate_text = AsyncMock(side_effect=Exception("API error"))

        content_item = make_content_item()
        result = await check_content_moderation(
            content_item=content_item,
            moderation_service=mock_service,
        )

        assert result is None
