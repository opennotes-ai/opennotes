"""Unit tests for the flashpoint detection capability."""

from unittest.mock import AsyncMock

import pendulum
import pytest

from src.bulk_content_scan.schemas import ContentItem, ConversationFlashpointMatch


def make_content_item(
    content_id: str = "msg_1",
    content_text: str = "you are completely wrong",
    author_id: str = "user_1",
    author_username: str | None = "testuser",
    channel_id: str = "ch_1",
    community_server_id: str = "server_1",
) -> ContentItem:
    return ContentItem(
        content_id=content_id,
        platform="discord",
        content_text=content_text,
        author_id=author_id,
        author_username=author_username,
        timestamp=pendulum.now("UTC"),
        channel_id=channel_id,
        community_server_id=community_server_id,
    )


def make_flashpoint_match(
    derailment_score: int = 75,
    risk_level: str = "Hostile",
    reasoning: str = "Escalating hostility",
    context_messages: int = 2,
) -> ConversationFlashpointMatch:
    return ConversationFlashpointMatch(
        derailment_score=derailment_score,
        risk_level=risk_level,
        reasoning=reasoning,
        context_messages=context_messages,
    )


class TestDetectFlashpoint:
    """Tests for the detect_flashpoint capability function."""

    def test_function_importable(self):
        """detect_flashpoint should be importable from capabilities.flashpoint."""
        from src.bulk_content_scan.capabilities.flashpoint import detect_flashpoint

        assert callable(detect_flashpoint)

    @pytest.mark.asyncio
    async def test_returns_none_when_service_not_configured(self):
        """Returns None when flashpoint_service is None."""
        from src.bulk_content_scan.capabilities.flashpoint import detect_flashpoint

        content_item = make_content_item()
        result = await detect_flashpoint(
            content_item=content_item,
            context_items=[],
            flashpoint_service=None,
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_match_when_flashpoint_detected(self):
        """Returns ConversationFlashpointMatch when flashpoint is detected."""
        from src.bulk_content_scan.capabilities.flashpoint import detect_flashpoint

        flashpoint_match = make_flashpoint_match(
            derailment_score=80,
            risk_level="Hostile",
            reasoning="Very heated exchange",
            context_messages=3,
        )

        mock_service = AsyncMock()
        mock_service.detect_flashpoint = AsyncMock(return_value=flashpoint_match)

        content_item = make_content_item()
        context_items = [
            make_content_item(content_id="ctx_1"),
            make_content_item(content_id="ctx_2"),
        ]

        result = await detect_flashpoint(
            content_item=content_item,
            context_items=context_items,
            flashpoint_service=mock_service,
        )

        assert result is not None
        assert isinstance(result, ConversationFlashpointMatch)
        assert result.derailment_score == 80
        assert result.risk_level == "Hostile"
        assert result.reasoning == "Very heated exchange"

    @pytest.mark.asyncio
    async def test_returns_none_when_no_flashpoint(self):
        """Returns None when flashpoint service returns None."""
        from src.bulk_content_scan.capabilities.flashpoint import detect_flashpoint

        mock_service = AsyncMock()
        mock_service.detect_flashpoint = AsyncMock(return_value=None)

        content_item = make_content_item()
        result = await detect_flashpoint(
            content_item=content_item,
            context_items=[],
            flashpoint_service=mock_service,
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_exception(self):
        """Returns None when flashpoint service raises an exception."""
        from src.bulk_content_scan.capabilities.flashpoint import detect_flashpoint

        mock_service = AsyncMock()
        mock_service.detect_flashpoint = AsyncMock(side_effect=Exception("DSPy error"))

        content_item = make_content_item()
        result = await detect_flashpoint(
            content_item=content_item,
            context_items=[],
            flashpoint_service=mock_service,
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_converts_content_items_to_bulk_scan_messages(self):
        """ContentItem inputs are converted to BulkScanMessage for flashpoint service."""
        from src.bulk_content_scan.capabilities.flashpoint import detect_flashpoint
        from src.bulk_content_scan.schemas import BulkScanMessage

        mock_service = AsyncMock()
        mock_service.detect_flashpoint = AsyncMock(return_value=None)

        content_item = make_content_item(
            content_text="main message",
            author_id="user_42",
            author_username="alice",
        )
        context_items = [
            make_content_item(
                content_id="ctx_1",
                content_text="context message 1",
                author_id="user_43",
            )
        ]

        await detect_flashpoint(
            content_item=content_item,
            context_items=context_items,
            flashpoint_service=mock_service,
        )

        mock_service.detect_flashpoint.assert_called_once()
        call_kwargs = mock_service.detect_flashpoint.call_args.kwargs
        msg = call_kwargs["message"]
        ctx = call_kwargs["context_messages"]

        assert isinstance(msg, BulkScanMessage)
        assert msg.content == "main message"
        assert msg.author_id == "user_42"

        assert len(ctx) == 1
        assert isinstance(ctx[0], BulkScanMessage)
        assert ctx[0].content == "context message 1"
