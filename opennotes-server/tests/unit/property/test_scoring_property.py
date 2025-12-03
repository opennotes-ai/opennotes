"""
Property-based tests for scoring algorithms using Hypothesis.

These tests verify mathematical invariants and properties that must hold
for all possible inputs. They catch edge cases like:
- Score values outside valid ranges
- Non-monotonic behavior
- Incorrect convergence properties
- Division by zero or overflow errors
"""

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from src.notes.scoring.bayesian_average_scorer import BayesianAverageScorer


class TestBayesianAverageScorerProperties:
    """Property-based tests for BayesianAverageScorer invariants."""

    @given(
        ratings=st.lists(
            st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
            min_size=0,
            max_size=100,
        ),
        confidence_param=st.floats(
            min_value=0.1, max_value=10.0, allow_nan=False, allow_infinity=False
        ),
        prior_mean=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    )
    def test_score_always_in_valid_range(self, ratings, confidence_param, prior_mean):
        """Score must always be in [0.0, 1.0] range regardless of inputs."""
        scorer = BayesianAverageScorer(
            confidence_param=confidence_param,
            prior_mean=prior_mean,
        )

        score = scorer.calculate_score(ratings)

        assert 0.0 <= score <= 1.0, f"Score {score} outside valid range [0.0, 1.0]"

    @given(
        confidence_param=st.floats(
            min_value=0.1, max_value=10.0, allow_nan=False, allow_infinity=False
        ),
        prior_mean=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    )
    def test_empty_ratings_returns_prior_mean(self, confidence_param, prior_mean):
        """With no ratings, score should equal prior mean."""
        scorer = BayesianAverageScorer(
            confidence_param=confidence_param,
            prior_mean=prior_mean,
        )

        score = scorer.calculate_score([])

        assert score == prior_mean, (
            f"Empty ratings should return prior mean {prior_mean}, got {score}"
        )

    @given(
        ratings=st.lists(
            st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
            min_size=1,
            max_size=50,
        ),
        confidence_param=st.floats(
            min_value=0.1, max_value=10.0, allow_nan=False, allow_infinity=False
        ),
        prior_mean=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    )
    def test_score_is_deterministic(self, ratings, confidence_param, prior_mean):
        """Same inputs should always produce same score."""
        scorer = BayesianAverageScorer(
            confidence_param=confidence_param,
            prior_mean=prior_mean,
        )

        score1 = scorer.calculate_score(ratings.copy())
        score2 = scorer.calculate_score(ratings.copy())

        assert score1 == score2, "calculate_score() not deterministic"

    @given(
        ratings=st.lists(
            st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
            min_size=20,
            max_size=100,
        ),
        confidence_param=st.floats(
            min_value=0.1, max_value=5.0, allow_nan=False, allow_infinity=False
        ),
        prior_mean=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    )
    def test_score_converges_to_average_with_many_ratings(
        self, ratings, confidence_param, prior_mean
    ):
        """With many ratings, score should approach the ratings average.

        As n → ∞, (C*m + sum(ratings))/(C + n) → sum(ratings)/n
        With n >= 20 and C <= 5, we have n >= 4*C, so the score should be
        closer to the average than to the prior.
        """
        scorer = BayesianAverageScorer(
            confidence_param=confidence_param,
            prior_mean=prior_mean,
        )

        score = scorer.calculate_score(ratings)
        ratings_average = sum(ratings) / len(ratings)

        assert abs(score - ratings_average) <= abs(prior_mean - ratings_average), (
            f"With many ratings (n={len(ratings)} >= 4*C={4 * confidence_param}), "
            f"score should be closer to average than prior. "
            f"Score: {score}, Average: {ratings_average}, Prior: {prior_mean}"
        )

    @given(
        ratings=st.lists(
            st.floats(min_value=-100.0, max_value=100.0, allow_nan=False, allow_infinity=False),
            min_size=1,
            max_size=50,
        ),
    )
    def test_out_of_range_ratings_are_clamped(self, ratings):
        """Ratings outside [0.0, 1.0] should be clamped, score still valid."""
        assume(any(r < 0.0 or r > 1.0 for r in ratings))

        scorer = BayesianAverageScorer()
        score = scorer.calculate_score(ratings)

        assert 0.0 <= score <= 1.0, f"Score {score} outside valid range even after clamping"

    @given(
        prior_mean=st.floats(min_value=0.01, max_value=0.99, allow_nan=False, allow_infinity=False),
    )
    def test_single_rating_pulls_score_toward_rating(self, prior_mean):
        """A single high rating should pull score above prior, low rating below.

        Using prior_mean in [0.01, 0.99] to avoid boundary cases where
        the score cannot move further (e.g., 0.0 cannot go lower).
        """
        scorer = BayesianAverageScorer(prior_mean=prior_mean, confidence_param=2.0)

        high_score = scorer.calculate_score([1.0])
        low_score = scorer.calculate_score([0.0])

        assert high_score > prior_mean, "High rating should pull score above prior"
        assert low_score < prior_mean, "Low rating should pull score below prior"

    @given(
        ratings=st.lists(
            st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
            min_size=1,
            max_size=50,
        ),
        confidence_param=st.floats(
            min_value=0.1, max_value=10.0, allow_nan=False, allow_infinity=False
        ),
        prior_mean=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    )
    def test_adding_rating_changes_score(self, ratings, confidence_param, prior_mean):
        """Adding a new rating should change the score (unless it equals current score)."""
        scorer = BayesianAverageScorer(
            confidence_param=confidence_param,
            prior_mean=prior_mean,
        )

        initial_score = scorer.calculate_score(ratings)

        new_rating = 0.8
        assume(abs(new_rating - initial_score) > 0.01)

        extended_ratings = [*ratings, new_rating]
        new_score = scorer.calculate_score(extended_ratings)

        assert new_score != initial_score, "Adding rating should change score"

    @given(
        confidence_param=st.floats(
            min_value=0.1, max_value=10.0, allow_nan=False, allow_infinity=False
        ),
        prior_mean=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    )
    def test_higher_confidence_param_pulls_closer_to_prior(self, confidence_param, prior_mean):
        """Higher C should make score closer to prior mean with few ratings."""
        low_c_scorer = BayesianAverageScorer(confidence_param=1.0, prior_mean=prior_mean)
        high_c_scorer = BayesianAverageScorer(confidence_param=10.0, prior_mean=prior_mean)

        ratings = [1.0] if prior_mean < 0.5 else [0.0]

        low_c_score = low_c_scorer.calculate_score(ratings)
        high_c_score = high_c_scorer.calculate_score(ratings)

        assert abs(high_c_score - prior_mean) < abs(low_c_score - prior_mean), (
            f"Higher C should pull closer to prior. "
            f"Low C score: {low_c_score}, High C score: {high_c_score}, Prior: {prior_mean}"
        )

    @given(
        system_average=st.floats(
            min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False
        ),
    )
    def test_update_prior_from_system_average(self, system_average):
        """Updating prior from system average should set new prior correctly."""
        scorer = BayesianAverageScorer(prior_mean=0.5)

        scorer.update_prior_from_system_average(system_average)

        assert scorer.m == system_average, (
            f"Prior not updated correctly: {scorer.m} != {system_average}"
        )
        assert 0.0 <= scorer.m <= 1.0, "Updated prior outside valid range"

    @given(
        system_average=st.floats(
            min_value=-100.0, max_value=100.0, allow_nan=False, allow_infinity=False
        ),
    )
    def test_update_prior_clamps_invalid_system_average(self, system_average):
        """System average outside [0.0, 1.0] should be clamped."""
        scorer = BayesianAverageScorer(prior_mean=0.5)

        scorer.update_prior_from_system_average(system_average)

        assert 0.0 <= scorer.m <= 1.0, f"Prior {scorer.m} not clamped to valid range"

    @given(
        ratings=st.lists(
            st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
            min_size=0,
            max_size=50,
        ),
        confidence_param=st.floats(
            min_value=0.1, max_value=10.0, allow_nan=False, allow_infinity=False
        ),
        prior_mean=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    )
    def test_get_score_metadata_matches_calculate_score(
        self, ratings, confidence_param, prior_mean
    ):
        """Metadata should contain correct rating count and algorithm info."""
        scorer = BayesianAverageScorer(
            confidence_param=confidence_param,
            prior_mean=prior_mean,
        )

        score = scorer.calculate_score(ratings)
        metadata = scorer.get_score_metadata(ratings, score=score)

        assert metadata["algorithm"] == "bayesian_average_tier0"
        assert metadata["rating_count"] == len(ratings)
        assert "confidence_level" in metadata
        assert metadata["prior_values"]["C"] == confidence_param
        assert metadata["prior_values"]["m"] == prior_mean

        if len(ratings) == 0:
            assert metadata.get("no_data") is True

    @given(
        ratings=st.lists(
            st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
            min_size=0,
            max_size=100,
        ),
    )
    def test_score_between_min_and_max_rating(self, ratings):
        """Score should be between min and max rating values (weighted by prior)."""
        if not ratings:
            return

        scorer = BayesianAverageScorer(prior_mean=0.5, confidence_param=2.0)
        score = scorer.calculate_score(ratings)

        min_rating = min(ratings)
        max_rating = max(ratings)
        prior = scorer.m

        overall_min = min(min_rating, prior)
        overall_max = max(max_rating, prior)

        assert overall_min <= score <= overall_max, (
            f"Score {score} not between min {overall_min} and max {overall_max}"
        )


class TestScoringEdgeCases:
    """Test edge cases discovered by Hypothesis."""

    def test_all_zeros(self):
        """All zero ratings should produce low score."""
        scorer = BayesianAverageScorer()
        score = scorer.calculate_score([0.0, 0.0, 0.0, 0.0])
        assert 0.0 <= score <= 0.5, "All zero ratings should produce low score"

    def test_all_ones(self):
        """All one ratings should produce high score."""
        scorer = BayesianAverageScorer()
        score = scorer.calculate_score([1.0, 1.0, 1.0, 1.0])
        assert 0.5 <= score <= 1.0, "All one ratings should produce high score"

    def test_very_small_confidence_param(self):
        """Very small C should make score close to ratings average."""
        scorer = BayesianAverageScorer(confidence_param=0.01, prior_mean=0.5)
        ratings = [0.9, 0.9, 0.9]
        score = scorer.calculate_score(ratings)
        average = sum(ratings) / len(ratings)

        assert abs(score - average) < 0.05, "Small C should produce score close to average"

    def test_very_large_confidence_param(self):
        """Very large C should make score close to prior with few ratings."""
        scorer = BayesianAverageScorer(confidence_param=100.0, prior_mean=0.5)
        ratings = [0.9, 0.9, 0.9]
        score = scorer.calculate_score(ratings)

        assert abs(score - 0.5) < 0.1, "Large C should keep score close to prior"

    @given(
        ratings=st.lists(
            st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
            min_size=1,
            max_size=1000,
        )
    )
    @settings(max_examples=50)
    def test_performance_with_many_ratings(self, ratings):
        """Scoring should complete quickly even with many ratings."""
        import time

        scorer = BayesianAverageScorer()

        start = time.perf_counter()
        score = scorer.calculate_score(ratings)
        duration = time.perf_counter() - start

        assert duration < 0.1, f"Scoring took too long: {duration}s for {len(ratings)} ratings"
        assert 0.0 <= score <= 1.0

    def test_mixed_extreme_values(self):
        """Mix of 0.0 and 1.0 should produce middle score."""
        scorer = BayesianAverageScorer(prior_mean=0.5, confidence_param=2.0)
        ratings = [0.0, 1.0, 0.0, 1.0, 0.0, 1.0]
        score = scorer.calculate_score(ratings)

        assert 0.3 <= score <= 0.7, f"Mixed extremes should produce middle score, got {score}"

    def test_single_outlier_doesnt_dominate(self):
        """A single outlier shouldn't dominate many consistent ratings."""
        scorer = BayesianAverageScorer(prior_mean=0.5, confidence_param=2.0)

        consistent_ratings = [0.9] * 20 + [0.0]
        score_with_outlier = scorer.calculate_score(consistent_ratings)

        only_consistent = [0.9] * 20
        score_without_outlier = scorer.calculate_score(only_consistent)

        assert abs(score_with_outlier - score_without_outlier) < 0.1, (
            "Single outlier shouldn't drastically change score"
        )
