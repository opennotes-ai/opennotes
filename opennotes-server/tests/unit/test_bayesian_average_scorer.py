import pytest

from src.notes.scoring import BayesianAverageScorer

pytestmark = pytest.mark.unit


class TestBayesianAverageScorerInitialization:
    def test_default_initialization(self):
        scorer = BayesianAverageScorer()
        assert scorer.C == 2.0
        assert scorer.m == 0.5
        assert scorer.min_ratings_for_confidence == 5

    def test_custom_initialization(self):
        scorer = BayesianAverageScorer(
            confidence_param=3.0,
            prior_mean=0.6,
            min_ratings_for_confidence=10,
        )
        assert scorer.C == 3.0
        assert scorer.m == 0.6
        assert scorer.min_ratings_for_confidence == 10


class TestBayesianAverageScorerCalculation:
    def test_calculate_score_no_ratings(self):
        scorer = BayesianAverageScorer()
        score = scorer.calculate_score([])
        assert score == 0.5

    def test_calculate_score_single_perfect_rating(self):
        scorer = BayesianAverageScorer(confidence_param=2.0, prior_mean=0.5)
        score = scorer.calculate_score([1.0])
        expected = (2.0 * 0.5 + 1.0) / (2.0 + 1)
        assert abs(score - expected) < 0.001
        assert abs(score - 0.667) < 0.01

    def test_calculate_score_two_perfect_ratings(self):
        scorer = BayesianAverageScorer(confidence_param=2.0, prior_mean=0.5)
        score = scorer.calculate_score([1.0, 1.0])
        expected = (2.0 * 0.5 + 2.0) / (2.0 + 2)
        assert abs(score - expected) < 0.001
        assert abs(score - 0.75) < 0.01

    def test_calculate_score_three_ratings_avg_08(self):
        scorer = BayesianAverageScorer(confidence_param=2.0, prior_mean=0.5)
        ratings = [0.8, 0.8, 0.8]
        score = scorer.calculate_score(ratings)
        expected = (2.0 * 0.5 + 2.4) / (2.0 + 3)
        assert abs(score - expected) < 0.001
        assert abs(score - 0.68) < 0.01

    def test_calculate_score_five_ratings_avg_08(self):
        scorer = BayesianAverageScorer(confidence_param=2.0, prior_mean=0.5)
        ratings = [0.8, 0.8, 0.8, 0.8, 0.8]
        score = scorer.calculate_score(ratings)
        expected = (2.0 * 0.5 + 4.0) / (2.0 + 5)
        assert abs(score - expected) < 0.001
        assert abs(score - 0.714) < 0.01

    def test_calculate_score_converges_to_ratings(self):
        scorer = BayesianAverageScorer(confidence_param=2.0, prior_mean=0.5)
        ratings = [0.9] * 100
        score = scorer.calculate_score(ratings)
        assert abs(score - 0.9) < 0.02

    def test_calculate_score_zero_ratings(self):
        scorer = BayesianAverageScorer(confidence_param=2.0, prior_mean=0.5)
        ratings = [0.0, 0.0, 0.0]
        score = scorer.calculate_score(ratings)
        expected = (2.0 * 0.5) / (2.0 + 3)
        assert abs(score - expected) < 0.001
        assert score < 0.5

    def test_calculate_score_mixed_ratings(self):
        scorer = BayesianAverageScorer(confidence_param=2.0, prior_mean=0.5)
        ratings = [0.0, 0.5, 1.0]
        score = scorer.calculate_score(ratings)
        expected = (2.0 * 0.5 + 1.5) / (2.0 + 3)
        assert abs(score - expected) < 0.001


class TestRatingClamping:
    def test_clamp_rating_above_one(self):
        scorer = BayesianAverageScorer()
        score = scorer.calculate_score([1.5])
        expected = (2.0 * 0.5 + 1.0) / (2.0 + 1)
        assert abs(score - expected) < 0.001

    def test_clamp_rating_below_zero(self):
        scorer = BayesianAverageScorer()
        score = scorer.calculate_score([-0.5])
        expected = (2.0 * 0.5 + 0.0) / (2.0 + 1)
        assert abs(score - expected) < 0.001

    def test_clamp_multiple_invalid_ratings(self):
        scorer = BayesianAverageScorer()
        score = scorer.calculate_score([1.5, -0.5, 2.0])
        expected = (2.0 * 0.5 + 2.0) / (2.0 + 3)
        assert abs(score - expected) < 0.001

    def test_clamping_statistics(self):
        scorer = BayesianAverageScorer()
        scorer.calculate_score([1.5, -0.5, 0.5])
        stats = scorer.get_clamping_statistics()
        assert stats["clamping_count"] == 2


class TestScoreMetadata:
    def test_metadata_no_ratings(self):
        scorer = BayesianAverageScorer()
        metadata = scorer.get_score_metadata([])
        assert metadata["algorithm"] == "bayesian_average_tier0"
        assert metadata["confidence_level"] == "provisional"
        assert metadata["rating_count"] == 0
        assert metadata["no_data"] is True
        assert metadata["prior_values"] == {"C": 2.0, "m": 0.5}

    def test_metadata_provisional_confidence(self):
        scorer = BayesianAverageScorer(min_ratings_for_confidence=5)
        metadata = scorer.get_score_metadata([0.8, 0.9, 0.7])
        assert metadata["confidence_level"] == "provisional"
        assert metadata["rating_count"] == 3
        assert "no_data" not in metadata

    def test_metadata_standard_confidence(self):
        scorer = BayesianAverageScorer(min_ratings_for_confidence=5)
        metadata = scorer.get_score_metadata([0.8] * 5)
        assert metadata["confidence_level"] == "standard"
        assert metadata["rating_count"] == 5

    def test_metadata_includes_prior_values(self):
        scorer = BayesianAverageScorer(confidence_param=3.0, prior_mean=0.6)
        metadata = scorer.get_score_metadata([0.8])
        assert metadata["prior_values"]["C"] == 3.0
        assert metadata["prior_values"]["m"] == 0.6

    def test_metadata_with_precomputed_score(self):
        scorer = BayesianAverageScorer()
        ratings = [0.8, 0.9]
        score = scorer.calculate_score(ratings)
        metadata = scorer.get_score_metadata(ratings, score=score)
        assert metadata["rating_count"] == 2

    def test_metadata_tracks_clamping(self):
        scorer = BayesianAverageScorer()
        score = scorer.calculate_score([1.5, 0.5])
        metadata = scorer.get_score_metadata([1.5, 0.5], score=score)
        assert metadata["clamped_ratings"] == 1


class TestPriorUpdate:
    def test_update_prior_from_system_average(self):
        scorer = BayesianAverageScorer(prior_mean=0.5)
        scorer.update_prior_from_system_average(0.7)
        assert scorer.m == 0.7

    def test_update_prior_affects_score(self):
        scorer = BayesianAverageScorer(confidence_param=2.0, prior_mean=0.5)
        score_before = scorer.calculate_score([])
        assert score_before == 0.5

        scorer.update_prior_from_system_average(0.7)
        score_after = scorer.calculate_score([])
        assert score_after == 0.7

    def test_update_prior_clamps_invalid_values(self):
        scorer = BayesianAverageScorer()
        scorer.update_prior_from_system_average(1.5)
        assert scorer.m == 1.0

        scorer.update_prior_from_system_average(-0.5)
        assert scorer.m == 0.0

    def test_update_prior_with_existing_ratings(self):
        scorer = BayesianAverageScorer(confidence_param=2.0, prior_mean=0.5)
        ratings = [0.8, 0.9]
        score_before = scorer.calculate_score(ratings)

        scorer.update_prior_from_system_average(0.6)
        score_after = scorer.calculate_score(ratings)

        assert score_after != score_before
        assert score_after > score_before


class TestErrorHandling:
    def test_exception_returns_prior(self):
        scorer = BayesianAverageScorer(prior_mean=0.5)
        score = scorer.calculate_score([])
        assert score == 0.5

    def test_handles_empty_list(self):
        scorer = BayesianAverageScorer()
        score = scorer.calculate_score([])
        assert score == scorer.m

    def test_reset_statistics(self):
        scorer = BayesianAverageScorer()
        scorer.calculate_score([1.5, -0.5])
        scorer.calculate_score([])

        stats_before = scorer.get_clamping_statistics()
        assert stats_before["clamping_count"] > 0
        assert stats_before["zero_rating_count"] > 0

        scorer.reset_statistics()
        stats_after = scorer.get_clamping_statistics()
        assert stats_after["clamping_count"] == 0
        assert stats_after["zero_rating_count"] == 0


class TestEdgeCases:
    def test_large_number_of_ratings(self):
        scorer = BayesianAverageScorer()
        ratings = [0.8] * 1000
        score = scorer.calculate_score(ratings)
        assert abs(score - 0.8) < 0.001

    def test_all_zeros(self):
        scorer = BayesianAverageScorer(confidence_param=2.0, prior_mean=0.5)
        ratings = [0.0] * 10
        score = scorer.calculate_score(ratings)
        expected = (2.0 * 0.5) / (2.0 + 10)
        assert abs(score - expected) < 0.001

    def test_all_ones(self):
        scorer = BayesianAverageScorer(confidence_param=2.0, prior_mean=0.5)
        ratings = [1.0] * 10
        score = scorer.calculate_score(ratings)
        expected = (2.0 * 0.5 + 10.0) / (2.0 + 10)
        assert abs(score - expected) < 0.001

    def test_alternating_ratings(self):
        scorer = BayesianAverageScorer()
        ratings = [0.0, 1.0] * 5
        score = scorer.calculate_score(ratings)
        assert 0.4 < score < 0.6

    def test_very_high_confidence_param(self):
        scorer = BayesianAverageScorer(confidence_param=100.0, prior_mean=0.5)
        ratings = [1.0] * 5
        score = scorer.calculate_score(ratings)
        assert abs(score - 0.5) < 0.1

    def test_very_low_confidence_param(self):
        scorer = BayesianAverageScorer(confidence_param=0.1, prior_mean=0.5)
        ratings = [1.0] * 5
        score = scorer.calculate_score(ratings)
        assert abs(score - 1.0) < 0.1


class TestBayesianFormula:
    def test_formula_correctness(self):
        c = 2.0
        m = 0.5
        ratings = [0.8, 0.9, 0.7]
        n = len(ratings)
        ratings_sum = sum(ratings)

        expected = (c * m + ratings_sum) / (c + n)

        scorer = BayesianAverageScorer(confidence_param=c, prior_mean=m)
        actual = scorer.calculate_score(ratings)

        assert abs(actual - expected) < 0.0001

    def test_formula_with_custom_params(self):
        c = 5.0
        m = 0.3
        ratings = [0.6, 0.7, 0.8, 0.9]
        n = len(ratings)
        ratings_sum = sum(ratings)

        expected = (c * m + ratings_sum) / (c + n)

        scorer = BayesianAverageScorer(confidence_param=c, prior_mean=m)
        actual = scorer.calculate_score(ratings)

        assert abs(actual - expected) < 0.0001


class TestIntegrationWithConfig:
    def test_scorer_uses_default_config_values(self):
        scorer = BayesianAverageScorer()
        assert scorer.C == 2.0
        assert scorer.m == 0.5
        assert scorer.min_ratings_for_confidence == 5

    def test_scorer_accepts_custom_config(self):
        scorer = BayesianAverageScorer(
            confidence_param=3.0,
            prior_mean=0.6,
            min_ratings_for_confidence=10,
        )
        assert scorer.C == 3.0
        assert scorer.m == 0.6
        assert scorer.min_ratings_for_confidence == 10
