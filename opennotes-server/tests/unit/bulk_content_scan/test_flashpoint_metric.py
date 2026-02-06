"""Unit tests for flashpoint metric functions."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import dspy
from dspy.teleprompt.gepa.gepa_utils import ScoreWithFeedback

from scripts.flashpoints.flashpoint_module import (
    FeedbackGenerator,
    _extract_reasoning,
    _static_feedback,
    comparative_flashpoint_metric,
    make_comparative_metric,
)


class TestExtractReasoning:
    def test_none_trace(self):
        assert _extract_reasoning(None) == ("N/A", "N/A")

    def test_empty_trace(self):
        assert _extract_reasoning([]) == ("N/A", "N/A")

    def test_single_entry(self):
        pred = MagicMock()
        pred.reasoning = "some reasoning"
        trace = [(MagicMock(), {}, pred)]
        assert _extract_reasoning(trace) == ("some reasoning", "N/A")

    def test_two_entries(self):
        pred1 = MagicMock()
        pred1.reasoning = "derailing reason"
        pred2 = MagicMock()
        pred2.reasoning = "non-derailing reason"
        trace = [(MagicMock(), {}, pred1), (MagicMock(), {}, pred2)]
        assert _extract_reasoning(trace) == ("derailing reason", "non-derailing reason")

    def test_no_reasoning_attr(self):
        pred = MagicMock(spec=[])
        trace = [(MagicMock(), {}, pred)]
        assert _extract_reasoning(trace) == ("N/A", "N/A")

    def test_truncates_long_reasoning(self):
        pred = MagicMock()
        pred.reasoning = "x" * 500
        trace = [(MagicMock(), {}, pred)]
        r1, _ = _extract_reasoning(trace)
        assert len(r1) == 300


class TestStaticFeedback:
    def test_correct_prediction(self):
        fb = _static_feedback(80, 30, 50, "high risk", "low risk")
        assert "CORRECT" in fb
        assert "80/100" in fb
        assert "30/100" in fb
        assert "+50" in fb
        assert "high risk" in fb
        assert "low risk" in fb

    def test_wrong_prediction(self):
        fb = _static_feedback(30, 80, -50, "missed signals", "benign")
        assert "WRONG" in fb
        assert "should have scored higher" in fb

    def test_tied_prediction(self):
        fb = _static_feedback(50, 50, 0, "r1", "r2")
        assert "TIED (WRONG)" in fb
        assert "should have scored higher" in fb

    def test_narrow_margin(self):
        fb = _static_feedback(55, 40, 15, "r1", "r2")
        assert "CORRECT" in fb
        assert "narrow" in fb.lower()

    def test_wide_margin_no_narrow_warning(self):
        fb = _static_feedback(90, 10, 80, "r1", "r2")
        assert "narrow" not in fb.lower()

    def test_no_prescriptive_content(self):
        fb = _static_feedback(30, 80, -50, "r1", "r2")
        assert "personal attacks" not in fb.lower()
        assert "absolutist language" not in fb.lower()
        assert "questioning competence" not in fb.lower()
        assert "escalation signals such as" not in fb.lower()
        assert "constructive disagreement" not in fb.lower()


class TestComparativeFlashpointMetric:
    def test_correct_returns_score_1(self):
        pred = dspy.Prediction(derailing_score=80, non_derailing_score=20)
        gold = dspy.Example()
        result = comparative_flashpoint_metric(gold, pred)
        assert isinstance(result, ScoreWithFeedback)
        assert result.score == 1.0

    def test_wrong_returns_score_0(self):
        pred = dspy.Prediction(derailing_score=20, non_derailing_score=80)
        gold = dspy.Example()
        result = comparative_flashpoint_metric(gold, pred)
        assert result.score == 0.0

    def test_tied_returns_score_0(self):
        pred = dspy.Prediction(derailing_score=50, non_derailing_score=50)
        gold = dspy.Example()
        result = comparative_flashpoint_metric(gold, pred)
        assert result.score == 0.0

    def test_feedback_is_factual(self):
        pred = dspy.Prediction(derailing_score=30, non_derailing_score=70)
        gold = dspy.Example()
        result = comparative_flashpoint_metric(gold, pred)
        assert "personal attacks" not in result.feedback.lower()
        assert "absolutist" not in result.feedback.lower()
        assert "30/100" in result.feedback
        assert "70/100" in result.feedback

    def test_uses_pred_trace_for_reasoning(self):
        pred = dspy.Prediction(derailing_score=80, non_derailing_score=20)
        gold = dspy.Example()
        mock_output1 = MagicMock()
        mock_output1.reasoning = "aggressive tone detected"
        mock_output2 = MagicMock()
        mock_output2.reasoning = "calm discussion"
        pred_trace = [
            (MagicMock(), {}, mock_output1),
            (MagicMock(), {}, mock_output2),
        ]
        result = comparative_flashpoint_metric(gold, pred, pred_trace=pred_trace)
        assert "aggressive tone detected" in result.feedback
        assert "calm discussion" in result.feedback

    def test_no_pred_trace_shows_na(self):
        pred = dspy.Prediction(derailing_score=80, non_derailing_score=20)
        gold = dspy.Example()
        result = comparative_flashpoint_metric(gold, pred)
        assert "N/A" in result.feedback


class TestMakeComparativeMetric:
    def test_static_mode_returns_default(self):
        metric = make_comparative_metric("static")
        assert metric is comparative_flashpoint_metric

    def test_dynamic_mode_returns_different(self):
        metric = make_comparative_metric("dynamic")
        assert metric is not comparative_flashpoint_metric

    def test_default_is_static(self):
        metric = make_comparative_metric()
        assert metric is comparative_flashpoint_metric


class TestFeedbackGenerator:
    @patch("scripts.flashpoints.flashpoint_module.dspy.Predict")
    def test_calls_predict_with_inputs(self, mock_predict_cls):
        mock_instance = MagicMock()
        mock_instance.return_value = MagicMock(feedback="diagnostic output")
        mock_predict_cls.return_value = mock_instance

        gen = FeedbackGenerator()
        result = gen(
            derailing_score=30,
            non_derailing_score=70,
            score_diff=-40,
            derailing_reasoning="missed signals",
            non_derailing_reasoning="benign",
        )
        assert result == "diagnostic output"
        mock_instance.assert_called_once()
