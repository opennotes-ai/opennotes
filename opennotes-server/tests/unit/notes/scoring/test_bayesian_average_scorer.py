import math

from src.notes.scoring.bayesian_average_scorer import BayesianAverageScorer


class TestBayesianAverageScorerCalculation:
    """
    Unit tests for BayesianAverageScorer score calculation (AC #10).

    Tests the formula: score = (C x m + Σ(ratings)) / (C + n)
    Default parameters: C=2.0, m=0.5, min_ratings_for_confidence=5
    """

    def test_zero_ratings_returns_prior(self):
        """Test that zero ratings returns the prior mean m."""
        scorer = BayesianAverageScorer(confidence_param=2.0, prior_mean=0.5)

        score = scorer.calculate_score([])

        assert score == 0.5
        metadata = scorer.get_score_metadata([])
        assert metadata["no_data"] is True
        assert metadata["confidence_level"] == "provisional"

    def test_single_rating_zero(self):
        """Test score calculation with a single rating of 0.0."""
        scorer = BayesianAverageScorer(confidence_param=2.0, prior_mean=0.5)

        score = scorer.calculate_score([0.0])

        expected = (2.0 * 0.5 + 0.0) / (2.0 + 1)
        assert math.isclose(score, expected, rel_tol=1e-9)
        assert math.isclose(score, 1.0 / 3.0, rel_tol=1e-9)

    def test_single_rating_half(self):
        """Test score calculation with a single rating of 0.5."""
        scorer = BayesianAverageScorer(confidence_param=2.0, prior_mean=0.5)

        score = scorer.calculate_score([0.5])

        expected = (2.0 * 0.5 + 0.5) / (2.0 + 1)
        assert math.isclose(score, expected, rel_tol=1e-9)
        assert math.isclose(score, 0.5, rel_tol=1e-9)

    def test_single_rating_one(self):
        """Test score calculation with a single rating of 1.0."""
        scorer = BayesianAverageScorer(confidence_param=2.0, prior_mean=0.5)

        score = scorer.calculate_score([1.0])

        expected = (2.0 * 0.5 + 1.0) / (2.0 + 1)
        assert math.isclose(score, expected, rel_tol=1e-9)
        assert math.isclose(score, 2.0 / 3.0, rel_tol=1e-9)

    def test_two_ratings_both_zero(self):
        """Test score calculation with two ratings, both 0.0."""
        scorer = BayesianAverageScorer(confidence_param=2.0, prior_mean=0.5)

        score = scorer.calculate_score([0.0, 0.0])

        expected = (2.0 * 0.5 + 0.0) / (2.0 + 2)
        assert math.isclose(score, expected, rel_tol=1e-9)
        assert math.isclose(score, 0.25, rel_tol=1e-9)

    def test_two_ratings_both_one(self):
        """Test score calculation with two ratings, both 1.0."""
        scorer = BayesianAverageScorer(confidence_param=2.0, prior_mean=0.5)

        score = scorer.calculate_score([1.0, 1.0])

        expected = (2.0 * 0.5 + 2.0) / (2.0 + 2)
        assert math.isclose(score, expected, rel_tol=1e-9)
        assert math.isclose(score, 0.75, rel_tol=1e-9)

    def test_two_ratings_mixed(self):
        """Test score calculation with two mixed ratings."""
        scorer = BayesianAverageScorer(confidence_param=2.0, prior_mean=0.5)

        score = scorer.calculate_score([0.25, 0.75])

        expected = (2.0 * 0.5 + 0.25 + 0.75) / (2.0 + 2)
        assert math.isclose(score, expected, rel_tol=1e-9)
        assert math.isclose(score, 0.5, rel_tol=1e-9)

    def test_five_ratings_transition_to_standard_confidence(self):
        """
        Test score calculation with 5 ratings (threshold for standard confidence).
        Verify confidence_level changes from provisional to standard.
        """
        scorer = BayesianAverageScorer(
            confidence_param=2.0,
            prior_mean=0.5,
            min_ratings_for_confidence=5,
        )

        ratings = [0.6, 0.7, 0.8, 0.5, 0.4]
        score = scorer.calculate_score(ratings)

        expected = (2.0 * 0.5 + sum(ratings)) / (2.0 + 5)
        assert math.isclose(score, expected, rel_tol=1e-9)

        metadata = scorer.get_score_metadata(ratings, score)
        assert metadata["confidence_level"] == "standard"
        assert metadata["rating_count"] == 5

    def test_ten_ratings_prior_influence_decreases(self):
        """
        Test score calculation with 10 ratings.
        Verify that prior influence decreases as rating count increases.
        """
        scorer = BayesianAverageScorer(confidence_param=2.0, prior_mean=0.5)

        ratings = [0.8] * 10
        score = scorer.calculate_score(ratings)

        expected = (2.0 * 0.5 + 8.0) / (2.0 + 10)
        assert math.isclose(score, expected, rel_tol=1e-9)
        assert math.isclose(score, 0.75, rel_tol=1e-9)

        avg_rating = sum(ratings) / len(ratings)
        assert score < avg_rating

    def test_different_confidence_params(self):
        """Test score calculation with different confidence parameters."""
        ratings = [0.8, 0.9]

        scorer_low_c = BayesianAverageScorer(confidence_param=1.0, prior_mean=0.5)
        score_low_c = scorer_low_c.calculate_score(ratings)

        scorer_high_c = BayesianAverageScorer(confidence_param=5.0, prior_mean=0.5)
        score_high_c = scorer_high_c.calculate_score(ratings)

        expected_low = (1.0 * 0.5 + 1.7) / (1.0 + 2)
        expected_high = (5.0 * 0.5 + 1.7) / (5.0 + 2)

        assert math.isclose(score_low_c, expected_low, rel_tol=1e-9)
        assert math.isclose(score_high_c, expected_high, rel_tol=1e-9)
        assert score_high_c < score_low_c

    def test_different_prior_means(self):
        """Test score calculation with different prior means."""
        ratings = [0.6]

        scorer_low_m = BayesianAverageScorer(confidence_param=2.0, prior_mean=0.3)
        score_low_m = scorer_low_m.calculate_score(ratings)

        scorer_high_m = BayesianAverageScorer(confidence_param=2.0, prior_mean=0.7)
        score_high_m = scorer_high_m.calculate_score(ratings)

        expected_low = (2.0 * 0.3 + 0.6) / (2.0 + 1)
        expected_high = (2.0 * 0.7 + 0.6) / (2.0 + 1)

        assert math.isclose(score_low_m, expected_low, rel_tol=1e-9)
        assert math.isclose(score_high_m, expected_high, rel_tol=1e-9)
        assert score_low_m < score_high_m

    def test_all_zeros_ratings(self):
        """Test score calculation with all zero ratings."""
        scorer = BayesianAverageScorer(confidence_param=2.0, prior_mean=0.5)

        score = scorer.calculate_score([0.0, 0.0, 0.0, 0.0, 0.0])

        expected = (2.0 * 0.5) / (2.0 + 5)
        assert math.isclose(score, expected, rel_tol=1e-9)

    def test_all_ones_ratings(self):
        """Test score calculation with all 1.0 ratings."""
        scorer = BayesianAverageScorer(confidence_param=2.0, prior_mean=0.5)

        score = scorer.calculate_score([1.0, 1.0, 1.0, 1.0, 1.0])

        expected = (2.0 * 0.5 + 5.0) / (2.0 + 5)
        assert math.isclose(score, expected, rel_tol=1e-9)

    def test_mixed_edge_values(self):
        """Test score calculation with mixed edge values (0.0 and 1.0)."""
        scorer = BayesianAverageScorer(confidence_param=2.0, prior_mean=0.5)

        score = scorer.calculate_score([0.0, 1.0, 0.0, 1.0])

        expected = (2.0 * 0.5 + 2.0) / (2.0 + 4)
        assert math.isclose(score, expected, rel_tol=1e-9)
        assert math.isclose(score, 0.5, rel_tol=1e-9)


class TestBayesianAverageScorerEdgeCases:
    """
    Unit tests for BayesianAverageScorer edge cases.
    """

    def test_rating_below_zero_clamped(self):
        """Test that ratings below 0.0 are clamped to 0.0."""
        scorer = BayesianAverageScorer(confidence_param=2.0, prior_mean=0.5)

        score = scorer.calculate_score([-0.5])

        expected = (2.0 * 0.5 + 0.0) / (2.0 + 1)
        assert math.isclose(score, expected, rel_tol=1e-9)

        stats = scorer.get_clamping_statistics()
        assert stats["clamping_count"] == 1

    def test_rating_above_one_clamped(self):
        """Test that ratings above 1.0 are clamped to 1.0."""
        scorer = BayesianAverageScorer(confidence_param=2.0, prior_mean=0.5)

        score = scorer.calculate_score([1.5])

        expected = (2.0 * 0.5 + 1.0) / (2.0 + 1)
        assert math.isclose(score, expected, rel_tol=1e-9)

        stats = scorer.get_clamping_statistics()
        assert stats["clamping_count"] == 1

    def test_multiple_out_of_range_ratings_clamped(self):
        """Test that multiple out-of-range ratings are all clamped."""
        scorer = BayesianAverageScorer(confidence_param=2.0, prior_mean=0.5)

        score = scorer.calculate_score([-1.0, 2.0, -0.5, 1.5])

        expected = (2.0 * 0.5 + 0.0 + 1.0 + 0.0 + 1.0) / (2.0 + 4)
        assert math.isclose(score, expected, rel_tol=1e-9)

        stats = scorer.get_clamping_statistics()
        assert stats["clamping_count"] == 4

    def test_single_outlier_rating(self):
        """Test score calculation with a single outlier rating."""
        scorer = BayesianAverageScorer(confidence_param=2.0, prior_mean=0.5)

        score = scorer.calculate_score([0.5, 0.5, 0.5, 10.0])

        expected = (2.0 * 0.5 + 0.5 + 0.5 + 0.5 + 1.0) / (2.0 + 4)
        assert math.isclose(score, expected, rel_tol=1e-9)

    def test_very_large_rating_count(self):
        """Test score calculation with a very large rating count (1000+)."""
        scorer = BayesianAverageScorer(confidence_param=2.0, prior_mean=0.5)

        ratings = [0.7] * 1000
        score = scorer.calculate_score(ratings)

        expected = (2.0 * 0.5 + 700.0) / (2.0 + 1000)
        assert math.isclose(score, expected, rel_tol=1e-9)
        assert math.isclose(score, 0.699, rel_tol=1e-3)

    def test_none_ratings_handled_as_error(self):
        """Test that None ratings trigger error handling and return prior."""
        scorer = BayesianAverageScorer(confidence_param=2.0, prior_mean=0.5)

        score = scorer.calculate_score(None)

        assert score == 0.5


class TestBayesianAverageScorerPriorUpdate:
    """
    Unit tests for BayesianAverageScorer prior update mechanism (AC #11).
    """

    def test_initial_prior(self):
        """Test that scorer initializes with correct prior mean."""
        scorer = BayesianAverageScorer(confidence_param=2.0, prior_mean=0.5)

        assert scorer.m == 0.5
        assert scorer.C == 2.0

    def test_prior_update_from_system_average(self):
        """Test that prior can be updated from system average."""
        scorer = BayesianAverageScorer(confidence_param=2.0, prior_mean=0.5)

        scorer.update_prior_from_system_average(0.65)

        assert scorer.m == 0.65

    def test_score_changes_after_prior_update(self):
        """Test that scores change after prior is updated."""
        scorer = BayesianAverageScorer(confidence_param=2.0, prior_mean=0.5)
        ratings = [0.6, 0.7]

        score_before = scorer.calculate_score(ratings)

        scorer.update_prior_from_system_average(0.7)

        score_after = scorer.calculate_score(ratings)

        assert score_before != score_after
        assert score_after > score_before

    def test_multiple_prior_updates(self):
        """Test multiple prior updates as system grows."""
        scorer = BayesianAverageScorer(confidence_param=2.0, prior_mean=0.5)

        scorer.update_prior_from_system_average(0.55)
        assert scorer.m == 0.55

        scorer.update_prior_from_system_average(0.60)
        assert scorer.m == 0.60

        scorer.update_prior_from_system_average(0.58)
        assert scorer.m == 0.58

    def test_prior_update_with_low_system_average(self):
        """Test prior update with low system average (0.3)."""
        scorer = BayesianAverageScorer(confidence_param=2.0, prior_mean=0.5)

        scorer.update_prior_from_system_average(0.3)

        assert scorer.m == 0.3

        score = scorer.calculate_score([0.5])
        expected = (2.0 * 0.3 + 0.5) / (2.0 + 1)
        assert math.isclose(score, expected, rel_tol=1e-9)

    def test_prior_update_with_high_system_average(self):
        """Test prior update with high system average (0.7)."""
        scorer = BayesianAverageScorer(confidence_param=2.0, prior_mean=0.5)

        scorer.update_prior_from_system_average(0.7)

        assert scorer.m == 0.7

        score = scorer.calculate_score([0.5])
        expected = (2.0 * 0.7 + 0.5) / (2.0 + 1)
        assert math.isclose(score, expected, rel_tol=1e-9)

    def test_prior_update_clamping_below_zero(self):
        """Test that prior update clamps values below 0.0."""
        scorer = BayesianAverageScorer(confidence_param=2.0, prior_mean=0.5)

        scorer.update_prior_from_system_average(-0.1)

        assert scorer.m == 0.0

    def test_prior_update_clamping_above_one(self):
        """Test that prior update clamps values above 1.0."""
        scorer = BayesianAverageScorer(confidence_param=2.0, prior_mean=0.5)

        scorer.update_prior_from_system_average(1.2)

        assert scorer.m == 1.0

    def test_prior_update_affects_zero_rating_case(self):
        """Test that prior update affects the zero-rating case."""
        scorer = BayesianAverageScorer(confidence_param=2.0, prior_mean=0.5)

        score_before = scorer.calculate_score([])
        assert score_before == 0.5

        scorer.update_prior_from_system_average(0.65)

        score_after = scorer.calculate_score([])
        assert score_after == 0.65


class TestBayesianAverageScorerMetadata:
    """
    Unit tests for BayesianAverageScorer metadata generation.
    """

    def test_metadata_structure(self):
        """Test that metadata has correct structure."""
        scorer = BayesianAverageScorer(confidence_param=2.0, prior_mean=0.5)

        metadata = scorer.get_score_metadata([0.6, 0.7])

        assert "algorithm" in metadata
        assert metadata["algorithm"] == "bayesian_average_tier0"
        assert "confidence_level" in metadata
        assert "rating_count" in metadata
        assert "prior_values" in metadata
        assert metadata["prior_values"]["C"] == 2.0
        assert metadata["prior_values"]["m"] == 0.5

    def test_metadata_no_data_flag(self):
        """Test that no_data flag is set for zero ratings."""
        scorer = BayesianAverageScorer(confidence_param=2.0, prior_mean=0.5)

        metadata = scorer.get_score_metadata([])

        assert metadata["no_data"] is True

    def test_metadata_no_data_flag_absent_with_ratings(self):
        """Test that no_data flag is absent when ratings exist."""
        scorer = BayesianAverageScorer(confidence_param=2.0, prior_mean=0.5)

        metadata = scorer.get_score_metadata([0.5])

        assert "no_data" not in metadata

    def test_metadata_confidence_level_provisional(self):
        """Test that confidence_level is 'provisional' for low rating counts."""
        scorer = BayesianAverageScorer(
            confidence_param=2.0,
            prior_mean=0.5,
            min_ratings_for_confidence=5,
        )

        metadata = scorer.get_score_metadata([0.5, 0.6, 0.7])

        assert metadata["confidence_level"] == "provisional"

    def test_metadata_confidence_level_standard(self):
        """Test that confidence_level is 'standard' for adequate rating counts."""
        scorer = BayesianAverageScorer(
            confidence_param=2.0,
            prior_mean=0.5,
            min_ratings_for_confidence=5,
        )

        metadata = scorer.get_score_metadata([0.5, 0.6, 0.7, 0.8, 0.9])

        assert metadata["confidence_level"] == "standard"

    def test_metadata_includes_clamping_count(self):
        """Test that metadata includes clamping count when clamping occurs."""
        scorer = BayesianAverageScorer(confidence_param=2.0, prior_mean=0.5)

        scorer.calculate_score([-0.5, 1.5])
        metadata = scorer.get_score_metadata([-0.5, 1.5])

        assert "clamped_ratings" in metadata
        assert metadata["clamped_ratings"] >= 2

    def test_metadata_no_clamping_count_when_none(self):
        """Test that clamping count is absent when no clamping occurs."""
        scorer = BayesianAverageScorer(confidence_param=2.0, prior_mean=0.5)

        metadata = scorer.get_score_metadata([0.5, 0.6])

        assert "clamped_ratings" not in metadata


class TestBayesianAverageScorerStatistics:
    """
    Unit tests for BayesianAverageScorer statistics tracking.
    """

    def test_statistics_initial_state(self):
        """Test that statistics start at zero."""
        scorer = BayesianAverageScorer(confidence_param=2.0, prior_mean=0.5)

        stats = scorer.get_clamping_statistics()

        assert stats["clamping_count"] == 0
        assert stats["zero_rating_count"] == 0

    def test_statistics_zero_rating_count(self):
        """Test that zero_rating_count increments correctly."""
        scorer = BayesianAverageScorer(confidence_param=2.0, prior_mean=0.5)

        scorer.calculate_score([])
        scorer.calculate_score([])

        stats = scorer.get_clamping_statistics()
        assert stats["zero_rating_count"] == 2

    def test_statistics_reset(self):
        """Test that statistics can be reset."""
        scorer = BayesianAverageScorer(confidence_param=2.0, prior_mean=0.5)

        scorer.calculate_score([])
        scorer.calculate_score([-1.0, 2.0])

        stats_before = scorer.get_clamping_statistics()
        assert stats_before["zero_rating_count"] > 0
        assert stats_before["clamping_count"] > 0

        scorer.reset_statistics()

        stats_after = scorer.get_clamping_statistics()
        assert stats_after["zero_rating_count"] == 0
        assert stats_after["clamping_count"] == 0
