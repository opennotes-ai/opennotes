"""Tests for the flashpoint detection capability + service port."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.analyses.tone._flashpoint_schemas import FlashpointMatch, RiskLevel
from src.analyses.tone.flashpoint import detect_flashpoint
from src.services.flashpoint_service import (
    FlashpointDetectionService,
    parse_derailment_score,
    parse_risk_level,
)
from src.utterances.schema import Utterance


def _utt(
    utterance_id: str,
    text: str,
    *,
    author: str | None = "alice",
    kind: Literal["post", "comment", "reply"] = "comment",
    parent_id: str | None = None,
) -> Utterance:
    return Utterance(
        utterance_id=utterance_id,
        kind=kind,
        text=text,
        author=author,
        timestamp=datetime(2026, 4, 21, 12, 0, 0, tzinfo=UTC),
        parent_id=parent_id,
    )


class TestDetectFlashpointCapability:
    """Capability: detect_flashpoint(utterance, context, service)."""


    @pytest.mark.asyncio
    async def test_returns_match_when_service_detects_flashpoint(self):
        expected = FlashpointMatch(
            utterance_id="u-3",
            derailment_score=82,
            risk_level=RiskLevel.HOSTILE,
            reasoning="Escalating personal attacks",
            context_messages=2,
        )
        service = MagicMock(spec=FlashpointDetectionService)
        service.detect_flashpoint = AsyncMock(return_value=expected)

        utterance = _utt("u-3", "You never know what you're talking about")
        context = [_utt("u-1", "I disagree"), _utt("u-2", "You don't get it")]

        result = await detect_flashpoint(utterance, context, service)

        assert result is expected
        service.detect_flashpoint.assert_awaited_once()
        call_kwargs = service.detect_flashpoint.await_args.kwargs
        assert call_kwargs["utterance"] is utterance
        assert call_kwargs["context"] == context

    @pytest.mark.asyncio
    async def test_returns_none_when_service_returns_none(self):
        service = MagicMock(spec=FlashpointDetectionService)
        service.detect_flashpoint = AsyncMock(return_value=None)

        utterance = _utt("u-2", "Thanks for explaining")
        context = [_utt("u-1", "Here's the doc link")]

        result = await detect_flashpoint(utterance, context, service)

        assert result is None
        service.detect_flashpoint.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_empty_context_short_circuits_without_calling_service(self):
        """Standalone blog posts have no context — don't invoke the LLM."""
        service = MagicMock(spec=FlashpointDetectionService)
        service.detect_flashpoint = AsyncMock(return_value=None)

        blog_post = _utt("post-1", "A standalone article body", kind="post")

        result = await detect_flashpoint(blog_post, [], service)

        assert result is None
        service.detect_flashpoint.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_none_service_returns_none(self):
        utterance = _utt("u-1", "Any message")
        context = [_utt("u-0", "prior")]

        result = await detect_flashpoint(utterance, context, None)

        assert result is None

    @pytest.mark.asyncio
    async def test_service_exception_swallowed_returns_none(self):
        service = MagicMock(spec=FlashpointDetectionService)
        service.detect_flashpoint = AsyncMock(side_effect=RuntimeError("boom"))

        utterance = _utt("u-2", "text")
        context = [_utt("u-1", "prior")]

        result = await detect_flashpoint(utterance, context, service)

        assert result is None


class TestFlashpointDetectionService:
    """Service: FlashpointDetectionService.detect_flashpoint."""


    @pytest.mark.asyncio
    async def test_returns_match_when_score_above_threshold(self, monkeypatch):
        service = FlashpointDetectionService()

        mock_prediction = MagicMock()
        mock_prediction.derailment_score = 75
        mock_prediction.risk_level = "Hostile"
        mock_prediction.reasoning = "Escalation detected"

        mock_detector = MagicMock(return_value=mock_prediction)
        monkeypatch.setattr(service, "_get_detector", lambda: mock_detector)

        utterance = _utt("u-3", "You are wrong")
        context = [_utt("u-1", "First msg"), _utt("u-2", "Second msg")]

        result = await service.detect_flashpoint(utterance, context)

        assert result is not None
        assert isinstance(result, FlashpointMatch)
        assert result.utterance_id == "u-3"
        assert result.derailment_score == 75
        assert result.risk_level == RiskLevel.HOSTILE
        assert result.reasoning == "Escalation detected"
        assert result.context_messages == 2
        assert result.scan_type == "conversation_flashpoint"

    @pytest.mark.asyncio
    async def test_returns_none_when_score_below_threshold(self, monkeypatch):
        service = FlashpointDetectionService()

        mock_prediction = MagicMock()
        mock_prediction.derailment_score = 10
        mock_prediction.risk_level = "Low Risk"
        mock_prediction.reasoning = "Friendly chat"

        mock_detector = MagicMock(return_value=mock_prediction)
        monkeypatch.setattr(service, "_get_detector", lambda: mock_detector)

        result = await service.detect_flashpoint(
            _utt("u-2", "Thanks!"), [_utt("u-1", "Here is the doc")]
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_empty_context_allowed_at_service_layer(self, monkeypatch):
        """The service itself does not short-circuit on empty context.

        The capability layer enforces the blog-post rule; the service
        will score whatever the caller gives it.
        """
        service = FlashpointDetectionService()

        mock_prediction = MagicMock()
        mock_prediction.derailment_score = 85
        mock_prediction.risk_level = "Hostile"
        mock_prediction.reasoning = "Isolated hostile message"

        mock_detector = MagicMock(return_value=mock_prediction)
        monkeypatch.setattr(service, "_get_detector", lambda: mock_detector)

        result = await service.detect_flashpoint(_utt("u-1", "hostile"), [])

        assert result is not None
        assert result.context_messages == 0

    @pytest.mark.asyncio
    async def test_transient_error_returns_none(self, monkeypatch):
        service = FlashpointDetectionService()

        mock_detector = MagicMock(side_effect=TimeoutError("timeout"))
        monkeypatch.setattr(service, "_get_detector", lambda: mock_detector)

        result = await service.detect_flashpoint(
            _utt("u-1", "msg"), [_utt("u-0", "prev")]
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_critical_error_propagates(self, monkeypatch):
        service = FlashpointDetectionService()

        mock_detector = MagicMock(side_effect=RuntimeError("auth failure"))
        monkeypatch.setattr(service, "_get_detector", lambda: mock_detector)

        with pytest.raises(RuntimeError, match="auth failure"):
            await service.detect_flashpoint(
                _utt("u-1", "msg"), [_utt("u-0", "prev")]
            )

    @pytest.mark.asyncio
    async def test_max_context_truncates_to_recent(self, monkeypatch):
        service = FlashpointDetectionService()

        captured: dict[str, str] = {}

        def _fake_detector(context: str, message: str):
            captured["context"] = context
            captured["message"] = message
            mock = MagicMock()
            mock.derailment_score = 70
            mock.risk_level = "Hostile"
            mock.reasoning = "fake"
            return mock

        mock_detector = MagicMock(side_effect=_fake_detector)
        monkeypatch.setattr(service, "_get_detector", lambda: mock_detector)

        context = [
            _utt(f"u-{i}", f"msg {i}", author=f"user{i}") for i in range(10)
        ]
        result = await service.detect_flashpoint(
            _utt("u-trigger", "trigger", author="trigger_user"),
            context,
            max_context=3,
        )

        assert result is not None
        assert result.context_messages == 3
        context_lines = captured["context"].splitlines()
        assert len(context_lines) == 3
        assert "msg 9" in captured["context"]
        assert "msg 0" not in captured["context"]
        assert captured["message"].startswith("trigger_user:")

    @pytest.mark.asyncio
    async def test_custom_score_threshold(self, monkeypatch):
        service = FlashpointDetectionService()

        mock_prediction = MagicMock()
        mock_prediction.derailment_score = 30
        mock_prediction.risk_level = "Guarded"
        mock_prediction.reasoning = "Mild tension"

        mock_detector = MagicMock(return_value=mock_prediction)
        monkeypatch.setattr(service, "_get_detector", lambda: mock_detector)

        default_res = await service.detect_flashpoint(
            _utt("u-2", "text"), [_utt("u-1", "prev")]
        )
        assert default_res is None

        low_res = await service.detect_flashpoint(
            _utt("u-2", "text"),
            [_utt("u-1", "prev")],
            score_threshold=25,
        )
        assert low_res is not None
        assert low_res.derailment_score == 30
        assert low_res.risk_level == RiskLevel.GUARDED

    @pytest.mark.asyncio
    async def test_malformed_risk_level_normalized_via_fallback(self, monkeypatch):
        service = FlashpointDetectionService()

        mock_prediction = MagicMock()
        mock_prediction.derailment_score = 95
        mock_prediction.risk_level = "INVALID_NONSENSE"
        mock_prediction.reasoning = "bogus label"

        mock_detector = MagicMock(return_value=mock_prediction)
        monkeypatch.setattr(service, "_get_detector", lambda: mock_detector)

        result = await service.detect_flashpoint(
            _utt("u-2", "text"), [_utt("u-1", "prev")]
        )

        assert result is not None
        assert result.risk_level == RiskLevel.HOSTILE


class TestParseHelpers:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            (85, 85),
            (0, 0),
            (100, 100),
            (150, 100),
            (-10, 0),
            ("75", 75),
            ("  50  ", 50),
            ("gibberish", 0),
            (85.5, 86),
        ],
    )
    def test_parse_derailment_score(self, raw, expected):
        assert parse_derailment_score(raw) == expected

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("Hostile", "Hostile"),
            ("hostile", "Hostile"),
            ("LOW RISK", "Low Risk"),
            ("  heated  ", "Heated"),
        ],
    )
    def test_parse_risk_level_canonical(self, raw, expected):
        assert parse_risk_level(raw) == expected

    @pytest.mark.parametrize(
        ("score", "expected"),
        [
            (100, "Dangerous"),
            (85, "Hostile"),
            (60, "Heated"),
            (30, "Guarded"),
            (10, "Low Risk"),
        ],
    )
    def test_parse_risk_level_score_fallback(self, score, expected):
        assert parse_risk_level("gibberish", score) == expected

    def test_parse_risk_level_default(self):
        assert parse_risk_level("gibberish") == "Heated"


class TestDefaultOptimizedPath:
    def test_points_at_models_flashpoint_module_json(self):
        service = FlashpointDetectionService()
        path = service._get_default_optimized_path()
        assert path.name == "flashpoint_module.json"
        assert path.parent.name == "models"
