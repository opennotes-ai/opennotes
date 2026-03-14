from src.notes.scoring.bayesian_scorer_adapter import BayesianAverageScorerAdapter
from src.notes.scoring.mf_scorer_adapter import MFCoreScorerAdapter
from src.notes.scoring.scorer_factory import ScorerFactory, clear_tier_failures, record_tier_failure
from src.notes.scoring.tier_config import ScoringTier


class TestTierDowngradeTracking:
    def setup_method(self):
        clear_tier_failures()

    def test_no_failure_recorded_uses_note_count_tier(self):
        factory = ScorerFactory()
        scorer = factory.get_scorer("community-1", note_count=500)
        assert isinstance(scorer, MFCoreScorerAdapter)

    def test_recorded_failure_caps_tier_to_minimal(self):
        record_tier_failure("community-1", ScoringTier.LIMITED)
        factory = ScorerFactory()
        scorer = factory.get_scorer("community-1", note_count=500)
        assert isinstance(scorer, BayesianAverageScorerAdapter)

    def test_recorded_failure_at_basic_allows_limited(self):
        record_tier_failure("community-1", ScoringTier.BASIC)
        factory = ScorerFactory()
        scorer = factory.get_scorer(
            "community-1",
            note_count=500,
        )
        assert isinstance(scorer, MFCoreScorerAdapter)

    def test_tier_override_ignores_failure_tracking(self):
        record_tier_failure("community-1", ScoringTier.LIMITED)
        factory = ScorerFactory()
        scorer = factory.get_scorer(
            "community-1",
            note_count=500,
            tier_override=ScoringTier.LIMITED,
        )
        assert isinstance(scorer, MFCoreScorerAdapter)

    def test_different_community_not_affected(self):
        record_tier_failure("community-1", ScoringTier.LIMITED)
        factory = ScorerFactory()
        scorer = factory.get_scorer("community-2", note_count=500)
        assert isinstance(scorer, MFCoreScorerAdapter)

    def test_clear_failures_allows_promotion_again(self):
        record_tier_failure("community-1", ScoringTier.LIMITED)
        clear_tier_failures("community-1")
        factory = ScorerFactory()
        scorer = factory.get_scorer("community-1", note_count=500)
        assert isinstance(scorer, MFCoreScorerAdapter)

    def test_density_recovery_clears_failure(self):
        record_tier_failure("community-1", ScoringTier.LIMITED)
        factory = ScorerFactory()
        scorer = factory.get_scorer(
            "community-1",
            note_count=500,
            ratings_density={"avg_raters_per_note": 8.0, "avg_ratings_per_rater": 15.0},
        )
        assert isinstance(scorer, MFCoreScorerAdapter)

    def test_density_recovery_does_not_clear_if_density_insufficient(self):
        record_tier_failure("community-1", ScoringTier.LIMITED)
        factory = ScorerFactory()
        scorer = factory.get_scorer(
            "community-1",
            note_count=500,
            ratings_density={"avg_raters_per_note": 2.0, "avg_ratings_per_rater": 3.0},
        )
        assert isinstance(scorer, BayesianAverageScorerAdapter)


class TestRecordTierFailureLogging:
    def setup_method(self):
        clear_tier_failures()

    def test_record_failure_stores_tier(self, caplog):
        import logging

        with caplog.at_level(logging.WARNING):
            record_tier_failure("community-1", ScoringTier.LIMITED, reason="AssertionError: empty")
        assert "Downgrading max viable tier" in caplog.text
        assert any(
            r.community_server_id == "community-1"
            for r in caplog.records
            if hasattr(r, "community_server_id")
        )

    def test_multiple_failures_keep_lowest_tier(self):
        record_tier_failure("community-1", ScoringTier.BASIC)
        record_tier_failure("community-1", ScoringTier.LIMITED)
        factory = ScorerFactory()
        scorer = factory.get_scorer("community-1", note_count=500)
        assert isinstance(scorer, BayesianAverageScorerAdapter)
