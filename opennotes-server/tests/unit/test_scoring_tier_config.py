import pytest

from src.notes.scoring.tier_config import (
    TIER_CONFIGURATIONS,
    ScoringTier,
    TierThresholds,
    get_tier_config,
    get_tier_for_note_count,
)

pytestmark = pytest.mark.unit


class TestScoringTier:
    def test_tier_enum_values(self):
        assert ScoringTier.MINIMAL == "minimal"
        assert ScoringTier.LIMITED == "limited"
        assert ScoringTier.BASIC == "basic"
        assert ScoringTier.INTERMEDIATE == "intermediate"
        assert ScoringTier.ADVANCED == "advanced"
        assert ScoringTier.FULL == "full"

    def test_tier_configurations_exist(self):
        assert ScoringTier.MINIMAL in TIER_CONFIGURATIONS
        assert ScoringTier.LIMITED in TIER_CONFIGURATIONS
        assert ScoringTier.BASIC in TIER_CONFIGURATIONS
        assert ScoringTier.INTERMEDIATE in TIER_CONFIGURATIONS
        assert ScoringTier.ADVANCED in TIER_CONFIGURATIONS
        assert ScoringTier.FULL in TIER_CONFIGURATIONS


class TestTierThresholds:
    def test_minimal_tier_configuration(self):
        config = TIER_CONFIGURATIONS[ScoringTier.MINIMAL]
        assert config.min_notes == 0
        assert config.max_notes == 200
        assert config.scorers == ["BayesianAverageScorer"]
        assert config.requires_full_pipeline is False
        assert config.enable_clustering is False
        assert config.confidence_warnings is True

    def test_limited_tier_configuration(self):
        config = TIER_CONFIGURATIONS[ScoringTier.LIMITED]
        assert config.min_notes == 200
        assert config.max_notes == 1000
        assert config.scorers == ["MFCoreScorer"]
        assert config.confidence_warnings is True

    def test_basic_tier_configuration(self):
        config = TIER_CONFIGURATIONS[ScoringTier.BASIC]
        assert config.min_notes == 1000
        assert config.max_notes == 5000
        assert config.scorers == ["MFCoreScorer"]
        assert config.confidence_warnings is False

    def test_intermediate_tier_configuration(self):
        config = TIER_CONFIGURATIONS[ScoringTier.INTERMEDIATE]
        assert config.min_notes == 5000
        assert config.max_notes == 10000
        assert "MFCoreScorer" in config.scorers
        assert "MFExpansionScorer" in config.scorers

    def test_advanced_tier_configuration(self):
        config = TIER_CONFIGURATIONS[ScoringTier.ADVANCED]
        assert config.min_notes == 10000
        assert config.max_notes == 50000
        assert "MFCoreScorer" in config.scorers
        assert "MFExpansionScorer" in config.scorers
        assert "MFGroupScorer" in config.scorers
        assert "MFExpansionPlusScorer" in config.scorers
        assert config.requires_full_pipeline is True

    def test_full_tier_configuration(self):
        config = TIER_CONFIGURATIONS[ScoringTier.FULL]
        assert config.min_notes == 50000
        assert config.max_notes is None
        assert config.enable_clustering is True


class TestGetTierForNoteCount:
    def test_minimal_tier_selection(self):
        assert get_tier_for_note_count(0) == ScoringTier.MINIMAL
        assert get_tier_for_note_count(50) == ScoringTier.MINIMAL
        assert get_tier_for_note_count(199) == ScoringTier.MINIMAL

    def test_limited_tier_selection(self):
        assert get_tier_for_note_count(200) == ScoringTier.LIMITED
        assert get_tier_for_note_count(500) == ScoringTier.LIMITED
        assert get_tier_for_note_count(999) == ScoringTier.LIMITED

    def test_basic_tier_selection(self):
        assert get_tier_for_note_count(1000) == ScoringTier.BASIC
        assert get_tier_for_note_count(2500) == ScoringTier.BASIC
        assert get_tier_for_note_count(4999) == ScoringTier.BASIC

    def test_intermediate_tier_selection(self):
        assert get_tier_for_note_count(5000) == ScoringTier.INTERMEDIATE
        assert get_tier_for_note_count(7500) == ScoringTier.INTERMEDIATE
        assert get_tier_for_note_count(9999) == ScoringTier.INTERMEDIATE

    def test_advanced_tier_selection(self):
        assert get_tier_for_note_count(10000) == ScoringTier.ADVANCED
        assert get_tier_for_note_count(25000) == ScoringTier.ADVANCED
        assert get_tier_for_note_count(49999) == ScoringTier.ADVANCED

    def test_full_tier_selection(self):
        assert get_tier_for_note_count(50000) == ScoringTier.FULL
        assert get_tier_for_note_count(100000) == ScoringTier.FULL
        assert get_tier_for_note_count(1000000) == ScoringTier.FULL

    def test_edge_case_boundaries(self):
        assert get_tier_for_note_count(200) == ScoringTier.LIMITED
        assert get_tier_for_note_count(1000) == ScoringTier.BASIC
        assert get_tier_for_note_count(5000) == ScoringTier.INTERMEDIATE
        assert get_tier_for_note_count(10000) == ScoringTier.ADVANCED
        assert get_tier_for_note_count(50000) == ScoringTier.FULL


class TestGetTierConfig:
    def test_get_tier_config_returns_correct_config(self):
        config = get_tier_config(ScoringTier.BASIC)
        assert isinstance(config, TierThresholds)
        assert config.min_notes == 1000
        assert config.max_notes == 5000

    def test_get_tier_config_for_all_tiers(self):
        for tier in ScoringTier:
            config = get_tier_config(tier)
            assert isinstance(config, TierThresholds)
            assert config.min_notes >= 0
            assert config.scorers is not None
            assert len(config.scorers) > 0


class TestTierConsistency:
    def test_tier_ranges_are_contiguous(self):
        tiers = [
            ScoringTier.MINIMAL,
            ScoringTier.LIMITED,
            ScoringTier.BASIC,
            ScoringTier.INTERMEDIATE,
            ScoringTier.ADVANCED,
            ScoringTier.FULL,
        ]

        for i in range(len(tiers) - 1):
            current_config = TIER_CONFIGURATIONS[tiers[i]]
            next_config = TIER_CONFIGURATIONS[tiers[i + 1]]

            if current_config.max_notes is not None:
                assert current_config.max_notes == next_config.min_notes

    def test_no_gaps_in_tier_coverage(self):
        for note_count in range(0, 100001, 100):
            tier = get_tier_for_note_count(note_count)
            assert tier is not None
            config = get_tier_config(tier)
            assert config.min_notes <= note_count
            if config.max_notes is not None:
                assert note_count < config.max_notes

    def test_scorer_complexity_increases_with_tier(self):
        minimal_scorers = len(TIER_CONFIGURATIONS[ScoringTier.MINIMAL].scorers)
        basic_scorers = len(TIER_CONFIGURATIONS[ScoringTier.BASIC].scorers)
        advanced_scorers = len(TIER_CONFIGURATIONS[ScoringTier.ADVANCED].scorers)

        assert minimal_scorers <= basic_scorers
        assert basic_scorers <= advanced_scorers
