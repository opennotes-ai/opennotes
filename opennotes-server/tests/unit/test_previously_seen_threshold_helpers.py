"""Unit tests for previously-seen threshold resolution helpers."""

from unittest.mock import MagicMock

from src.config import settings
from src.fact_checking.threshold_helpers import get_previously_seen_thresholds


class TestThresholdResolutionHelpers:
    """Test threshold resolution logic with channel overrides."""

    def test_get_thresholds_with_none_channel_returns_defaults(self):
        """Test get_previously_seen_thresholds returns config defaults when channel is None."""
        autopublish, autorequest = get_previously_seen_thresholds(None)

        assert autopublish == settings.PREVIOUSLY_SEEN_AUTOPUBLISH_THRESHOLD
        assert autorequest == settings.PREVIOUSLY_SEEN_AUTOREQUEST_THRESHOLD
        assert autopublish == 0.9
        assert autorequest == 0.75

    def test_get_thresholds_with_null_overrides_returns_defaults(self):
        """Test get_previously_seen_thresholds returns config defaults when overrides are NULL."""
        mock_channel = MagicMock()
        mock_channel.previously_seen_autopublish_threshold = None
        mock_channel.previously_seen_autorequest_threshold = None

        autopublish, autorequest = get_previously_seen_thresholds(mock_channel)

        assert autopublish == settings.PREVIOUSLY_SEEN_AUTOPUBLISH_THRESHOLD
        assert autorequest == settings.PREVIOUSLY_SEEN_AUTOREQUEST_THRESHOLD

    def test_get_thresholds_with_autopublish_override(self):
        """Test get_previously_seen_thresholds uses autopublish override when set."""
        mock_channel = MagicMock()
        mock_channel.previously_seen_autopublish_threshold = 0.95
        mock_channel.previously_seen_autorequest_threshold = None

        autopublish, autorequest = get_previously_seen_thresholds(mock_channel)

        assert autopublish == 0.95  # Override
        assert autorequest == settings.PREVIOUSLY_SEEN_AUTOREQUEST_THRESHOLD  # Default

    def test_get_thresholds_with_autorequest_override(self):
        """Test get_previously_seen_thresholds uses autorequest override when set."""
        mock_channel = MagicMock()
        mock_channel.previously_seen_autopublish_threshold = None
        mock_channel.previously_seen_autorequest_threshold = 0.8

        autopublish, autorequest = get_previously_seen_thresholds(mock_channel)

        assert autopublish == settings.PREVIOUSLY_SEEN_AUTOPUBLISH_THRESHOLD  # Default
        assert autorequest == 0.8  # Override

    def test_get_thresholds_with_both_overrides(self):
        """Test get_previously_seen_thresholds uses both overrides when set."""
        mock_channel = MagicMock()
        mock_channel.previously_seen_autopublish_threshold = 0.88
        mock_channel.previously_seen_autorequest_threshold = 0.72

        autopublish, autorequest = get_previously_seen_thresholds(mock_channel)

        assert autopublish == 0.88
        assert autorequest == 0.72

    def test_get_thresholds_independent_resolution(self):
        """Test autopublish and autorequest thresholds resolve independently."""
        mock_channel = MagicMock()

        # Test 1: Only autopublish override
        mock_channel.previously_seen_autopublish_threshold = 0.92
        mock_channel.previously_seen_autorequest_threshold = None
        ap1, ar1 = get_previously_seen_thresholds(mock_channel)
        assert ap1 == 0.92
        assert ar1 == settings.PREVIOUSLY_SEEN_AUTOREQUEST_THRESHOLD

        # Test 2: Only autorequest override
        mock_channel.previously_seen_autopublish_threshold = None
        mock_channel.previously_seen_autorequest_threshold = 0.68
        ap2, ar2 = get_previously_seen_thresholds(mock_channel)
        assert ap2 == settings.PREVIOUSLY_SEEN_AUTOPUBLISH_THRESHOLD
        assert ar2 == 0.68

    def test_get_thresholds_zero_values_are_valid_overrides(self):
        """Test that zero values are treated as valid overrides (not NULL)."""
        mock_channel = MagicMock()
        mock_channel.previously_seen_autopublish_threshold = 0.0
        mock_channel.previously_seen_autorequest_threshold = 0.0

        autopublish, autorequest = get_previously_seen_thresholds(mock_channel)

        assert autopublish == 0.0  # Should use override, not default
        assert autorequest == 0.0  # Should use override, not default

    def test_get_thresholds_returns_tuple(self):
        """Test get_previously_seen_thresholds returns a tuple of two floats."""
        result = get_previously_seen_thresholds(None)

        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], float)
        assert isinstance(result[1], float)
