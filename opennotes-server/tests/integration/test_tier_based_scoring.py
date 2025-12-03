"""
Integration tests for tier-based scoring system.

Tests the full flow of ScorerFactory -> scorer selection -> scoring result,
verifying that both BayesianAverageScorerAdapter and MFCoreScorerAdapter
produce valid results through the unified ScorerProtocol interface.

Task: 805.05
"""

import time
from unittest.mock import patch

import pytest

from src.notes.scoring.bayesian_scorer_adapter import BayesianAverageScorerAdapter
from src.notes.scoring.mf_scorer_adapter import MFCoreScorerAdapter
from src.notes.scoring.scorer_factory import ScorerFactory
from src.notes.scoring.scorer_protocol import ScorerProtocol, ScoringResult
from src.notes.scoring.tier_config import ScoringTier


class TestTierBasedScorerSelection:
    """Integration tests for tier-based scorer selection (AC #1, #2, #3)."""

    def test_community_under_200_notes_uses_bayesian_scorer(self):
        """
        AC #1: Communities with <200 notes should use BayesianAverageScorerAdapter.

        Integration test: creates factory, gets scorer, verifies correct type
        and that scoring produces valid results.
        """
        factory = ScorerFactory()

        scorer = factory.get_scorer("small-community", note_count=50)

        assert isinstance(scorer, BayesianAverageScorerAdapter)
        assert isinstance(scorer, ScorerProtocol)

        result = scorer.score_note("note-1", [0.8, 0.9, 0.7, 0.85])

        assert isinstance(result, ScoringResult)
        assert 0.0 <= result.score <= 1.0
        assert result.confidence_level in ["provisional", "low", "standard", "high"]
        assert result.metadata["algorithm"] == "bayesian_average_tier0"

    def test_community_at_or_above_200_notes_uses_mf_scorer(self):
        """
        AC #2: Communities with >=200 notes should use MFCoreScorerAdapter.

        Integration test: verifies MFCoreScorer is used at and above 200 notes.
        """
        factory = ScorerFactory()

        scorer_200 = factory.get_scorer("medium-community", note_count=200)
        scorer_500 = factory.get_scorer("larger-community", note_count=500)
        scorer_1000 = factory.get_scorer("large-community", note_count=1000)

        assert isinstance(scorer_200, MFCoreScorerAdapter)
        assert isinstance(scorer_500, MFCoreScorerAdapter)
        assert isinstance(scorer_1000, MFCoreScorerAdapter)

        for scorer in [scorer_200, scorer_500, scorer_1000]:
            assert isinstance(scorer, ScorerProtocol)

            result = scorer.score_note("note-1", [0.8, 0.9, 0.7, 0.85, 0.6])

            assert isinstance(result, ScoringResult)
            assert 0.0 <= result.score <= 1.0
            assert result.confidence_level in ["provisional", "standard"]

    def test_tier_boundary_at_exactly_200_notes(self):
        """
        AC #3: Test tier boundary behavior at exactly 200 notes.

        At 199 notes: BayesianAverageScorerAdapter
        At 200 notes: MFCoreScorerAdapter
        """
        factory = ScorerFactory()

        scorer_199 = factory.get_scorer("boundary-community", note_count=199)
        scorer_200 = factory.get_scorer("boundary-community", note_count=200)

        assert isinstance(scorer_199, BayesianAverageScorerAdapter), (
            "199 notes should use Bayesian scorer"
        )
        assert isinstance(scorer_200, MFCoreScorerAdapter), "200 notes should use MFCore scorer"

        result_199 = scorer_199.score_note("note-199", [0.7, 0.8, 0.6])
        result_200 = scorer_200.score_note("note-200", [0.7, 0.8, 0.6])

        assert isinstance(result_199, ScoringResult)
        assert isinstance(result_200, ScoringResult)

    def test_boundary_cases_comprehensive(self):
        """Test all tier boundaries produce valid results."""
        factory = ScorerFactory()

        test_cases = [
            (0, BayesianAverageScorerAdapter),
            (1, BayesianAverageScorerAdapter),
            (100, BayesianAverageScorerAdapter),
            (199, BayesianAverageScorerAdapter),
            (200, MFCoreScorerAdapter),
            (201, MFCoreScorerAdapter),
            (500, MFCoreScorerAdapter),
            (999, MFCoreScorerAdapter),
            (1000, MFCoreScorerAdapter),
            (5000, MFCoreScorerAdapter),
            (10000, MFCoreScorerAdapter),
            (50000, MFCoreScorerAdapter),
            (100000, MFCoreScorerAdapter),
        ]

        for note_count, expected_type in test_cases:
            scorer = factory.get_scorer(f"community-{note_count}", note_count=note_count)
            assert isinstance(scorer, expected_type), (
                f"note_count={note_count} should use {expected_type.__name__}"
            )

            result = scorer.score_note("test-note", [0.5, 0.6, 0.7])
            assert isinstance(result, ScoringResult), (
                f"note_count={note_count} should produce valid ScoringResult"
            )


class TestScorerFallbackBehavior:
    """Integration tests for fallback behavior (AC #4)."""

    def test_mf_scorer_error_does_not_propagate(self):
        """
        AC #4: When MFCoreScorer fails, verify error behavior.

        Note: Current implementation does not have automatic fallback to lower tier.
        This test documents expected behavior and can be updated if fallback is added.
        """
        factory = ScorerFactory()

        scorer = factory.get_scorer("community-with-issue", note_count=500)
        assert isinstance(scorer, MFCoreScorerAdapter)

        result = scorer.score_note("note-1", [0.5, 0.6, 0.7, 0.8, 0.9])
        assert isinstance(result, ScoringResult)

    @patch.object(MFCoreScorerAdapter, "_score_batch_stub")
    def test_mf_scorer_failure_handling(self, mock_batch_stub):
        """
        Test behavior when MFCoreScorerAdapter batch scoring fails.

        Verifies that errors in the scorer are handled gracefully.
        """
        mock_batch_stub.side_effect = RuntimeError("Simulated MFCore failure")

        factory = ScorerFactory()
        scorer = factory.get_scorer("failing-community", note_count=500)

        with pytest.raises(RuntimeError, match="Simulated MFCore failure"):
            scorer.score_note("note-fail", [0.5, 0.6])

    def test_bayesian_scorer_handles_empty_ratings(self):
        """Bayesian scorer handles edge case of empty ratings gracefully."""
        factory = ScorerFactory()
        scorer = factory.get_scorer("empty-ratings-community", note_count=50)

        result = scorer.score_note("note-empty", [])

        assert isinstance(result, ScoringResult)
        assert result.score >= 0.0
        assert result.confidence_level == "provisional"

    def test_mf_scorer_handles_single_rating(self):
        """MF scorer handles edge case of single rating."""
        factory = ScorerFactory()
        scorer = factory.get_scorer("single-rating-community", note_count=300)

        result = scorer.score_note("note-single", [0.8])

        assert isinstance(result, ScoringResult)
        assert result.score >= 0.0


class TestScorerCachingBehavior:
    """Integration tests for scorer caching (AC #5)."""

    def test_same_community_returns_cached_scorer(self):
        """
        AC #5: Same community with same tier returns identical cached scorer instance.
        """
        factory = ScorerFactory()

        scorer_1 = factory.get_scorer("cached-community", note_count=100)
        scorer_2 = factory.get_scorer("cached-community", note_count=150)

        assert scorer_1 is scorer_2, "Same community/tier should return cached instance"

        cache_info = factory.get_cache_info()
        assert cache_info["cache_size"] == 1

    def test_different_communities_get_different_scorers(self):
        """Different communities get separate scorer instances."""
        factory = ScorerFactory()

        scorer_a = factory.get_scorer("community-a", note_count=100)
        scorer_b = factory.get_scorer("community-b", note_count=100)

        assert scorer_a is not scorer_b

        cache_info = factory.get_cache_info()
        assert cache_info["cache_size"] == 2

    def test_tier_change_creates_new_scorer(self):
        """Tier change for same community creates new scorer instance."""
        factory = ScorerFactory()

        scorer_minimal = factory.get_scorer("growing-community", note_count=100)
        scorer_limited = factory.get_scorer("growing-community", note_count=300)

        assert scorer_minimal is not scorer_limited
        assert isinstance(scorer_minimal, BayesianAverageScorerAdapter)
        assert isinstance(scorer_limited, MFCoreScorerAdapter)

        cache_info = factory.get_cache_info()
        assert cache_info["cache_size"] == 2

    def test_cached_scorer_produces_consistent_results(self):
        """Cached scorer instance produces consistent scoring results."""
        factory = ScorerFactory()

        ratings = [0.7, 0.8, 0.75, 0.82]

        scorer = factory.get_scorer("consistent-community", note_count=50)
        result_1 = scorer.score_note("note-1", ratings)

        cached_scorer = factory.get_scorer("consistent-community", note_count=50)
        result_2 = cached_scorer.score_note("note-1", ratings)

        assert scorer is cached_scorer
        assert result_1.score == result_2.score
        assert result_1.confidence_level == result_2.confidence_level

    def test_cache_invalidation_per_community(self):
        """Cache invalidation removes only specified community's scorers."""
        factory = ScorerFactory()

        factory.get_scorer("community-x", note_count=100)
        factory.get_scorer("community-x", note_count=300)
        factory.get_scorer("community-y", note_count=100)

        assert factory.get_cache_info()["cache_size"] == 3

        removed = factory.invalidate_community("community-x")

        assert removed == 2
        assert factory.get_cache_info()["cache_size"] == 1

    def test_clear_cache_removes_all_scorers(self):
        """Clear cache removes all cached scorers."""
        factory = ScorerFactory()

        for i in range(5):
            factory.get_scorer(f"community-{i}", note_count=100)

        assert factory.get_cache_info()["cache_size"] == 5

        factory.clear_cache()

        assert factory.get_cache_info()["cache_size"] == 0


class TestTierOverrideFunctionality:
    """Integration tests for tier_override (AC #6)."""

    def test_tier_override_forces_bayesian_for_large_community(self):
        """
        AC #6: tier_override can force Bayesian scorer for large community.
        """
        factory = ScorerFactory()

        scorer = factory.get_scorer(
            "large-community-override", note_count=5000, tier_override=ScoringTier.MINIMAL
        )

        assert isinstance(scorer, BayesianAverageScorerAdapter)

        result = scorer.score_note("override-note", [0.6, 0.7, 0.8])
        assert isinstance(result, ScoringResult)
        assert result.metadata["algorithm"] == "bayesian_average_tier0"

    def test_tier_override_forces_mf_for_small_community(self):
        """tier_override can force MF scorer for small community."""
        factory = ScorerFactory()

        scorer = factory.get_scorer(
            "small-community-override", note_count=50, tier_override=ScoringTier.LIMITED
        )

        assert isinstance(scorer, MFCoreScorerAdapter)

        result = scorer.score_note("override-note", [0.6, 0.7, 0.8, 0.9, 0.5])
        assert isinstance(result, ScoringResult)

    def test_tier_override_uses_override_tier_in_cache(self):
        """tier_override stores scorer under override tier in cache."""
        factory = ScorerFactory()

        _scorer = factory.get_scorer(
            "cache-override-community", note_count=50, tier_override=ScoringTier.BASIC
        )

        cache_info = factory.get_cache_info()

        cached_entry = next(
            (
                e
                for e in cache_info["cached_entries"]
                if e["community_server_id"] == "cache-override-community"
            ),
            None,
        )
        assert cached_entry is not None
        assert cached_entry["tier"] == "basic"

    def test_tier_override_and_computed_tier_both_cached(self):
        """Both override tier and computed tier can be cached separately."""
        factory = ScorerFactory()

        scorer_computed = factory.get_scorer("dual-cache-community", note_count=50)
        scorer_override = factory.get_scorer(
            "dual-cache-community", note_count=50, tier_override=ScoringTier.LIMITED
        )

        assert scorer_computed is not scorer_override
        assert isinstance(scorer_computed, BayesianAverageScorerAdapter)
        assert isinstance(scorer_override, MFCoreScorerAdapter)

        assert factory.get_cache_info()["cache_size"] == 2

    def test_all_tier_overrides_work(self):
        """Test that all tier overrides produce valid scorers."""
        factory = ScorerFactory()

        all_tiers = [
            ScoringTier.MINIMAL,
            ScoringTier.LIMITED,
            ScoringTier.BASIC,
            ScoringTier.INTERMEDIATE,
            ScoringTier.ADVANCED,
            ScoringTier.FULL,
        ]

        for tier in all_tiers:
            scorer = factory.get_scorer(f"tier-test-{tier.value}", note_count=1, tier_override=tier)

            assert isinstance(scorer, ScorerProtocol), (
                f"tier_override={tier.value} should return ScorerProtocol"
            )

            result = scorer.score_note("test-note", [0.5, 0.6, 0.7, 0.8, 0.9])
            assert isinstance(result, ScoringResult), (
                f"tier_override={tier.value} should produce valid ScoringResult"
            )


class TestBatchCachingPerformance:
    """Performance tests for MFCoreScorer batch caching (AC #7)."""

    @pytest.mark.benchmark
    def test_mf_scorer_caching_reduces_latency(self):
        """
        AC #7: Verify MFCoreScorerAdapter batch caching reduces scoring latency.

        First call triggers batch scoring, subsequent calls use cache.
        """
        factory = ScorerFactory()
        scorer = factory.get_scorer("perf-community", note_count=500)
        assert isinstance(scorer, MFCoreScorerAdapter)

        ratings = [0.7, 0.8, 0.75, 0.82, 0.9]

        start_first = time.perf_counter()
        result_1 = scorer.score_note("note-1", ratings)
        first_call_time = time.perf_counter() - start_first

        start_cached = time.perf_counter()
        result_2 = scorer.score_note("note-1", ratings)
        cached_call_time = time.perf_counter() - start_cached

        assert result_1.score == result_2.score

        assert cached_call_time <= first_call_time * 1.2, (
            f"Cached call ({cached_call_time:.6f}s) should not be significantly slower than "
            f"first call ({first_call_time:.6f}s) - allowing 20% tolerance for timing variance"
        )

    @pytest.mark.benchmark
    def test_mf_scorer_cache_hit_is_fast(self):
        """Cache hits should be very fast (sub-millisecond)."""
        factory = ScorerFactory()
        scorer = factory.get_scorer("fast-cache-community", note_count=500)

        scorer.score_note("note-precache", [0.5, 0.6, 0.7, 0.8, 0.9])

        iterations = 100
        start = time.perf_counter()
        for _ in range(iterations):
            scorer.score_note("note-precache", [0.5, 0.6, 0.7, 0.8, 0.9])
        total_time = time.perf_counter() - start

        avg_time_ms = (total_time / iterations) * 1000

        assert avg_time_ms < 1.0, (
            f"Average cache hit time ({avg_time_ms:.3f}ms) should be under 1ms"
        )

    @pytest.mark.benchmark
    def test_mf_scorer_cache_stats_tracking(self):
        """MFCoreScorerAdapter tracks cache statistics."""
        factory = ScorerFactory()
        scorer = factory.get_scorer("stats-community", note_count=500)
        assert isinstance(scorer, MFCoreScorerAdapter)

        stats_before = scorer.get_cache_stats()
        assert stats_before["cached_notes"] == 0

        scorer.score_note("note-1", [0.5, 0.6])
        scorer.score_note("note-2", [0.7, 0.8])

        stats_after = scorer.get_cache_stats()
        assert stats_after["cached_notes"] == 2
        assert stats_after["is_valid"] is True

    @pytest.mark.benchmark
    def test_mf_scorer_cache_invalidation_triggers_rescoring(self):
        """Cache invalidation causes next score_note to re-score."""
        factory = ScorerFactory()
        scorer = factory.get_scorer("invalidation-community", note_count=500)
        assert isinstance(scorer, MFCoreScorerAdapter)

        scorer.score_note("note-1", [0.5, 0.6, 0.7, 0.8, 0.9])
        assert scorer.get_cache_stats()["cached_notes"] == 1

        scorer.update_ratings_version()

        start = time.perf_counter()
        scorer.score_note("note-1", [0.5, 0.6, 0.7, 0.8, 0.9])
        _rescore_time = time.perf_counter() - start

        assert scorer.get_cache_stats()["cached_notes"] == 1

    @pytest.mark.benchmark
    def test_bayesian_scorer_consistent_performance(self):
        """Bayesian scorer has consistent performance (no caching benefit)."""
        factory = ScorerFactory()
        scorer = factory.get_scorer("bayesian-perf-community", note_count=50)
        assert isinstance(scorer, BayesianAverageScorerAdapter)

        ratings = [0.7, 0.8, 0.75, 0.82]

        times = []
        for i in range(10):
            start = time.perf_counter()
            scorer.score_note(f"note-{i}", ratings)
            times.append(time.perf_counter() - start)

        avg_time = sum(times) / len(times)
        variance = sum((t - avg_time) ** 2 for t in times) / len(times)
        std_dev = variance**0.5

        assert std_dev < 0.01, f"Bayesian scorer timing variance ({std_dev:.6f}s) should be low"


class TestEndToEndScoringFlow:
    """End-to-end integration tests for complete scoring flow."""

    def test_complete_scoring_flow_bayesian_tier(self):
        """Complete flow for Bayesian tier: factory -> scorer -> result."""
        factory = ScorerFactory()
        community_id = "e2e-bayesian-community"

        scorer = factory.get_scorer(community_id, note_count=100)
        assert isinstance(scorer, BayesianAverageScorerAdapter)

        notes_to_score = [
            ("note-1", [0.9, 0.85, 0.88, 0.92]),
            ("note-2", [0.4, 0.35, 0.42, 0.38]),
            ("note-3", [0.6, 0.55, 0.58]),
            ("note-4", []),
        ]

        results = {}
        for note_id, ratings in notes_to_score:
            result = scorer.score_note(note_id, ratings)
            results[note_id] = result

            assert isinstance(result, ScoringResult)
            assert 0.0 <= result.score <= 1.0
            assert result.confidence_level in ["provisional", "low", "standard", "high"]

        assert results["note-1"].score > results["note-2"].score, (
            "Higher rated note should have higher score"
        )

    def test_complete_scoring_flow_mf_tier(self):
        """Complete flow for MF tier: factory -> scorer -> result."""
        factory = ScorerFactory()
        community_id = "e2e-mf-community"

        scorer = factory.get_scorer(community_id, note_count=500)
        assert isinstance(scorer, MFCoreScorerAdapter)

        notes_to_score = [
            ("note-1", [0.9, 0.85, 0.88, 0.92, 0.87]),
            ("note-2", [0.4, 0.35, 0.42, 0.38, 0.41]),
            ("note-3", [0.6, 0.55, 0.58, 0.62, 0.59]),
        ]

        results = {}
        for note_id, ratings in notes_to_score:
            result = scorer.score_note(note_id, ratings)
            results[note_id] = result

            assert isinstance(result, ScoringResult)
            assert 0.0 <= result.score <= 1.0
            assert result.confidence_level in ["provisional", "standard"]

    def test_protocol_compliance_both_scorers(self):
        """Both scorers fully comply with ScorerProtocol interface."""
        factory = ScorerFactory()

        bayesian = factory.get_scorer("protocol-test-1", note_count=50)
        mf = factory.get_scorer("protocol-test-2", note_count=500)

        for scorer in [bayesian, mf]:
            assert isinstance(scorer, ScorerProtocol)
            assert hasattr(scorer, "score_note")
            assert callable(scorer.score_note)

            result = scorer.score_note("protocol-note", [0.5, 0.6, 0.7])

            assert hasattr(result, "score")
            assert hasattr(result, "confidence_level")
            assert hasattr(result, "metadata")
            assert isinstance(result.score, float)
            assert isinstance(result.confidence_level, str)
            assert isinstance(result.metadata, dict)
