"""Unit tests for FlashpointDetectionService."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import dspy
import pytest

from src.bulk_content_scan.flashpoint_service import FlashpointDetectionService
from src.bulk_content_scan.schemas import BulkScanMessage, ConversationFlashpointMatch


def make_bulk_scan_message(
    message_id: str = "msg_1",
    content: str = "test message",
    author_id: str = "user_1",
    author_username: str = "testuser",
) -> BulkScanMessage:
    """Create a BulkScanMessage for testing."""
    return BulkScanMessage(
        message_id=message_id,
        channel_id="ch_1",
        community_server_id="server_1",
        content=content,
        author_id=author_id,
        author_username=author_username,
        timestamp=datetime.now(UTC),
    )


class TestFlashpointDetectionService:
    """Tests for FlashpointDetectionService.detect_flashpoint method."""

    @pytest.mark.asyncio
    async def test_detect_flashpoint_returns_match_when_derailing(self):
        """Returns ConversationFlashpointMatch when detector predicts derailing."""
        service = FlashpointDetectionService(model="openai/gpt-4o-mini")

        mock_prediction = MagicMock(spec=dspy.Prediction)
        mock_prediction.will_derail = True
        mock_prediction.reasoning = "Escalating hostility detected"

        mock_detector = MagicMock()
        mock_detector.return_value = mock_prediction

        with (
            patch.object(service, "_get_detector", return_value=mock_detector),
        ):
            message = make_bulk_scan_message(content="You're completely wrong!")
            context = [
                make_bulk_scan_message(
                    message_id="ctx_1", content="I think X is true", author_id="user_2"
                ),
                make_bulk_scan_message(
                    message_id="ctx_2", content="No, it's Y", author_id="user_1"
                ),
            ]

            result = await service.detect_flashpoint(message, context)

        assert result is not None
        assert isinstance(result, ConversationFlashpointMatch)
        assert result.will_derail is True
        assert result.reasoning == "Escalating hostility detected"
        assert result.context_messages == 2
        assert result.scan_type == "conversation_flashpoint"

    @pytest.mark.asyncio
    async def test_detect_flashpoint_returns_none_when_not_derailing(self):
        """Returns None when detector predicts conversation will not derail."""
        service = FlashpointDetectionService(model="openai/gpt-4o-mini")

        mock_prediction = MagicMock(spec=dspy.Prediction)
        mock_prediction.will_derail = False
        mock_prediction.reasoning = "Normal conversation"

        mock_detector = MagicMock()
        mock_detector.return_value = mock_prediction

        with (
            patch.object(service, "_get_detector", return_value=mock_detector),
        ):
            message = make_bulk_scan_message(content="Thanks for the info!")
            context = [
                make_bulk_scan_message(
                    message_id="ctx_1",
                    content="Here's the documentation",
                    author_id="user_2",
                ),
            ]

            result = await service.detect_flashpoint(message, context)

        assert result is None

    @pytest.mark.asyncio
    async def test_handles_string_bool_response_true(self):
        """String 'True' from LLM is correctly converted to boolean True."""
        service = FlashpointDetectionService(model="openai/gpt-4o-mini")

        mock_prediction = MagicMock(spec=dspy.Prediction)
        mock_prediction.will_derail = "True"
        mock_prediction.reasoning = "String response detected"

        mock_detector = MagicMock()
        mock_detector.return_value = mock_prediction

        with (
            patch.object(service, "_get_detector", return_value=mock_detector),
        ):
            message = make_bulk_scan_message()

            result = await service.detect_flashpoint(message, [])

        assert result is not None
        assert result.will_derail is True

    @pytest.mark.asyncio
    async def test_handles_string_bool_response_false(self):
        """String 'False' from LLM is correctly converted to boolean False."""
        service = FlashpointDetectionService(model="openai/gpt-4o-mini")

        mock_prediction = MagicMock(spec=dspy.Prediction)
        mock_prediction.will_derail = "False"
        mock_prediction.reasoning = "Normal conversation"

        mock_detector = MagicMock()
        mock_detector.return_value = mock_prediction

        with (
            patch.object(service, "_get_detector", return_value=mock_detector),
        ):
            message = make_bulk_scan_message()

            result = await service.detect_flashpoint(message, [])

        assert result is None

    @pytest.mark.asyncio
    async def test_handles_string_bool_response_yes(self):
        """String 'yes' from LLM is correctly converted to boolean True."""
        service = FlashpointDetectionService(model="openai/gpt-4o-mini")

        mock_prediction = MagicMock(spec=dspy.Prediction)
        mock_prediction.will_derail = "yes"
        mock_prediction.reasoning = "Affirmative string response"

        mock_detector = MagicMock()
        mock_detector.return_value = mock_prediction

        with (
            patch.object(service, "_get_detector", return_value=mock_detector),
        ):
            message = make_bulk_scan_message()

            result = await service.detect_flashpoint(message, [])

        assert result is not None
        assert result.will_derail is True

    @pytest.mark.asyncio
    async def test_handles_string_bool_response_one(self):
        """String '1' from LLM is correctly converted to boolean True."""
        service = FlashpointDetectionService(model="openai/gpt-4o-mini")

        mock_prediction = MagicMock(spec=dspy.Prediction)
        mock_prediction.will_derail = "1"
        mock_prediction.reasoning = "Numeric string response"

        mock_detector = MagicMock()
        mock_detector.return_value = mock_prediction

        with (
            patch.object(service, "_get_detector", return_value=mock_detector),
        ):
            message = make_bulk_scan_message()

            result = await service.detect_flashpoint(message, [])

        assert result is not None
        assert result.will_derail is True

    @pytest.mark.asyncio
    async def test_context_limited_to_max_context(self):
        """Only most recent max_context messages are used."""
        service = FlashpointDetectionService(model="openai/gpt-4o-mini")

        mock_prediction = MagicMock(spec=dspy.Prediction)
        mock_prediction.will_derail = True
        mock_prediction.reasoning = "Limited context"

        mock_detector = MagicMock()
        mock_detector.return_value = mock_prediction

        with (
            patch.object(service, "_get_detector", return_value=mock_detector),
        ):
            message = make_bulk_scan_message()
            context = [
                make_bulk_scan_message(message_id=f"ctx_{i}", content=f"Message {i}")
                for i in range(10)
            ]

            result = await service.detect_flashpoint(message, context, max_context=3)

        assert result is not None
        assert result.context_messages == 3

    @pytest.mark.asyncio
    async def test_returns_none_on_exception(self):
        """Returns None when detector raises an exception."""
        service = FlashpointDetectionService(model="openai/gpt-4o-mini")

        mock_detector = MagicMock()
        mock_detector.side_effect = RuntimeError("LLM API error")

        with (
            patch.object(service, "_get_detector", return_value=mock_detector),
            patch("src.bulk_content_scan.flashpoint_service.logger") as mock_logger,
        ):
            message = make_bulk_scan_message()

            result = await service.detect_flashpoint(message, [])

        assert result is None
        mock_logger.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_uses_author_username_in_context(self):
        """Context string uses author_username when available."""
        service = FlashpointDetectionService(model="openai/gpt-4o-mini")

        captured_context = None

        def capture_detector(*args, **kwargs):
            nonlocal captured_context
            captured_context = kwargs.get("context", "")
            mock_result = MagicMock()
            mock_result.will_derail = False
            mock_result.reasoning = "N/A"
            return mock_result

        mock_detector = MagicMock()
        mock_detector.side_effect = capture_detector

        with (
            patch.object(service, "_get_detector", return_value=mock_detector),
        ):
            message = make_bulk_scan_message(author_username="main_user")
            context = [
                make_bulk_scan_message(
                    message_id="ctx_1",
                    content="Hello there",
                    author_username="context_user",
                ),
            ]

            await service.detect_flashpoint(message, context)

        assert "context_user: Hello there" in captured_context

    @pytest.mark.asyncio
    async def test_falls_back_to_author_id(self):
        """Context string uses author_id when author_username is None."""
        service = FlashpointDetectionService(model="openai/gpt-4o-mini")

        captured_context = None

        def capture_detector(*args, **kwargs):
            nonlocal captured_context
            captured_context = kwargs.get("context", "")
            mock_result = MagicMock()
            mock_result.will_derail = False
            mock_result.reasoning = "N/A"
            return mock_result

        mock_detector = MagicMock()
        mock_detector.side_effect = capture_detector

        with (
            patch.object(service, "_get_detector", return_value=mock_detector),
        ):
            message = make_bulk_scan_message(author_username=None, author_id="user_123")
            context = [
                BulkScanMessage(
                    message_id="ctx_1",
                    channel_id="ch_1",
                    community_server_id="server_1",
                    content="Hello there",
                    author_id="user_456",
                    author_username=None,
                    timestamp=datetime.now(UTC),
                ),
            ]

            await service.detect_flashpoint(message, context)

        assert "user_456: Hello there" in captured_context

    @pytest.mark.asyncio
    async def test_empty_context_allowed(self):
        """Detection works with empty context list."""
        service = FlashpointDetectionService(model="openai/gpt-4o-mini")

        mock_prediction = MagicMock(spec=dspy.Prediction)
        mock_prediction.will_derail = True
        mock_prediction.reasoning = "Isolated hostile message"

        mock_detector = MagicMock()
        mock_detector.return_value = mock_prediction

        with (
            patch.object(service, "_get_detector", return_value=mock_detector),
        ):
            message = make_bulk_scan_message()

            result = await service.detect_flashpoint(message, [])

        assert result is not None
        assert result.context_messages == 0


class TestFlashpointDetectionServiceInit:
    """Tests for FlashpointDetectionService initialization."""

    def test_default_model(self):
        """Default model should be gpt-4o-mini."""
        service = FlashpointDetectionService()
        assert service.model == "openai/gpt-4o-mini"

    def test_custom_model(self):
        """Custom model can be specified."""
        service = FlashpointDetectionService(model="anthropic/claude-3-haiku")
        assert service.model == "anthropic/claude-3-haiku"
