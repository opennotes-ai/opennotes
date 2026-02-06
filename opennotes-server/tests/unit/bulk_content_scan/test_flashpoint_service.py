"""Unit tests for FlashpointDetectionService."""

import warnings
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import dspy
import pytest

from src.bulk_content_scan.flashpoint_service import (
    _TRANSIENT_ERRORS,
    FlashpointDetectionService,
    get_flashpoint_service,
)
from src.bulk_content_scan.flashpoint_utils import FlashpointDetector
from src.bulk_content_scan.schemas import BulkScanMessage, ConversationFlashpointMatch


def make_bulk_scan_message(
    message_id: str = "msg_1",
    content: str = "test message",
    author_id: str = "user_1",
    author_username: str | None = "testuser",
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
    async def test_detect_flashpoint_returns_match_when_high_score(self):
        """Returns ConversationFlashpointMatch when derailment_score >= threshold."""
        service = FlashpointDetectionService(model="openai/gpt-5-mini")

        mock_prediction = MagicMock(spec=dspy.Prediction)
        mock_prediction.derailment_score = 75
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
        assert result.derailment_score == 75
        assert result.reasoning == "Escalating hostility detected"
        assert result.context_messages == 2
        assert result.scan_type == "conversation_flashpoint"

    @pytest.mark.asyncio
    async def test_detect_flashpoint_returns_none_when_low_score(self):
        """Returns None when derailment_score is below threshold."""
        service = FlashpointDetectionService(model="openai/gpt-5-mini")

        mock_prediction = MagicMock(spec=dspy.Prediction)
        mock_prediction.derailment_score = 10
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
    async def test_handles_string_score_response(self):
        """String '80' from LLM is correctly parsed to integer 80."""
        service = FlashpointDetectionService(model="openai/gpt-5-mini")

        mock_prediction = MagicMock(spec=dspy.Prediction)
        mock_prediction.derailment_score = "80"
        mock_prediction.reasoning = "String response detected"

        mock_detector = MagicMock()
        mock_detector.return_value = mock_prediction

        with (
            patch.object(service, "_get_detector", return_value=mock_detector),
        ):
            message = make_bulk_scan_message()

            result = await service.detect_flashpoint(message, [])

        assert result is not None
        assert result.derailment_score == 80

    @pytest.mark.asyncio
    async def test_handles_string_score_below_threshold(self):
        """String '20' from LLM is correctly parsed and returns None."""
        service = FlashpointDetectionService(model="openai/gpt-5-mini")

        mock_prediction = MagicMock(spec=dspy.Prediction)
        mock_prediction.derailment_score = "20"
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
    async def test_custom_score_threshold(self):
        """Custom score_threshold overrides the default."""
        service = FlashpointDetectionService(model="openai/gpt-5-mini")

        mock_prediction = MagicMock(spec=dspy.Prediction)
        mock_prediction.derailment_score = 30
        mock_prediction.reasoning = "Moderate tension"

        mock_detector = MagicMock()
        mock_detector.return_value = mock_prediction

        with (
            patch.object(service, "_get_detector", return_value=mock_detector),
        ):
            message = make_bulk_scan_message()

            result_default = await service.detect_flashpoint(message, [])
            assert result_default is None

            result_low = await service.detect_flashpoint(message, [], score_threshold=25)
            assert result_low is not None
            assert result_low.derailment_score == 30

    @pytest.mark.asyncio
    async def test_score_at_exact_threshold(self):
        """Score exactly at threshold is included."""
        service = FlashpointDetectionService(model="openai/gpt-5-mini")

        mock_prediction = MagicMock(spec=dspy.Prediction)
        mock_prediction.derailment_score = 50
        mock_prediction.reasoning = "At threshold"

        mock_detector = MagicMock()
        mock_detector.return_value = mock_prediction

        with (
            patch.object(service, "_get_detector", return_value=mock_detector),
        ):
            message = make_bulk_scan_message()

            result = await service.detect_flashpoint(message, [])

        assert result is not None
        assert result.derailment_score == 50

    @pytest.mark.asyncio
    async def test_context_limited_to_max_context(self):
        """Only most recent max_context messages are used."""
        service = FlashpointDetectionService(model="openai/gpt-5-mini")

        mock_prediction = MagicMock(spec=dspy.Prediction)
        mock_prediction.derailment_score = 75
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
    async def test_returns_none_on_transient_error(self):
        """Returns None when detector raises a transient error."""
        service = FlashpointDetectionService(model="openai/gpt-5-mini")

        mock_detector = MagicMock()
        mock_detector.side_effect = TimeoutError("Request timed out")

        with (
            patch.object(service, "_get_detector", return_value=mock_detector),
            patch("src.bulk_content_scan.flashpoint_service.logger") as mock_logger,
        ):
            message = make_bulk_scan_message()

            result = await service.detect_flashpoint(message, [])

        assert result is None
        mock_logger.warning.assert_called_once()

    @pytest.mark.asyncio
    async def test_raises_on_critical_error(self):
        """Re-raises critical (non-transient) errors after logging."""
        service = FlashpointDetectionService(model="openai/gpt-5-mini")

        mock_detector = MagicMock()
        mock_detector.side_effect = RuntimeError("LLM API auth failure")

        with (
            patch.object(service, "_get_detector", return_value=mock_detector),
            patch("src.bulk_content_scan.flashpoint_service.logger") as mock_logger,
        ):
            message = make_bulk_scan_message()

            with pytest.raises(RuntimeError, match="LLM API auth failure"):
                await service.detect_flashpoint(message, [])

        mock_logger.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_none_on_timeout_error(self):
        """Returns None when detector raises TimeoutError (transient)."""
        service = FlashpointDetectionService(model="openai/gpt-5-mini")

        mock_detector = MagicMock()
        mock_detector.side_effect = TimeoutError("Request timed out")

        with (
            patch.object(service, "_get_detector", return_value=mock_detector),
        ):
            message = make_bulk_scan_message()

            result = await service.detect_flashpoint(message, [])

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_connection_error(self):
        """Returns None when detector raises ConnectionError (transient)."""
        service = FlashpointDetectionService(model="openai/gpt-5-mini")

        mock_detector = MagicMock()
        mock_detector.side_effect = ConnectionError("Connection refused")

        with (
            patch.object(service, "_get_detector", return_value=mock_detector),
        ):
            message = make_bulk_scan_message()

            result = await service.detect_flashpoint(message, [])

        assert result is None

    @pytest.mark.asyncio
    async def test_uses_author_username_in_context(self):
        """Context string uses author_username when available."""
        service = FlashpointDetectionService(model="openai/gpt-5-mini")

        captured_context = None

        def capture_detector(*args, **kwargs):
            nonlocal captured_context
            captured_context = kwargs.get("context", "")
            mock_result = MagicMock()
            mock_result.derailment_score = 10
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
        service = FlashpointDetectionService(model="openai/gpt-5-mini")

        captured_context = None

        def capture_detector(*args, **kwargs):
            nonlocal captured_context
            captured_context = kwargs.get("context", "")
            mock_result = MagicMock()
            mock_result.derailment_score = 10
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
        service = FlashpointDetectionService(model="openai/gpt-5-mini")

        mock_prediction = MagicMock(spec=dspy.Prediction)
        mock_prediction.derailment_score = 85
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
        """Default model should be gpt-5-mini."""
        service = FlashpointDetectionService()
        assert service.model == "openai/gpt-5-mini"

    def test_custom_model(self):
        """Custom model can be specified."""
        service = FlashpointDetectionService(model="anthropic/claude-3-haiku")
        assert service.model == "anthropic/claude-3-haiku"

    def test_default_score_threshold(self):
        """Default score threshold is 50."""
        assert FlashpointDetectionService.DEFAULT_SCORE_THRESHOLD == 50


class TestGetDetectorLazyInit:
    """Tests for _get_detector lazy initialization paths.

    These tests exercise the real _get_detector method rather than
    mocking it away. Only dspy.LM (to prevent API calls) and
    FlashpointDetector.load (to prevent file I/O) are mocked.
    """

    @patch("dspy.LM")
    def test_creates_detector_when_none_cached(self, mock_lm_cls: MagicMock, tmp_path: Path):
        """_get_detector creates a FlashpointDetector when _detector is None."""
        service = FlashpointDetectionService(
            model="openai/gpt-5-mini",
            optimized_model_path=tmp_path / "nonexistent.json",
        )
        assert service._detector is None

        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}):
            detector = service._get_detector()

        assert detector is not None
        assert isinstance(detector, FlashpointDetector)
        assert service._detector is detector
        mock_lm_cls.assert_called_once_with("openai/gpt-5-mini")
        assert service._lm is mock_lm_cls.return_value

    @patch("dspy.LM")
    def test_reuses_cached_detector_on_subsequent_calls(
        self, mock_lm_cls: MagicMock, tmp_path: Path
    ):
        """_get_detector returns the same cached instance on repeated calls."""
        service = FlashpointDetectionService(
            model="openai/gpt-5-mini",
            optimized_model_path=tmp_path / "nonexistent.json",
        )

        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}):
            first = service._get_detector()
            second = service._get_detector()

        assert first is second
        mock_lm_cls.assert_called_once()

    @patch("dspy.LM")
    def test_loads_optimized_model_when_file_exists(self, mock_lm_cls: MagicMock, tmp_path: Path):
        """_get_detector calls .load() when the optimized model file exists."""
        optimized_path = tmp_path / "optimized_detector.json"
        optimized_path.write_text("{}")

        service = FlashpointDetectionService(
            model="openai/gpt-5-mini",
            optimized_model_path=optimized_path,
        )

        with (
            patch.object(FlashpointDetector, "load") as mock_load,
            patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}),
        ):
            detector = service._get_detector()

        assert isinstance(detector, FlashpointDetector)
        mock_load.assert_called_once_with(str(optimized_path))

    @patch("dspy.LM")
    def test_skips_load_when_optimized_model_missing(self, mock_lm_cls: MagicMock, tmp_path: Path):
        """_get_detector uses base detector when optimized file does not exist."""
        missing_path = tmp_path / "optimized_detector.json"
        assert not missing_path.exists()

        service = FlashpointDetectionService(
            model="openai/gpt-5-mini",
            optimized_model_path=missing_path,
        )

        with (
            patch.object(FlashpointDetector, "load") as mock_load,
            patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}),
        ):
            detector = service._get_detector()

        assert isinstance(detector, FlashpointDetector)
        mock_load.assert_not_called()

    @patch("dspy.LM")
    def test_uses_default_path_when_no_path_provided(self, mock_lm_cls: MagicMock):
        """_get_detector uses _get_default_optimized_path when no path given."""
        service = FlashpointDetectionService(model="openai/gpt-5-mini")
        assert service._optimized_path is None

        with (
            patch.object(FlashpointDetector, "load"),
            patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}),
        ):
            service._get_detector()

        default_path = service._get_default_optimized_path()
        assert default_path.name == "optimized_detector.json"
        assert default_path.parent.name == "flashpoints"
        assert default_path.parent.parent.name == "data"

    @patch("dspy.LM")
    def test_detector_has_predict_attribute(self, mock_lm_cls: MagicMock, tmp_path: Path):
        """The real FlashpointDetector created by _get_detector has a predict module."""
        service = FlashpointDetectionService(
            model="openai/gpt-5-mini",
            optimized_model_path=tmp_path / "nonexistent.json",
        )

        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}):
            detector = service._get_detector()

        assert hasattr(detector, "predict")
        assert isinstance(detector.predict, dspy.ChainOfThought)


class TestGetFlashpointServiceSingleton:
    """Tests for the get_flashpoint_service singleton factory."""

    def test_returns_same_instance(self):
        """Repeated calls return the same service instance."""
        import src.bulk_content_scan.flashpoint_service as mod

        mod._flashpoint_service = None
        try:
            svc1 = get_flashpoint_service()
            svc2 = get_flashpoint_service()
            assert svc1 is svc2
        finally:
            mod._flashpoint_service = None

    def test_accepts_model_on_first_call(self):
        """First call can configure the model."""
        import src.bulk_content_scan.flashpoint_service as mod

        mod._flashpoint_service = None
        try:
            svc = get_flashpoint_service(model="anthropic/claude-3-haiku")
            assert svc.model == "anthropic/claude-3-haiku"
        finally:
            mod._flashpoint_service = None

    def test_warns_when_model_differs_from_singleton(self):
        """Warning when singleton exists and different model requested."""
        import src.bulk_content_scan.flashpoint_service as mod

        mod._flashpoint_service = None
        try:
            get_flashpoint_service(model="openai/gpt-5-mini")

            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                svc = get_flashpoint_service(model="anthropic/claude-3-haiku")

            assert len(w) == 1
            assert "singleton already created" in str(w[0].message)
            assert "openai/gpt-5-mini" in str(w[0].message)
            assert "anthropic/claude-3-haiku" in str(w[0].message)
            assert svc.model == "openai/gpt-5-mini"
        finally:
            mod._flashpoint_service = None

    def test_warns_when_path_differs_from_singleton(self):
        """Warning when singleton exists and different path requested."""
        import src.bulk_content_scan.flashpoint_service as mod

        mod._flashpoint_service = None
        try:
            get_flashpoint_service(optimized_model_path=Path("/first/path.json"))

            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                svc = get_flashpoint_service(optimized_model_path=Path("/different/path.json"))

            assert len(w) == 1
            assert "singleton already created" in str(w[0].message)
            assert svc._optimized_path == Path("/first/path.json")
        finally:
            mod._flashpoint_service = None

    def test_no_warning_when_same_model_requested(self):
        """No warning when singleton exists and same model requested."""
        import src.bulk_content_scan.flashpoint_service as mod

        mod._flashpoint_service = None
        try:
            get_flashpoint_service(model="openai/gpt-5-mini")

            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                get_flashpoint_service(model="openai/gpt-5-mini")

            assert len(w) == 0
        finally:
            mod._flashpoint_service = None

    def test_no_warning_when_no_args_on_subsequent_call(self):
        """No warning when singleton exists and no args are passed."""
        import src.bulk_content_scan.flashpoint_service as mod

        mod._flashpoint_service = None
        try:
            get_flashpoint_service(model="openai/gpt-5-mini")

            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                get_flashpoint_service()

            assert len(w) == 0
        finally:
            mod._flashpoint_service = None


class TestFlashpointRealisticExamples:
    """Tests using realistic Discord conversation format."""

    @pytest.mark.asyncio
    async def test_escalating_argument_detected(self):
        """Realistic Discord argument that escalates into personal attacks."""
        service = FlashpointDetectionService(model="openai/gpt-5-mini")

        mock_prediction = MagicMock(spec=dspy.Prediction)
        mock_prediction.derailment_score = 82
        mock_prediction.reasoning = (
            "Conversation shifting from topic disagreement to "
            "personal attacks. User moved from 'I disagree' to "
            "'you never know what you are talking about'."
        )

        mock_detector = MagicMock()
        mock_detector.return_value = mock_prediction

        with patch.object(service, "_get_detector", return_value=mock_detector):
            context = [
                make_bulk_scan_message(
                    message_id="ctx_1",
                    content="I think React is better for this use case",
                    author_id="dev_alice",
                    author_username="alice",
                ),
                make_bulk_scan_message(
                    message_id="ctx_2",
                    content="Nah Vue is way simpler, you just don't get it",
                    author_id="dev_bob",
                    author_username="bob",
                ),
                make_bulk_scan_message(
                    message_id="ctx_3",
                    content="I 'don't get it'? I've used React for 5 years",
                    author_id="dev_alice",
                    author_username="alice",
                ),
            ]
            message = make_bulk_scan_message(
                message_id="msg_trigger",
                content=(
                    "Years of experience don't mean anything if you "
                    "never learn. You always push React on everyone."
                ),
                author_id="dev_bob",
                author_username="bob",
            )

            result = await service.detect_flashpoint(message, context)

        assert result is not None
        assert isinstance(result, ConversationFlashpointMatch)
        assert result.derailment_score == 82
        assert result.context_messages == 3
        assert "personal attacks" in result.reasoning

    @pytest.mark.asyncio
    async def test_healthy_debate_not_flagged(self):
        """Realistic Discord debate that stays respectful."""
        service = FlashpointDetectionService(model="openai/gpt-5-mini")

        mock_prediction = MagicMock(spec=dspy.Prediction)
        mock_prediction.derailment_score = 8
        mock_prediction.reasoning = "Constructive disagreement with mutual respect."

        mock_detector = MagicMock()
        mock_detector.return_value = mock_prediction

        with patch.object(service, "_get_detector", return_value=mock_detector):
            context = [
                make_bulk_scan_message(
                    message_id="ctx_1",
                    content="I prefer PostgreSQL for this kind of workload",
                    author_id="dba_carol",
                    author_username="carol",
                ),
                make_bulk_scan_message(
                    message_id="ctx_2",
                    content=(
                        "Fair point, but have you considered the "
                        "read-heavy pattern? MongoDB might be worth it"
                    ),
                    author_id="dba_dave",
                    author_username="dave",
                ),
            ]
            message = make_bulk_scan_message(
                message_id="msg_reply",
                content=("That's a good point, let me benchmark both and share results"),
                author_id="dba_carol",
                author_username="carol",
            )

            result = await service.detect_flashpoint(message, context)

        assert result is None

    @pytest.mark.asyncio
    async def test_context_truncation_uses_most_recent(self):
        """With max_context=2, only the last 2 messages are included."""
        service = FlashpointDetectionService(model="openai/gpt-5-mini")

        captured_args: dict = {}

        def capture_detector(*args, **kwargs):
            captured_args.update(kwargs)
            mock_result = MagicMock()
            mock_result.derailment_score = 70
            mock_result.reasoning = "Truncated context analysis"
            return mock_result

        mock_detector = MagicMock()
        mock_detector.side_effect = capture_detector

        with patch.object(service, "_get_detector", return_value=mock_detector):
            context = [
                make_bulk_scan_message(
                    message_id="old_1",
                    content="This old message should be excluded",
                    author_username="old_user",
                ),
                make_bulk_scan_message(
                    message_id="old_2",
                    content="Another old message",
                    author_username="old_user2",
                ),
                make_bulk_scan_message(
                    message_id="recent_1",
                    content="Recent message one",
                    author_username="recent_user",
                ),
                make_bulk_scan_message(
                    message_id="recent_2",
                    content="Recent message two",
                    author_username="recent_user2",
                ),
            ]
            message = make_bulk_scan_message(
                content="The trigger message",
                author_username="trigger_user",
            )

            result = await service.detect_flashpoint(message, context, max_context=2)

        assert result is not None
        assert result.context_messages == 2
        context_str = captured_args["context"]
        assert "Recent message one" in context_str
        assert "Recent message two" in context_str
        assert "old message should be excluded" not in context_str

    @pytest.mark.asyncio
    async def test_transient_error_returns_none_gracefully(self):
        """Transient network error returns None without raising."""
        service = FlashpointDetectionService(model="openai/gpt-5-mini")

        mock_detector = MagicMock()
        mock_detector.side_effect = OSError("Network unreachable")

        with (
            patch.object(service, "_get_detector", return_value=mock_detector),
            patch("src.bulk_content_scan.flashpoint_service.logger") as mock_logger,
        ):
            message = make_bulk_scan_message(
                content="Some message during network outage",
                author_username="user_during_outage",
            )

            result = await service.detect_flashpoint(message, [])

        assert result is None
        mock_logger.warning.assert_called_once()


class TestDerailmentScoreThreshold:
    """Tests for derailment score threshold behavior."""

    @pytest.mark.asyncio
    async def test_score_zero_returns_none(self):
        """Score of 0 returns None (below default threshold)."""
        service = FlashpointDetectionService(model="openai/gpt-5-mini")

        mock_prediction = MagicMock(spec=dspy.Prediction)
        mock_prediction.derailment_score = 0
        mock_prediction.reasoning = "No risk"

        mock_detector = MagicMock()
        mock_detector.return_value = mock_prediction

        with patch.object(service, "_get_detector", return_value=mock_detector):
            message = make_bulk_scan_message()
            result = await service.detect_flashpoint(message, [])

        assert result is None

    @pytest.mark.asyncio
    async def test_score_100_returns_match(self):
        """Score of 100 always returns a match."""
        service = FlashpointDetectionService(model="openai/gpt-5-mini")

        mock_prediction = MagicMock(spec=dspy.Prediction)
        mock_prediction.derailment_score = 100
        mock_prediction.reasoning = "Certain derailment"

        mock_detector = MagicMock()
        mock_detector.return_value = mock_prediction

        with patch.object(service, "_get_detector", return_value=mock_detector):
            message = make_bulk_scan_message()
            result = await service.detect_flashpoint(message, [])

        assert result is not None
        assert result.derailment_score == 100

    @pytest.mark.asyncio
    async def test_score_clamped_above_100(self):
        """Score > 100 is clamped to 100."""
        service = FlashpointDetectionService(model="openai/gpt-5-mini")

        mock_prediction = MagicMock(spec=dspy.Prediction)
        mock_prediction.derailment_score = 150
        mock_prediction.reasoning = "Over max"

        mock_detector = MagicMock()
        mock_detector.return_value = mock_prediction

        with patch.object(service, "_get_detector", return_value=mock_detector):
            message = make_bulk_scan_message()
            result = await service.detect_flashpoint(message, [])

        assert result is not None
        assert result.derailment_score == 100


class TestValueErrorPropagation:
    """Tests that ValueError is NOT a transient error."""

    def test_value_error_not_in_transient_errors(self):
        """ValueError is not in the _TRANSIENT_ERRORS tuple."""
        assert ValueError not in _TRANSIENT_ERRORS

    def test_transient_errors_contains_expected_types(self):
        """_TRANSIENT_ERRORS contains exactly the expected types."""
        assert TimeoutError in _TRANSIENT_ERRORS
        assert ConnectionError in _TRANSIENT_ERRORS
        assert OSError in _TRANSIENT_ERRORS
        assert len(_TRANSIENT_ERRORS) == 3

    @pytest.mark.asyncio
    async def test_value_error_propagates_as_critical(self):
        """ValueError raises as critical, not swallowed as transient."""
        service = FlashpointDetectionService(model="openai/gpt-5-mini")

        mock_detector = MagicMock()
        mock_detector.side_effect = ValueError("Bad LLM output format")

        with (
            patch.object(service, "_get_detector", return_value=mock_detector),
            patch("src.bulk_content_scan.flashpoint_service.logger") as mock_logger,
        ):
            message = make_bulk_scan_message()

            with pytest.raises(ValueError, match="Bad LLM output format"):
                await service.detect_flashpoint(message, [])

        mock_logger.error.assert_called_once()


class TestConcurrencyGuard:
    """Tests for thread-safe _get_detector initialization."""

    @patch("dspy.LM")
    def test_single_initialization_under_concurrent_access(
        self, mock_lm_cls: MagicMock, tmp_path: Path
    ):
        """Concurrent calls to _get_detector produce one initialization."""
        import concurrent.futures

        service = FlashpointDetectionService(
            model="openai/gpt-5-mini",
            optimized_model_path=tmp_path / "nonexistent.json",
        )

        detectors = []

        def call_get_detector():
            return service._get_detector()

        with (
            patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}),
            concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor,
        ):
            futures = [executor.submit(call_get_detector) for _ in range(20)]
            for f in concurrent.futures.as_completed(futures):
                detectors.append(f.result())

        assert all(d is detectors[0] for d in detectors)
        mock_lm_cls.assert_called_once_with("openai/gpt-5-mini")

    def test_init_lock_exists(self):
        """Service has a threading.Lock for initialization."""
        import threading

        service = FlashpointDetectionService()
        assert isinstance(service._init_lock, type(threading.Lock()))


class TestApiKeyValidation:
    """Tests for API key validation in _get_detector."""

    def test_raises_when_openai_key_missing(self, tmp_path: Path):
        """RuntimeError when OPENAI_API_KEY not set for openai/ model."""
        service = FlashpointDetectionService(
            model="openai/gpt-5-mini",
            optimized_model_path=tmp_path / "nonexistent.json",
        )

        with (
            patch.dict("os.environ", {}, clear=True),
            pytest.raises(RuntimeError, match="OPENAI_API_KEY"),
        ):
            service._get_detector()

    def test_raises_when_anthropic_key_missing(self, tmp_path: Path):
        """RuntimeError when ANTHROPIC_API_KEY not set."""
        service = FlashpointDetectionService(
            model="anthropic/claude-3-haiku",
            optimized_model_path=tmp_path / "nonexistent.json",
        )

        with (
            patch.dict("os.environ", {}, clear=True),
            pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"),
        ):
            service._get_detector()

    @patch("dspy.LM")
    def test_no_error_when_openai_key_set(self, mock_lm_cls: MagicMock, tmp_path: Path):
        """No error when OPENAI_API_KEY is set."""
        service = FlashpointDetectionService(
            model="openai/gpt-5-mini",
            optimized_model_path=tmp_path / "nonexistent.json",
        )

        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test-key"}):
            detector = service._get_detector()

        assert detector is not None

    @patch("dspy.LM")
    def test_unknown_provider_skips_validation(self, mock_lm_cls: MagicMock, tmp_path: Path):
        """Unknown model prefixes skip API key validation."""
        service = FlashpointDetectionService(
            model="together/llama-3-70b",
            optimized_model_path=tmp_path / "nonexistent.json",
        )

        with patch.dict("os.environ", {}, clear=True):
            detector = service._get_detector()

        assert detector is not None

    @pytest.mark.asyncio
    async def test_existing_tests_not_broken_by_validation(self):
        """Tests that mock _get_detector bypass API key validation."""
        service = FlashpointDetectionService(model="openai/gpt-5-mini")

        mock_prediction = MagicMock(spec=dspy.Prediction)
        mock_prediction.derailment_score = 10
        mock_prediction.reasoning = "Normal"

        mock_detector = MagicMock()
        mock_detector.return_value = mock_prediction

        with patch.object(service, "_get_detector", return_value=mock_detector):
            message = make_bulk_scan_message()
            result = await service.detect_flashpoint(message, [])

        assert result is None


class TestCriticalErrorPropagation:
    """Tests for critical error type propagation.

    Transient errors (TimeoutError, ConnectionError, OSError) return None.
    All other exceptions propagate as critical errors.
    """

    @pytest.mark.asyncio
    async def test_type_error_propagates(self):
        """TypeError propagates as a critical error."""
        service = FlashpointDetectionService(model="openai/gpt-5-mini")

        mock_detector = MagicMock()
        mock_detector.side_effect = TypeError("unsupported operand type")

        with (
            patch.object(service, "_get_detector", return_value=mock_detector),
            patch("src.bulk_content_scan.flashpoint_service.logger") as mock_logger,
        ):
            message = make_bulk_scan_message()
            with pytest.raises(TypeError, match="unsupported operand type"):
                await service.detect_flashpoint(message, [])

        mock_logger.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_key_error_propagates(self):
        """KeyError propagates as a critical error."""
        service = FlashpointDetectionService(model="openai/gpt-5-mini")

        mock_detector = MagicMock()
        mock_detector.side_effect = KeyError("missing_field")

        with (
            patch.object(service, "_get_detector", return_value=mock_detector),
            patch("src.bulk_content_scan.flashpoint_service.logger") as mock_logger,
        ):
            message = make_bulk_scan_message()
            with pytest.raises(KeyError, match="missing_field"):
                await service.detect_flashpoint(message, [])

        mock_logger.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_attribute_error_propagates(self):
        """AttributeError propagates as a critical error."""
        service = FlashpointDetectionService(model="openai/gpt-5-mini")

        mock_detector = MagicMock()
        mock_detector.side_effect = AttributeError("'NoneType' has no attribute 'derailment_score'")

        with (
            patch.object(service, "_get_detector", return_value=mock_detector),
            patch("src.bulk_content_scan.flashpoint_service.logger") as mock_logger,
        ):
            message = make_bulk_scan_message()
            with pytest.raises(AttributeError, match="has no attribute"):
                await service.detect_flashpoint(message, [])

        mock_logger.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_runtime_error_propagates(self):
        """RuntimeError propagates as a critical error."""
        service = FlashpointDetectionService(model="openai/gpt-5-mini")

        mock_detector = MagicMock()
        mock_detector.side_effect = RuntimeError("LLM API auth failure")

        with (
            patch.object(service, "_get_detector", return_value=mock_detector),
            patch("src.bulk_content_scan.flashpoint_service.logger") as mock_logger,
        ):
            message = make_bulk_scan_message()
            with pytest.raises(RuntimeError, match="LLM API auth failure"):
                await service.detect_flashpoint(message, [])

        mock_logger.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_value_error_propagates_as_critical(self):
        """ValueError propagates (programming error, not transient)."""
        service = FlashpointDetectionService(model="openai/gpt-5-mini")

        mock_detector = MagicMock()
        mock_detector.side_effect = ValueError("invalid literal")

        with (
            patch.object(service, "_get_detector", return_value=mock_detector),
            patch("src.bulk_content_scan.flashpoint_service.logger") as mock_logger,
        ):
            message = make_bulk_scan_message()
            with pytest.raises(ValueError, match="invalid literal"):
                await service.detect_flashpoint(message, [])

        mock_logger.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_os_error_is_transient(self):
        """OSError is treated as transient (returns None)."""
        service = FlashpointDetectionService(model="openai/gpt-5-mini")

        mock_detector = MagicMock()
        mock_detector.side_effect = OSError("Network unreachable")

        with patch.object(service, "_get_detector", return_value=mock_detector):
            message = make_bulk_scan_message()
            result = await service.detect_flashpoint(message, [])

        assert result is None
