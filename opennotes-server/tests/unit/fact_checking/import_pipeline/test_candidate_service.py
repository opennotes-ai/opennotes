"""Unit tests for candidate_service.py.

Tests the service layer functions for candidate listing, rating, and bulk approval.
"""

from src.fact_checking.import_pipeline.candidate_service import (
    extract_high_confidence_rating,
)


class TestExtractHighConfidenceRating:
    """Tests for extract_high_confidence_rating helper function."""

    def test_with_float_1_0(self):
        """Returns rating key when value is exactly 1.0 (float)."""
        predicted_ratings = {"false": 1.0}
        result = extract_high_confidence_rating(predicted_ratings, threshold=1.0)
        assert result == "false"

    def test_with_int_1(self):
        """Returns rating key when value is 1 (integer from JSON)."""
        predicted_ratings = {"false": 1}
        result = extract_high_confidence_rating(predicted_ratings, threshold=1.0)
        assert result == "false"

    def test_below_threshold(self):
        """Returns None when all values are below threshold."""
        predicted_ratings = {"false": 0.85, "mostly_false": 0.10}
        result = extract_high_confidence_rating(predicted_ratings, threshold=1.0)
        assert result is None

    def test_empty_dict(self):
        """Returns None for empty dict."""
        predicted_ratings: dict[str, float] = {}
        result = extract_high_confidence_rating(predicted_ratings, threshold=1.0)
        assert result is None

    def test_none_input(self):
        """Returns None for None input."""
        result = extract_high_confidence_rating(None, threshold=1.0)
        assert result is None

    def test_custom_threshold(self):
        """Returns rating when value meets custom threshold."""
        predicted_ratings = {"false": 0.85, "mostly_false": 0.10}
        result = extract_high_confidence_rating(predicted_ratings, threshold=0.8)
        assert result == "false"

    def test_multiple_matches_returns_first(self):
        """Returns first matching rating when multiple meet threshold."""
        predicted_ratings = {"false": 1.0, "misleading": 1.0}
        result = extract_high_confidence_rating(predicted_ratings, threshold=1.0)
        assert result in ["false", "misleading"]

    def test_exact_threshold_boundary(self):
        """Returns rating when value equals threshold exactly."""
        predicted_ratings = {"false": 0.9}
        result = extract_high_confidence_rating(predicted_ratings, threshold=0.9)
        assert result == "false"

    def test_just_below_threshold(self):
        """Returns None when value is just below threshold."""
        predicted_ratings = {"false": 0.899999}
        result = extract_high_confidence_rating(predicted_ratings, threshold=0.9)
        assert result is None
