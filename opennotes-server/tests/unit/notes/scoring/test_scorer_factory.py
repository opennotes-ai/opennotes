"""
Tests for ScorerFactory with tier-based selection.

TDD: Write failing tests first, then implement.
"""


class TestScorerFactoryInstantiation:
    """Tests for ScorerFactory instantiation (AC #1)."""

    def test_factory_can_be_instantiated(self):
        """ScorerFactory can be instantiated."""
        from src.notes.scoring.scorer_factory import ScorerFactory

        factory = ScorerFactory()

        assert factory is not None

    def test_factory_has_empty_cache_initially(self):
        """Factory starts with empty cache."""
        from src.notes.scoring.scorer_factory import ScorerFactory

        factory = ScorerFactory()

        assert len(factory._cache) == 0


class TestScorerFactoryTierSelection:
    """Tests for get_scorer tier selection logic (AC #2, #5)."""

    def test_get_scorer_returns_bayesian_adapter_for_minimal_tier(self):
        """get_scorer returns BayesianAverageScorerAdapter for MINIMAL tier (< 200 notes)."""
        from src.notes.scoring.bayesian_scorer_adapter import (
            BayesianAverageScorerAdapter,
        )
        from src.notes.scoring.scorer_factory import ScorerFactory

        factory = ScorerFactory()

        scorer = factory.get_scorer("community-123", note_count=50)

        assert isinstance(scorer, BayesianAverageScorerAdapter)

    def test_get_scorer_returns_bayesian_for_zero_notes(self):
        """get_scorer returns BayesianAverageScorerAdapter for 0 notes."""
        from src.notes.scoring.bayesian_scorer_adapter import (
            BayesianAverageScorerAdapter,
        )
        from src.notes.scoring.scorer_factory import ScorerFactory

        factory = ScorerFactory()

        scorer = factory.get_scorer("community-123", note_count=0)

        assert isinstance(scorer, BayesianAverageScorerAdapter)

    def test_get_scorer_returns_bayesian_at_199_notes(self):
        """get_scorer returns BayesianAverageScorerAdapter at 199 notes (still MINIMAL)."""
        from src.notes.scoring.bayesian_scorer_adapter import (
            BayesianAverageScorerAdapter,
        )
        from src.notes.scoring.scorer_factory import ScorerFactory

        factory = ScorerFactory()

        scorer = factory.get_scorer("community-123", note_count=199)

        assert isinstance(scorer, BayesianAverageScorerAdapter)

    def test_get_scorer_returns_mf_adapter_at_200_notes(self):
        """get_scorer returns MFCoreScorerAdapter at exactly 200 notes (LIMITED tier)."""
        from src.notes.scoring.mf_scorer_adapter import MFCoreScorerAdapter
        from src.notes.scoring.scorer_factory import ScorerFactory

        factory = ScorerFactory()

        scorer = factory.get_scorer("community-123", note_count=200)

        assert isinstance(scorer, MFCoreScorerAdapter)

    def test_get_scorer_returns_mf_adapter_for_limited_tier(self):
        """get_scorer returns MFCoreScorerAdapter for LIMITED tier (200-1000 notes)."""
        from src.notes.scoring.mf_scorer_adapter import MFCoreScorerAdapter
        from src.notes.scoring.scorer_factory import ScorerFactory

        factory = ScorerFactory()

        scorer = factory.get_scorer("community-123", note_count=500)

        assert isinstance(scorer, MFCoreScorerAdapter)

    def test_get_scorer_returns_mf_adapter_for_basic_tier(self):
        """get_scorer returns MFCoreScorerAdapter for BASIC tier (1000-5000 notes)."""
        from src.notes.scoring.mf_scorer_adapter import MFCoreScorerAdapter
        from src.notes.scoring.scorer_factory import ScorerFactory

        factory = ScorerFactory()

        scorer = factory.get_scorer("community-123", note_count=2000)

        assert isinstance(scorer, MFCoreScorerAdapter)

    def test_get_scorer_returns_mf_adapter_for_intermediate_tier(self):
        """get_scorer returns MFCoreScorerAdapter for INTERMEDIATE tier (5000-10000 notes)."""
        from src.notes.scoring.mf_scorer_adapter import MFCoreScorerAdapter
        from src.notes.scoring.scorer_factory import ScorerFactory

        factory = ScorerFactory()

        scorer = factory.get_scorer("community-123", note_count=7000)

        assert isinstance(scorer, MFCoreScorerAdapter)

    def test_get_scorer_returns_mf_adapter_for_advanced_tier(self):
        """get_scorer returns MFCoreScorerAdapter for ADVANCED tier (10000-50000 notes)."""
        from src.notes.scoring.mf_scorer_adapter import MFCoreScorerAdapter
        from src.notes.scoring.scorer_factory import ScorerFactory

        factory = ScorerFactory()

        scorer = factory.get_scorer("community-123", note_count=25000)

        assert isinstance(scorer, MFCoreScorerAdapter)

    def test_get_scorer_returns_mf_adapter_for_full_tier(self):
        """get_scorer returns MFCoreScorerAdapter for FULL tier (50000+ notes)."""
        from src.notes.scoring.mf_scorer_adapter import MFCoreScorerAdapter
        from src.notes.scoring.scorer_factory import ScorerFactory

        factory = ScorerFactory()

        scorer = factory.get_scorer("community-123", note_count=100000)

        assert isinstance(scorer, MFCoreScorerAdapter)


class TestScorerFactoryProtocolCompliance:
    """Tests for ScorerProtocol compliance (AC #2)."""

    def test_get_scorer_returns_scorer_protocol_for_minimal(self):
        """get_scorer returns ScorerProtocol implementation for MINIMAL tier."""
        from src.notes.scoring.scorer_factory import ScorerFactory
        from src.notes.scoring.scorer_protocol import ScorerProtocol

        factory = ScorerFactory()

        scorer = factory.get_scorer("community-123", note_count=50)

        assert isinstance(scorer, ScorerProtocol)

    def test_get_scorer_returns_scorer_protocol_for_limited(self):
        """get_scorer returns ScorerProtocol implementation for LIMITED tier."""
        from src.notes.scoring.scorer_factory import ScorerFactory
        from src.notes.scoring.scorer_protocol import ScorerProtocol

        factory = ScorerFactory()

        scorer = factory.get_scorer("community-123", note_count=500)

        assert isinstance(scorer, ScorerProtocol)


class TestScorerFactoryCaching:
    """Tests for scorer caching per community (AC #3)."""

    def test_get_scorer_caches_scorer_per_community(self):
        """get_scorer returns cached scorer for same community and tier."""
        from src.notes.scoring.scorer_factory import ScorerFactory

        factory = ScorerFactory()

        scorer1 = factory.get_scorer("community-123", note_count=50)
        scorer2 = factory.get_scorer("community-123", note_count=50)

        assert scorer1 is scorer2

    def test_get_scorer_different_communities_get_different_scorers(self):
        """Different communities get different scorer instances."""
        from src.notes.scoring.scorer_factory import ScorerFactory

        factory = ScorerFactory()

        scorer1 = factory.get_scorer("community-123", note_count=50)
        scorer2 = factory.get_scorer("community-456", note_count=50)

        assert scorer1 is not scorer2

    def test_get_scorer_same_community_same_tier_returns_cached(self):
        """Same community and tier returns cached scorer."""
        from src.notes.scoring.scorer_factory import ScorerFactory

        factory = ScorerFactory()

        scorer1 = factory.get_scorer("community-123", note_count=100)
        scorer2 = factory.get_scorer("community-123", note_count=150)

        assert scorer1 is scorer2

    def test_get_scorer_creates_new_scorer_when_tier_changes(self):
        """When tier changes, a new scorer is created."""
        from src.notes.scoring.bayesian_scorer_adapter import (
            BayesianAverageScorerAdapter,
        )
        from src.notes.scoring.mf_scorer_adapter import MFCoreScorerAdapter
        from src.notes.scoring.scorer_factory import ScorerFactory

        factory = ScorerFactory()

        scorer1 = factory.get_scorer("community-123", note_count=100)
        scorer2 = factory.get_scorer("community-123", note_count=300)

        assert isinstance(scorer1, BayesianAverageScorerAdapter)
        assert isinstance(scorer2, MFCoreScorerAdapter)
        assert scorer1 is not scorer2

    def test_cache_includes_tier_in_key(self):
        """Cache key includes both community_server_id and tier."""
        from src.notes.scoring.scorer_factory import ScorerFactory
        from src.notes.scoring.tier_config import ScoringTier

        factory = ScorerFactory()

        factory.get_scorer("community-123", note_count=50)
        factory.get_scorer("community-123", note_count=500)

        assert (
            "community-123",
            ScoringTier.MINIMAL,
        ) in factory._cache
        assert (
            "community-123",
            ScoringTier.LIMITED,
        ) in factory._cache


class TestScorerFactoryTierOverride:
    """Tests for tier_override parameter (AC #4)."""

    def test_tier_override_forces_specific_tier(self):
        """tier_override forces use of specific tier regardless of note_count."""
        from src.notes.scoring.mf_scorer_adapter import MFCoreScorerAdapter
        from src.notes.scoring.scorer_factory import ScorerFactory
        from src.notes.scoring.tier_config import ScoringTier

        factory = ScorerFactory()

        scorer = factory.get_scorer(
            "community-123", note_count=50, tier_override=ScoringTier.LIMITED
        )

        assert isinstance(scorer, MFCoreScorerAdapter)

    def test_tier_override_to_minimal_forces_bayesian(self):
        """tier_override to MINIMAL forces BayesianAverageScorerAdapter."""
        from src.notes.scoring.bayesian_scorer_adapter import (
            BayesianAverageScorerAdapter,
        )
        from src.notes.scoring.scorer_factory import ScorerFactory
        from src.notes.scoring.tier_config import ScoringTier

        factory = ScorerFactory()

        scorer = factory.get_scorer(
            "community-123", note_count=5000, tier_override=ScoringTier.MINIMAL
        )

        assert isinstance(scorer, BayesianAverageScorerAdapter)

    def test_tier_override_ignores_note_count(self):
        """tier_override completely ignores note_count when determining tier."""
        from src.notes.scoring.mf_scorer_adapter import MFCoreScorerAdapter
        from src.notes.scoring.scorer_factory import ScorerFactory
        from src.notes.scoring.tier_config import ScoringTier

        factory = ScorerFactory()

        scorer = factory.get_scorer("community-123", note_count=0, tier_override=ScoringTier.FULL)

        assert isinstance(scorer, MFCoreScorerAdapter)

    def test_tier_override_uses_correct_cache_key(self):
        """tier_override uses the override tier in cache key, not computed tier."""
        from src.notes.scoring.scorer_factory import ScorerFactory
        from src.notes.scoring.tier_config import ScoringTier

        factory = ScorerFactory()

        factory.get_scorer("community-123", note_count=50, tier_override=ScoringTier.LIMITED)

        assert (
            "community-123",
            ScoringTier.LIMITED,
        ) in factory._cache

    def test_tier_override_none_uses_computed_tier(self):
        """tier_override=None uses computed tier from note_count."""
        from src.notes.scoring.bayesian_scorer_adapter import (
            BayesianAverageScorerAdapter,
        )
        from src.notes.scoring.scorer_factory import ScorerFactory

        factory = ScorerFactory()

        scorer = factory.get_scorer("community-123", note_count=50, tier_override=None)

        assert isinstance(scorer, BayesianAverageScorerAdapter)


class TestScorerFactoryIntegrationWithTierConfig:
    """Tests for integration with tier_config.py (AC #5, #6)."""

    def test_uses_get_tier_for_note_count_function(self):
        """Factory uses get_tier_for_note_count for tier determination."""
        from src.notes.scoring.scorer_factory import ScorerFactory
        from src.notes.scoring.tier_config import ScoringTier

        factory = ScorerFactory()

        factory.get_scorer("community-123", note_count=199)

        assert (
            "community-123",
            ScoringTier.MINIMAL,
        ) in factory._cache

    def test_boundary_at_200_notes_yields_limited(self):
        """At exactly 200 notes, tier should be LIMITED per tier_config.py."""
        from src.notes.scoring.scorer_factory import ScorerFactory
        from src.notes.scoring.tier_config import ScoringTier

        factory = ScorerFactory()

        factory.get_scorer("community-123", note_count=200)

        assert (
            "community-123",
            ScoringTier.LIMITED,
        ) in factory._cache

    def test_boundary_at_1000_notes_yields_basic(self):
        """At exactly 1000 notes, tier should be BASIC per tier_config.py."""
        from src.notes.scoring.scorer_factory import ScorerFactory
        from src.notes.scoring.tier_config import ScoringTier

        factory = ScorerFactory()

        factory.get_scorer("community-123", note_count=1000)

        assert (
            "community-123",
            ScoringTier.BASIC,
        ) in factory._cache
