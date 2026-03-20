from src.notes.scoring.bayesian_scorer_adapter import BayesianAverageScorerAdapter
from src.notes.scoring.mf_scorer_adapter import MFCoreScorerAdapter
from src.notes.scoring.scorer_factory import (
    MIN_AVG_RATERS_PER_NOTE,
    MIN_AVG_RATINGS_PER_RATER,
    ScorerFactory,
)
from src.notes.scoring.tier_config import ScoringTier


class TestDensityConstants:
    def test_min_avg_raters_per_note_matches_filter_ratings(self):
        assert MIN_AVG_RATERS_PER_NOTE == 5

    def test_min_avg_ratings_per_rater_matches_filter_ratings(self):
        assert MIN_AVG_RATINGS_PER_RATER == 10


class TestDensityCheckPromotion:
    def test_sufficient_density_returns_mf_scorer(self):
        factory = ScorerFactory()
        density = {"avg_raters_per_note": 6.0, "avg_ratings_per_rater": 12.0}

        scorer = factory.get_scorer("community-123", note_count=300, ratings_density=density)

        assert isinstance(scorer, MFCoreScorerAdapter)

    def test_insufficient_raters_per_note_stays_minimal(self):
        factory = ScorerFactory()
        density = {"avg_raters_per_note": 3.0, "avg_ratings_per_rater": 15.0}

        scorer = factory.get_scorer("community-123", note_count=300, ratings_density=density)

        assert isinstance(scorer, BayesianAverageScorerAdapter)

    def test_insufficient_ratings_per_rater_stays_minimal(self):
        factory = ScorerFactory()
        density = {"avg_raters_per_note": 8.0, "avg_ratings_per_rater": 5.0}

        scorer = factory.get_scorer("community-123", note_count=300, ratings_density=density)

        assert isinstance(scorer, BayesianAverageScorerAdapter)

    def test_both_insufficient_stays_minimal(self):
        factory = ScorerFactory()
        density = {"avg_raters_per_note": 2.0, "avg_ratings_per_rater": 3.0}

        scorer = factory.get_scorer("community-123", note_count=300, ratings_density=density)

        assert isinstance(scorer, BayesianAverageScorerAdapter)

    def test_no_density_info_uses_note_count_only(self):
        factory = ScorerFactory()

        scorer = factory.get_scorer("community-123", note_count=300, ratings_density=None)

        assert isinstance(scorer, MFCoreScorerAdapter)

    def test_no_density_kwarg_uses_note_count_only(self):
        factory = ScorerFactory()

        scorer = factory.get_scorer("community-123", note_count=300)

        assert isinstance(scorer, MFCoreScorerAdapter)

    def test_minimal_tier_ignores_density(self):
        factory = ScorerFactory()
        density = {"avg_raters_per_note": 0.0, "avg_ratings_per_rater": 0.0}

        scorer = factory.get_scorer("community-123", note_count=50, ratings_density=density)

        assert isinstance(scorer, BayesianAverageScorerAdapter)

    def test_density_at_exact_thresholds_promotes(self):
        factory = ScorerFactory()
        density = {"avg_raters_per_note": 5.0, "avg_ratings_per_rater": 10.0}

        scorer = factory.get_scorer("community-123", note_count=300, ratings_density=density)

        assert isinstance(scorer, MFCoreScorerAdapter)

    def test_density_just_below_raters_threshold_stays_minimal(self):
        factory = ScorerFactory()
        density = {"avg_raters_per_note": 4.99, "avg_ratings_per_rater": 10.0}

        scorer = factory.get_scorer("community-123", note_count=300, ratings_density=density)

        assert isinstance(scorer, BayesianAverageScorerAdapter)

    def test_density_just_below_ratings_threshold_stays_minimal(self):
        factory = ScorerFactory()
        density = {"avg_raters_per_note": 5.0, "avg_ratings_per_rater": 9.99}

        scorer = factory.get_scorer("community-123", note_count=300, ratings_density=density)

        assert isinstance(scorer, BayesianAverageScorerAdapter)

    def test_tier_override_skips_density_check(self):
        factory = ScorerFactory()
        density = {"avg_raters_per_note": 0.0, "avg_ratings_per_rater": 0.0}

        scorer = factory.get_scorer(
            "community-123",
            note_count=300,
            tier_override=ScoringTier.LIMITED,
            ratings_density=density,
        )

        assert isinstance(scorer, MFCoreScorerAdapter)

    def test_density_downgrade_uses_minimal_cache_key(self):
        factory = ScorerFactory()
        density = {"avg_raters_per_note": 2.0, "avg_ratings_per_rater": 3.0}

        factory.get_scorer("community-123", note_count=300, ratings_density=density)

        assert ("community-123", ScoringTier.MINIMAL, False) in factory._cache
        assert ("community-123", ScoringTier.LIMITED, False) not in factory._cache

    def test_missing_density_keys_treated_as_zero(self):
        factory = ScorerFactory()
        density: dict[str, float] = {}

        scorer = factory.get_scorer("community-123", note_count=300, ratings_density=density)

        assert isinstance(scorer, BayesianAverageScorerAdapter)
