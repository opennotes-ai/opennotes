import pytest

from src.notes.scoring import ScoringTier, get_tier_config, get_tier_warnings

pytestmark = pytest.mark.unit


TIER_ORDER = [
    ScoringTier.MINIMAL,
    ScoringTier.LIMITED,
    ScoringTier.BASIC,
    ScoringTier.INTERMEDIATE,
    ScoringTier.ADVANCED,
    ScoringTier.FULL,
]


class TestGetWarnings:
    def test_warnings_for_low_confidence_tier(self):
        tier = ScoringTier.MINIMAL
        note_count = 150

        warnings = get_tier_warnings(note_count, tier)

        assert len(warnings) >= 1
        assert any("Limited data confidence" in w for w in warnings)

    def test_warnings_for_below_production_threshold(self):
        tier = ScoringTier.MINIMAL
        note_count = 150

        warnings = get_tier_warnings(note_count, tier)

        assert any("Below production threshold" in w for w in warnings)
        assert any("Matrix factorization requires at least 200 notes" in w for w in warnings)

    def test_warnings_approaching_next_tier(self):
        tier = ScoringTier.LIMITED
        tier_config = get_tier_config(tier)
        note_count = int(tier_config.max_notes * 0.95)

        warnings = get_tier_warnings(note_count, tier)

        assert any("Approaching next tier" in w for w in warnings)
        assert any("basic tier soon" in w for w in warnings)

    def test_warnings_at_maximum_tier_no_index_error(self):
        tier = ScoringTier.FULL
        note_count = 55000

        warnings = get_tier_warnings(note_count, tier)

        assert any("At maximum tier" in w for w in warnings)
        assert any("full" in w for w in warnings)
        assert any("Using full scoring pipeline" in w for w in warnings)

    def test_no_warnings_for_healthy_mid_tier(self):
        tier = ScoringTier.BASIC
        note_count = 3000

        warnings = get_tier_warnings(note_count, tier)

        assert len(warnings) == 0

    def test_warnings_for_each_tier_approaching_threshold(self):
        for i, tier in enumerate(TIER_ORDER):
            tier_config = get_tier_config(tier)
            if tier_config.max_notes is None:
                continue

            note_count = int(tier_config.max_notes * 0.95)
            warnings = get_tier_warnings(note_count, tier)

            if i < len(TIER_ORDER) - 1:
                assert any("Approaching next tier" in w for w in warnings)
            else:
                assert any("At maximum tier" in w for w in warnings)

    def test_no_index_error_at_max_tier_boundary(self):
        max_tier = TIER_ORDER[-1]
        note_count = 60000

        try:
            warnings = get_tier_warnings(note_count, max_tier)
            assert isinstance(warnings, list)
        except IndexError:
            pytest.fail("IndexError raised when accessing max tier warnings")

    def test_warnings_combine_multiple_conditions(self):
        tier = ScoringTier.MINIMAL
        tier_config = get_tier_config(tier)
        note_count = int(tier_config.max_notes * 0.95)

        warnings = get_tier_warnings(note_count, tier)

        assert len(warnings) >= 2
        assert any("Limited data confidence" in w for w in warnings)
        assert any("Below production threshold" in w for w in warnings)
        assert any("Approaching next tier" in w for w in warnings)

    def test_tier_without_max_notes_no_approaching_warning(self):
        tier = TIER_ORDER[-1]
        note_count = 100000

        warnings = get_tier_warnings(note_count, tier)

        assert not any("Approaching next tier" in w for w in warnings)

    def test_warning_message_includes_tier_name(self):
        max_tier = TIER_ORDER[-1]
        note_count = 60000

        warnings = get_tier_warnings(note_count, max_tier)

        matching_warnings = [w for w in warnings if "At maximum tier" in w]
        assert len(matching_warnings) > 0
        assert "full" in matching_warnings[0]
