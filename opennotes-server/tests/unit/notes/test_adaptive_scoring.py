import sys
from pathlib import Path

import pytest

# Add Community Notes scoring module to path
scoring_path = (
    Path(__file__).parent.parent.parent.parent.parent / "communitynotes" / "scoring" / "src"
)
sys.path.insert(0, str(scoring_path))

from scoring.enums import Scorers  # noqa: E402 - sys.path manipulation required before import

VALID_CONFIDENCE_LEVELS = {"very_low", "low", "medium", "high", "very_high", "maximum"}


# Disable database setup for pure unit tests
# Override the autouse fixtures from root conftest
@pytest.fixture(autouse=True)
def setup_database():
    """Override autouse database fixture - unit tests don't need database."""
    return


@pytest.fixture(autouse=True)
def mock_external_services():
    """Override autouse mock fixture - unit tests don't need external services."""
    return


class AdaptiveScoringTier:
    """
    Represents a tier in the adaptive scoring system.

    Each tier defines data volume thresholds and which Community Notes scorers
    should be enabled for that tier.
    """

    def __init__(
        self,
        tier_id: str,
        min_notes: int,
        max_notes: int | None,
        enabled_scorers: set[Scorers],
        description: str,
        confidence_level: str,
    ):
        self.tier_id = tier_id
        self.min_notes = min_notes
        self.max_notes = max_notes
        self.enabled_scorers = enabled_scorers
        self.description = description
        self.confidence_level = confidence_level

    def contains(self, note_count: int) -> bool:
        """Check if a given note count falls within this tier's range."""
        if self.max_notes is None:
            return note_count >= self.min_notes
        return self.min_notes <= note_count < self.max_notes


class AdaptiveScoringSelector:
    """
    Selects the appropriate Community Notes scoring tier based on data volume.

    The system implements 6 graduated tiers:
    - Tier 0: 0-200 notes (minimal/test mode)
    - Tier 0.5: 200-1000 notes (limited/MFCoreScorer with warnings)
    - Tier 1: 1000-5000 notes (basic/full MFCoreScorer)
    - Tier 2: 5000-10000 notes (intermediate/+ MFExpansionScorer)
    - Tier 3: 10000-50000 notes (advanced/+ group scorers)
    - Tier 4: 50000+ notes (full pipeline with clustering)
    """

    def __init__(self):
        self.tiers = [
            AdaptiveScoringTier(
                tier_id="tier-0",
                min_notes=0,
                max_notes=200,
                enabled_scorers=set(),  # Minimal/test mode - no matrix factorization
                description="Minimal (test mode)",
                confidence_level="very_low",
            ),
            AdaptiveScoringTier(
                tier_id="tier-0.5",
                min_notes=200,
                max_notes=1000,
                enabled_scorers={Scorers.MFCoreScorer},
                description="Limited (MFCoreScorer with warnings)",
                confidence_level="low",
            ),
            AdaptiveScoringTier(
                tier_id="tier-1",
                min_notes=1000,
                max_notes=5000,
                enabled_scorers={Scorers.MFCoreScorer},
                description="Basic (full MFCoreScorer)",
                confidence_level="medium",
            ),
            AdaptiveScoringTier(
                tier_id="tier-2",
                min_notes=5000,
                max_notes=10000,
                enabled_scorers={Scorers.MFCoreScorer, Scorers.MFExpansionScorer},
                description="Intermediate (+ MFExpansionScorer)",
                confidence_level="high",
            ),
            AdaptiveScoringTier(
                tier_id="tier-3",
                min_notes=10000,
                max_notes=50000,
                enabled_scorers={
                    Scorers.MFCoreScorer,
                    Scorers.MFExpansionScorer,
                    Scorers.MFGroupScorer,
                    Scorers.MFExpansionPlusScorer,
                },
                description="Advanced (+ group scorers)",
                confidence_level="very_high",
            ),
            AdaptiveScoringTier(
                tier_id="tier-4",
                min_notes=50000,
                max_notes=None,
                enabled_scorers={
                    Scorers.MFCoreScorer,
                    Scorers.MFExpansionScorer,
                    Scorers.MFGroupScorer,
                    Scorers.MFExpansionPlusScorer,
                    Scorers.MFMultiGroupScorer,
                },
                description="Full pipeline (all scorers + clustering)",
                confidence_level="maximum",
            ),
        ]

    def select_tier(self, note_count: int) -> AdaptiveScoringTier:
        """
        Select the appropriate tier based on note count.

        Args:
            note_count: Number of notes available for scoring

        Returns:
            The tier that matches the note count

        Raises:
            ValueError: If note count is negative
        """
        if note_count < 0:
            raise ValueError(f"Note count must be non-negative, got {note_count}")

        for tier in self.tiers:
            if tier.contains(note_count):
                return tier

        # Should never reach here due to tier-4 having no max
        raise ValueError(f"No tier found for note count {note_count}")


@pytest.fixture
def selector():
    """Fixture providing an AdaptiveScoringSelector instance."""
    return AdaptiveScoringSelector()


class TestTierSelection:
    """Test correct tier selection across all boundaries."""

    def test_tier_0_minimum_boundary(self, selector):
        """Test Tier 0 selection at 0 notes."""
        tier = selector.select_tier(0)
        assert tier.tier_id == "tier-0"
        assert tier.confidence_level in VALID_CONFIDENCE_LEVELS
        assert tier.enabled_scorers == set()

    def test_tier_0_single_note(self, selector):
        """Test Tier 0 selection with 1 note."""
        tier = selector.select_tier(1)
        assert tier.tier_id == "tier-0"

    def test_tier_0_near_upper_boundary(self, selector):
        """Test Tier 0 selection at 199 notes (just below threshold)."""
        tier = selector.select_tier(199)
        assert tier.tier_id == "tier-0"
        assert tier.enabled_scorers == set()

    def test_tier_0_5_lower_boundary(self, selector):
        """Test Tier 0.5 selection at exactly 200 notes."""
        tier = selector.select_tier(200)
        assert tier.tier_id == "tier-0.5"
        assert tier.confidence_level in VALID_CONFIDENCE_LEVELS
        assert Scorers.MFCoreScorer in tier.enabled_scorers
        assert len(tier.enabled_scorers) == 1

    def test_tier_0_5_middle(self, selector):
        """Test Tier 0.5 selection at 201 notes."""
        tier = selector.select_tier(201)
        assert tier.tier_id == "tier-0.5"

    def test_tier_0_5_near_upper_boundary(self, selector):
        """Test Tier 0.5 selection at 999 notes."""
        tier = selector.select_tier(999)
        assert tier.tier_id == "tier-0.5"
        assert Scorers.MFCoreScorer in tier.enabled_scorers

    def test_tier_1_lower_boundary(self, selector):
        """Test Tier 1 selection at exactly 1000 notes."""
        tier = selector.select_tier(1000)
        assert tier.tier_id == "tier-1"
        assert tier.confidence_level in VALID_CONFIDENCE_LEVELS
        assert Scorers.MFCoreScorer in tier.enabled_scorers
        assert len(tier.enabled_scorers) == 1

    def test_tier_1_middle(self, selector):
        """Test Tier 1 selection at 1001 notes."""
        tier = selector.select_tier(1001)
        assert tier.tier_id == "tier-1"

    def test_tier_1_near_upper_boundary(self, selector):
        """Test Tier 1 selection at 4999 notes."""
        tier = selector.select_tier(4999)
        assert tier.tier_id == "tier-1"

    def test_tier_2_lower_boundary(self, selector):
        """Test Tier 2 selection at exactly 5000 notes."""
        tier = selector.select_tier(5000)
        assert tier.tier_id == "tier-2"
        assert tier.confidence_level in VALID_CONFIDENCE_LEVELS
        assert Scorers.MFCoreScorer in tier.enabled_scorers
        assert Scorers.MFExpansionScorer in tier.enabled_scorers
        assert len(tier.enabled_scorers) == 2

    def test_tier_2_middle(self, selector):
        """Test Tier 2 selection at 5001 notes."""
        tier = selector.select_tier(5001)
        assert tier.tier_id == "tier-2"

    def test_tier_2_near_upper_boundary(self, selector):
        """Test Tier 2 selection at 9999 notes."""
        tier = selector.select_tier(9999)
        assert tier.tier_id == "tier-2"

    def test_tier_3_lower_boundary(self, selector):
        """Test Tier 3 selection at exactly 10000 notes."""
        tier = selector.select_tier(10000)
        assert tier.tier_id == "tier-3"
        assert tier.confidence_level in VALID_CONFIDENCE_LEVELS
        assert Scorers.MFCoreScorer in tier.enabled_scorers
        assert Scorers.MFExpansionScorer in tier.enabled_scorers
        assert Scorers.MFGroupScorer in tier.enabled_scorers
        assert Scorers.MFExpansionPlusScorer in tier.enabled_scorers
        assert len(tier.enabled_scorers) == 4

    def test_tier_3_middle(self, selector):
        """Test Tier 3 selection at 10001 notes."""
        tier = selector.select_tier(10001)
        assert tier.tier_id == "tier-3"

    def test_tier_3_near_upper_boundary(self, selector):
        """Test Tier 3 selection at 49999 notes."""
        tier = selector.select_tier(49999)
        assert tier.tier_id == "tier-3"

    def test_tier_4_lower_boundary(self, selector):
        """Test Tier 4 selection at exactly 50000 notes."""
        tier = selector.select_tier(50000)
        assert tier.tier_id == "tier-4"
        assert tier.confidence_level in VALID_CONFIDENCE_LEVELS
        assert Scorers.MFCoreScorer in tier.enabled_scorers
        assert Scorers.MFExpansionScorer in tier.enabled_scorers
        assert Scorers.MFGroupScorer in tier.enabled_scorers
        assert Scorers.MFExpansionPlusScorer in tier.enabled_scorers
        assert Scorers.MFMultiGroupScorer in tier.enabled_scorers
        assert len(tier.enabled_scorers) == 5

    def test_tier_4_middle(self, selector):
        """Test Tier 4 selection at 50001 notes."""
        tier = selector.select_tier(50001)
        assert tier.tier_id == "tier-4"

    def test_tier_4_large_dataset(self, selector):
        """Test Tier 4 selection at 100000 notes."""
        tier = selector.select_tier(100000)
        assert tier.tier_id == "tier-4"


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_negative_note_count(self, selector):
        """Test that negative note counts raise ValueError."""
        with pytest.raises(ValueError, match="Note count must be non-negative"):
            selector.select_tier(-1)

    def test_exact_boundary_200(self, selector):
        """Test exact boundary at 200 notes (Tier 0 -> Tier 0.5)."""
        tier_199 = selector.select_tier(199)
        tier_200 = selector.select_tier(200)

        assert tier_199.tier_id == "tier-0"
        assert tier_200.tier_id == "tier-0.5"
        assert tier_199.tier_id != tier_200.tier_id

    def test_exact_boundary_1000(self, selector):
        """Test exact boundary at 1000 notes (Tier 0.5 -> Tier 1)."""
        tier_999 = selector.select_tier(999)
        tier_1000 = selector.select_tier(1000)

        assert tier_999.tier_id == "tier-0.5"
        assert tier_1000.tier_id == "tier-1"
        assert tier_999.confidence_level == "low"
        assert tier_1000.confidence_level == "medium"


class TestTierProperties:
    """Test tier property consistency."""

    def test_tier_progression_scorers(self, selector):
        """Test that enabled scorers generally increase with tier level."""
        tier_counts = []
        for note_count in [0, 200, 1000, 5000, 10000, 50000]:
            tier = selector.select_tier(note_count)
            tier_counts.append(len(tier.enabled_scorers))

        # Tier 0 has 0 scorers, Tier 0.5 and 1 have 1, then increasing
        assert tier_counts[0] == 0  # Tier 0
        assert tier_counts[1] == 1  # Tier 0.5
        assert tier_counts[2] == 1  # Tier 1
        assert tier_counts[3] == 2  # Tier 2
        assert tier_counts[4] == 4  # Tier 3
        assert tier_counts[5] == 5  # Tier 4

    def test_tier_confidence_progression(self, selector):
        """Test that confidence levels progress appropriately."""
        expected_confidence = [
            "very_low",  # Tier 0
            "low",  # Tier 0.5
            "medium",  # Tier 1
            "high",  # Tier 2
            "very_high",  # Tier 3
            "maximum",  # Tier 4
        ]

        for i, note_count in enumerate([0, 200, 1000, 5000, 10000, 50000]):
            tier = selector.select_tier(note_count)
            assert tier.confidence_level == expected_confidence[i]

    def test_all_tiers_have_descriptions(self, selector):
        """Test that all tiers have non-empty descriptions."""
        for tier in selector.tiers:
            assert tier.description
            assert len(tier.description) > 0

    def test_tier_ranges_non_overlapping(self, selector):
        """Test that tier ranges don't overlap."""
        for i in range(len(selector.tiers) - 1):
            current_tier = selector.tiers[i]
            next_tier = selector.tiers[i + 1]

            # Current tier's max should equal next tier's min
            assert current_tier.max_notes == next_tier.min_notes


class TestScorerEnabling:
    """Test scorer enabling logic for each tier."""

    def test_tier_0_no_scorers(self, selector):
        """Test Tier 0 has no enabled scorers (test mode)."""
        tier = selector.select_tier(100)
        assert len(tier.enabled_scorers) == 0

    def test_tier_0_5_mf_core_only(self, selector):
        """Test Tier 0.5 only enables MFCoreScorer."""
        tier = selector.select_tier(500)
        assert tier.enabled_scorers == {Scorers.MFCoreScorer}

    def test_tier_1_mf_core_only(self, selector):
        """Test Tier 1 only enables MFCoreScorer (same as 0.5 but higher confidence)."""
        tier = selector.select_tier(2000)
        assert tier.enabled_scorers == {Scorers.MFCoreScorer}

    def test_tier_2_adds_expansion(self, selector):
        """Test Tier 2 adds MFExpansionScorer."""
        tier = selector.select_tier(7500)
        assert Scorers.MFCoreScorer in tier.enabled_scorers
        assert Scorers.MFExpansionScorer in tier.enabled_scorers
        assert Scorers.MFGroupScorer not in tier.enabled_scorers

    def test_tier_3_adds_group_scorers(self, selector):
        """Test Tier 3 adds group scorers."""
        tier = selector.select_tier(25000)
        assert Scorers.MFCoreScorer in tier.enabled_scorers
        assert Scorers.MFExpansionScorer in tier.enabled_scorers
        assert Scorers.MFGroupScorer in tier.enabled_scorers
        assert Scorers.MFExpansionPlusScorer in tier.enabled_scorers
        assert Scorers.MFMultiGroupScorer not in tier.enabled_scorers

    def test_tier_4_all_scorers(self, selector):
        """Test Tier 4 enables all major scorers."""
        tier = selector.select_tier(75000)
        assert Scorers.MFCoreScorer in tier.enabled_scorers
        assert Scorers.MFExpansionScorer in tier.enabled_scorers
        assert Scorers.MFGroupScorer in tier.enabled_scorers
        assert Scorers.MFExpansionPlusScorer in tier.enabled_scorers
        assert Scorers.MFMultiGroupScorer in tier.enabled_scorers


class TestConfigurationOverride:
    """Test configuration override functionality (to be implemented)."""

    @pytest.mark.skip(reason="Configuration override not yet implemented")
    def test_manual_tier_override(self):
        """Test that manual tier selection overrides automatic selection."""

    @pytest.mark.skip(reason="Configuration override not yet implemented")
    def test_manual_scorer_specification(self):
        """Test that manual scorer specification overrides tier defaults."""


class TestFallbackMechanism:
    """Test graceful fallback when scorers fail (to be implemented)."""

    @pytest.mark.skip(reason="Fallback mechanism not yet implemented")
    def test_fallback_to_simpler_scorer_on_timeout(self):
        """Test that system falls back to simpler scorer on timeout."""

    @pytest.mark.skip(reason="Fallback mechanism not yet implemented")
    def test_fallback_to_simpler_scorer_on_error(self):
        """Test that system falls back to simpler scorer on error."""
