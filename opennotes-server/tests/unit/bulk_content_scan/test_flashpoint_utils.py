"""Unit tests for flashpoint_utils."""

import logging
from unittest.mock import MagicMock

import dspy
import pytest

from src.bulk_content_scan.flashpoint_utils import parse_bool, parse_derailment_score


class TestParseBool:
    """Tests for parse_bool covering bool passthrough, positive/negative strings,
    unrecognized strings, and non-string types."""

    @pytest.mark.parametrize("value", [True, False])
    def test_bool_passthrough(self, value: bool):
        assert parse_bool(value) is value

    @pytest.mark.parametrize("value", ["true", "True", "TRUE", "yes", "Yes", "1", "y", "Y"])
    def test_positive_strings(self, value: str):
        assert parse_bool(value) is True

    @pytest.mark.parametrize("value", ["false", "False", "FALSE", "no", "No", "0", "n", "N"])
    def test_negative_strings(self, value: str):
        assert parse_bool(value) is False

    @pytest.mark.parametrize(
        "value",
        [
            "maybe",
            "uncertain",
            "something",
            "The conversation might derail",
            "I think so",
            "possibly",
        ],
    )
    def test_unrecognized_strings_return_false(self, value: str, caplog):
        with caplog.at_level(logging.WARNING, logger="src.bulk_content_scan.flashpoint_utils"):
            result = parse_bool(value)
        assert result is False
        assert "unrecognized string" in caplog.text

    def test_empty_string_returns_false(self):
        assert parse_bool("") is False

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (1, True),
            (0, False),
            (42, True),
            (0.0, False),
            (3.14, True),
            (None, False),
            ([], False),
            ([1], True),
        ],
    )
    def test_non_string_types(self, value, expected: bool):
        assert parse_bool(value) is expected


class TestParseDerailmentScore:
    """Tests for parse_derailment_score covering int, float, string, clamping."""

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (0, 0),
            (50, 50),
            (100, 100),
            (42, 42),
        ],
    )
    def test_int_passthrough(self, value: int, expected: int):
        assert parse_derailment_score(value) == expected

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (-10, 0),
            (150, 100),
            (-1, 0),
            (101, 100),
        ],
    )
    def test_int_clamping(self, value: int, expected: int):
        assert parse_derailment_score(value) == expected

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (49.5, 50),
            (0.0, 0),
            (100.0, 100),
            (99.9, 100),
            (0.4, 0),
        ],
    )
    def test_float_rounding(self, value: float, expected: int):
        assert parse_derailment_score(value) == expected

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("0", 0),
            ("50", 50),
            ("100", 100),
            ("42", 42),
            (" 75 ", 75),
            ("33.7", 33),
        ],
    )
    def test_string_parsing(self, value: str, expected: int):
        assert parse_derailment_score(value) == expected

    def test_string_clamping(self):
        assert parse_derailment_score("-5") == 0
        assert parse_derailment_score("200") == 100

    def test_unrecognized_string_returns_zero(self, caplog):
        with caplog.at_level(logging.WARNING, logger="src.bulk_content_scan.flashpoint_utils"):
            result = parse_derailment_score("high risk")
        assert result == 0
        assert "unrecognized string" in caplog.text

    def test_none_returns_zero(self, caplog):
        with caplog.at_level(logging.WARNING, logger="src.bulk_content_scan.flashpoint_utils"):
            result = parse_derailment_score(None)
        assert result == 0


class TestTwoStageFlashpointDetector:
    """Tests for TwoStageFlashpointDetector context pass-through and ScoringSignature fields."""

    def test_scoring_signature_has_context_field(self):
        from src.bulk_content_scan.flashpoint_utils import ScoringSignature

        sig = ScoringSignature.get()
        field_names = list(sig.input_fields.keys())
        assert "context" in field_names

    def test_scoring_signature_has_escalation_analysis_field(self):
        from src.bulk_content_scan.flashpoint_utils import ScoringSignature

        sig = ScoringSignature.get()
        field_names = list(sig.input_fields.keys())
        assert "escalation_analysis" in field_names
        assert "escalation_summary" not in field_names

    def test_forward_passes_context_to_scorer(self):
        from src.bulk_content_scan.flashpoint_utils import TwoStageFlashpointDetector

        detector = TwoStageFlashpointDetector()

        mock_summary_result = MagicMock()
        mock_summary_result.escalation_summary = "test analysis"
        detector._inner.summarize = MagicMock(return_value=mock_summary_result)

        mock_score_result = MagicMock()
        mock_score_result.derailment_score = 75
        mock_score_result.reasoning = "test"
        detector._inner.score = MagicMock(return_value=mock_score_result)

        detector(context="user1: hello\nuser2: shut up", message="user1: you're terrible")

        detector._inner.score.assert_called_once_with(
            context="user1: hello\nuser2: shut up",
            message="user1: you're terrible",
            escalation_analysis="test analysis",
        )

    def test_forward_passes_context_to_summarizer(self):
        from src.bulk_content_scan.flashpoint_utils import TwoStageFlashpointDetector

        detector = TwoStageFlashpointDetector()

        mock_summary_result = MagicMock()
        mock_summary_result.escalation_summary = "signals detected"
        detector._inner.summarize = MagicMock(return_value=mock_summary_result)

        mock_score_result = MagicMock()
        mock_score_result.derailment_score = 30
        mock_score_result.reasoning = "low risk"
        detector._inner.score = MagicMock(return_value=mock_score_result)

        detector(context="some context", message="some message")

        detector._inner.summarize.assert_called_once_with(
            context="some context",
            message="some message",
        )


class TestRubricDetector:
    """Tests for RubricDetector categorical classification."""

    def test_risk_level_mapping_covers_all_categories(self):
        from src.bulk_content_scan.flashpoint_utils import RISK_LEVEL_MAPPING

        assert set(RISK_LEVEL_MAPPING.keys()) == {
            "Low Risk",
            "Guarded",
            "Heated",
            "Hostile",
            "Dangerous",
        }

    def test_risk_level_mapping_values_are_ordered(self):
        from src.bulk_content_scan.flashpoint_utils import RISK_LEVEL_MAPPING

        values = list(RISK_LEVEL_MAPPING.values())
        assert values == sorted(values)

    def test_unknown_category_falls_back_to_default(self):
        from src.bulk_content_scan.flashpoint_utils import RISK_LEVEL_DEFAULT, RISK_LEVEL_MAPPING

        assert RISK_LEVEL_MAPPING.get("Unknown Category", RISK_LEVEL_DEFAULT) == 50

    def test_rubric_detector_has_assess_attribute(self):
        from src.bulk_content_scan.flashpoint_utils import RubricDetector

        detector = RubricDetector()
        assert hasattr(detector, "assess")
        assert isinstance(detector.assess, dspy.ChainOfThought)

    def test_rubric_detector_inner_module_exists(self):
        from src.bulk_content_scan.flashpoint_utils import RubricDetector

        detector = RubricDetector()
        assert hasattr(detector, "_inner")

    def test_rubric_detector_forward_with_mock(self):
        from src.bulk_content_scan.flashpoint_utils import RubricDetector

        detector = RubricDetector()
        mock_result = MagicMock()
        mock_result.risk_level = "Hostile"
        mock_result.reasoning = "Personal attacks detected"
        detector._inner.assess = MagicMock(return_value=mock_result)

        result = detector(context="user1: hello", message="user2: you're an idiot")
        assert result.derailment_score == 85
        assert result.reasoning == "Personal attacks detected"
        assert result.risk_level == "Hostile"

    def test_rubric_detector_unknown_category_returns_default(self):
        from src.bulk_content_scan.flashpoint_utils import RubricDetector

        detector = RubricDetector()
        mock_result = MagicMock()
        mock_result.risk_level = "Somewhat Risky"
        mock_result.reasoning = "test"
        detector._inner.assess = MagicMock(return_value=mock_result)

        result = detector(context="test", message="test")
        assert result.derailment_score == 50
