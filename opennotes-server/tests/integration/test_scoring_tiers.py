"""
Integration tests for adaptive scoring system with real Community Notes datasets.

Tests scoring execution across all tiers with sample datasets of varying sizes.
"""

import sys
from pathlib import Path

import pytest

# Add Community Notes scoring module to path
scoring_path = Path(__file__).parent.parent.parent.parent / "communitynotes" / "scoring" / "src"
sys.path.insert(0, str(scoring_path))

from scoring.enums import Scorers  # noqa: E402

# Import the adaptive scoring selector from unit tests
sys.path.insert(0, str(Path(__file__).parent.parent / "unit" / "notes"))
from test_adaptive_scoring import AdaptiveScoringSelector  # noqa: E402

# Import test data generator
sys.path.insert(0, str(Path(__file__).parent.parent / "fixtures"))
from community_notes_generator import CommunityNotesGenerator, generate_tier_datasets  # noqa: E402


@pytest.fixture(scope="module")
def generator():
    """Fixture providing a CommunityNotesGenerator instance."""
    return CommunityNotesGenerator(seed=42)


@pytest.fixture(scope="module")
def selector():
    """Fixture providing an AdaptiveScoringSelector instance."""
    return AdaptiveScoringSelector()


@pytest.fixture(scope="module")
def tier_datasets():
    """Generate datasets for each tier (cached for module)."""
    return generate_tier_datasets()


class TestTierDatasetGeneration:
    """Test that dataset generation works correctly."""

    def test_tier_0_dataset(self, generator):
        """Test generation of Tier 0 dataset (150 notes)."""
        notes, ratings, enrollment = generator.generate_dataset(150, ratings_per_note=5)

        assert len(notes) == 150
        assert len(ratings) >= 150 * 2  # At least 2 ratings per note
        assert len(enrollment) > 0
        assert all("noteId" in note for note in notes)
        assert all("raterParticipantId" in rating for rating in ratings)

    def test_tier_0_5_dataset(self, generator):
        """Test generation of Tier 0.5 dataset (500 notes)."""
        notes, ratings, enrollment = generator.generate_dataset(500, ratings_per_note=5)

        assert len(notes) == 500
        assert len(ratings) >= 500 * 2
        assert len(enrollment) > 0

    def test_tier_1_dataset(self, generator):
        """Test generation of Tier 1 dataset (2000 notes)."""
        notes, ratings, enrollment = generator.generate_dataset(2000, ratings_per_note=6)

        assert len(notes) == 2000
        assert len(ratings) >= 2000 * 2
        assert len(enrollment) > 0

    def test_tier_2_dataset(self, generator):
        """Test generation of Tier 2 dataset (7500 notes)."""
        notes, ratings, enrollment = generator.generate_dataset(7500, ratings_per_note=6)

        assert len(notes) == 7500
        assert len(ratings) >= 7500 * 2
        assert len(enrollment) > 0

    @pytest.mark.slow
    def test_tier_3_dataset(self, generator):
        """Test generation of Tier 3 dataset (25000 notes)."""
        notes, ratings, enrollment = generator.generate_dataset(25000, ratings_per_note=7)

        assert len(notes) == 25000
        assert len(ratings) >= 25000 * 2
        assert len(enrollment) > 0

    @pytest.mark.slow
    def test_tier_4_dataset(self, generator):
        """Test generation of Tier 4 dataset (75000 notes)."""
        notes, ratings, enrollment = generator.generate_dataset(75000, ratings_per_note=8)

        assert len(notes) == 75000
        assert len(ratings) >= 75000 * 2
        assert len(enrollment) > 0


class TestTierSelectionWithRealData:
    """Test tier selection with real dataset sizes."""

    def test_tier_selection_matches_dataset_size(self, selector, tier_datasets):
        """Test that tier selection correctly identifies dataset sizes."""
        tier_expectations = {
            "tier_0_150": "tier-0",
            "tier_0.5_500": "tier-0.5",
            "tier_1_2000": "tier-1",
            "tier_2_7500": "tier-2",
            "tier_3_25000": "tier-3",
            "tier_4_75000": "tier-4",
        }

        for dataset_name, expected_tier_id in tier_expectations.items():
            notes, _, _ = tier_datasets[dataset_name]
            note_count = len(notes)
            tier = selector.select_tier(note_count)
            assert tier.tier_id == expected_tier_id, (
                f"Dataset {dataset_name} with {note_count} notes "
                f"should select {expected_tier_id}, got {tier.tier_id}"
            )


class TestScoringExecution:
    """Test actual scoring execution (mocked for now)."""

    @pytest.mark.skip(reason="Requires full Community Notes scorer integration")
    def test_tier_0_scoring_execution(self, tier_datasets):
        """Test scoring execution on Tier 0 dataset."""
        _notes, _ratings, _enrollment = tier_datasets["tier_0_150"]
        # TODO: Run actual scoring with appropriate tier configuration

    @pytest.mark.skip(reason="Requires full Community Notes scorer integration")
    def test_tier_0_5_scoring_execution(self, tier_datasets):
        """Test scoring execution on Tier 0.5 dataset with MFCoreScorer."""
        _notes, _ratings, _enrollment = tier_datasets["tier_0.5_500"]
        # TODO: Run actual scoring with MFCoreScorer

    @pytest.mark.skip(reason="Requires full Community Notes scorer integration")
    def test_tier_1_scoring_execution(self, tier_datasets):
        """Test scoring execution on Tier 1 dataset with full MFCoreScorer."""
        _notes, _ratings, _enrollment = tier_datasets["tier_1_2000"]
        # TODO: Run actual scoring with MFCoreScorer (full confidence)

    @pytest.mark.skip(reason="Requires full Community Notes scorer integration")
    def test_tier_2_scoring_execution(self, tier_datasets):
        """Test scoring execution on Tier 2 dataset with expansion scorer."""
        _notes, _ratings, _enrollment = tier_datasets["tier_2_7500"]
        # TODO: Run actual scoring with MFCoreScorer + MFExpansionScorer

    @pytest.mark.skip(reason="Requires full Community Notes scorer integration")
    @pytest.mark.slow
    def test_tier_3_scoring_execution(self, tier_datasets):
        """Test scoring execution on Tier 3 dataset with group scorers."""
        _notes, _ratings, _enrollment = tier_datasets["tier_3_25000"]
        # TODO: Run actual scoring with all Tier 3 scorers

    @pytest.mark.skip(reason="Requires full Community Notes scorer integration")
    @pytest.mark.slow
    def test_tier_4_scoring_execution(self, tier_datasets):
        """Test scoring execution on Tier 4 dataset with full pipeline."""
        _notes, _ratings, _enrollment = tier_datasets["tier_4_75000"]
        # TODO: Run actual scoring with full pipeline


class TestDataQuality:
    """Test quality and validity of generated test data."""

    def test_notes_have_required_fields(self, generator):
        """Test that generated notes have all required fields."""
        notes, _, _ = generator.generate_dataset(100, ratings_per_note=5)

        required_fields = {
            "noteId",
            "noteAuthorParticipantId",
            "createdAtMillis",
            "tweetId",
            "summary",
            "classification",
        }

        for note in notes:
            assert all(field in note for field in required_fields), (
                f"Note missing required fields: {required_fields - set(note.keys())}"
            )

    def test_ratings_have_required_fields(self, generator):
        """Test that generated ratings have all required fields."""
        _, ratings, _ = generator.generate_dataset(100, ratings_per_note=5)

        required_fields = {
            "raterParticipantId",
            "noteId",
            "createdAtMillis",
            "helpfulnessLevel",
        }

        for rating in ratings:
            assert all(field in rating for field in required_fields), (
                f"Rating missing required fields: {required_fields - set(rating.keys())}"
            )

    def test_enrollment_has_required_fields(self, generator):
        """Test that generated enrollment has all required fields."""
        _, _, enrollment = generator.generate_dataset(100, ratings_per_note=5)

        required_fields = {
            "participantId",
            "enrollmentState",
            "successfulRatingNeededToEarnIn",
            "timestampOfLastStateChange",
        }

        for entry in enrollment:
            assert all(field in entry for field in required_fields), (
                f"Enrollment missing required fields: {required_fields - set(entry.keys())}"
            )

    def test_ratings_reference_valid_notes(self, generator):
        """Test that ratings reference valid note IDs."""
        notes, ratings, _ = generator.generate_dataset(100, ratings_per_note=5)

        note_ids = {note["noteId"] for note in notes}

        for rating in ratings:
            assert rating["noteId"] in note_ids, (
                f"Rating references invalid note ID: {rating['noteId']}"
            )

    def test_enrollment_covers_authors_and_raters(self, generator):
        """Test that enrollment includes both authors and raters."""
        notes, ratings, enrollment = generator.generate_dataset(100, ratings_per_note=5)

        participant_ids = {entry["participantId"] for entry in enrollment}
        author_ids = {note["noteAuthorParticipantId"] for note in notes}
        rater_ids = {rating["raterParticipantId"] for rating in ratings}

        # All authors should be enrolled
        missing_authors = author_ids - participant_ids
        assert not missing_authors, f"Authors not enrolled: {missing_authors}"

        # All raters should be enrolled
        missing_raters = rater_ids - participant_ids
        assert not missing_raters, f"Raters not enrolled: {missing_raters}"


class TestTierTransitions:
    """Test smooth transitions between tiers."""

    def test_transition_tier_0_to_0_5(self, selector, generator):
        """Test transition from Tier 0 to Tier 0.5 at 200 notes."""
        # Generate datasets just below and at the boundary
        notes_199, _, _ = generator.generate_dataset(199, ratings_per_note=5)
        notes_200, _, _ = generator.generate_dataset(200, ratings_per_note=5)

        tier_199 = selector.select_tier(len(notes_199))
        tier_200 = selector.select_tier(len(notes_200))

        assert tier_199.tier_id == "tier-0"
        assert tier_200.tier_id == "tier-0.5"

    def test_transition_tier_0_5_to_1(self, selector, generator):
        """Test transition from Tier 0.5 to Tier 1 at 1000 notes."""
        notes_999, _, _ = generator.generate_dataset(999, ratings_per_note=5)
        notes_1000, _, _ = generator.generate_dataset(1000, ratings_per_note=5)

        tier_999 = selector.select_tier(len(notes_999))
        tier_1000 = selector.select_tier(len(notes_1000))

        assert tier_999.tier_id == "tier-0.5"
        assert tier_1000.tier_id == "tier-1"

    def test_transition_tier_1_to_2(self, selector, generator):
        """Test transition from Tier 1 to Tier 2 at 5000 notes."""
        notes_4999, _, _ = generator.generate_dataset(4999, ratings_per_note=6)
        notes_5000, _, _ = generator.generate_dataset(5000, ratings_per_note=6)

        tier_4999 = selector.select_tier(len(notes_4999))
        tier_5000 = selector.select_tier(len(notes_5000))

        assert tier_4999.tier_id == "tier-1"
        assert tier_5000.tier_id == "tier-2"


class TestScorerConfiguration:
    """Test that correct scorers are configured for each tier."""

    def test_tier_0_scorer_configuration(self, selector, tier_datasets):
        """Test Tier 0 has no scorers (test mode)."""
        notes, _, _ = tier_datasets["tier_0_150"]
        tier = selector.select_tier(len(notes))

        assert len(tier.enabled_scorers) == 0
        assert tier.confidence_level == "very_low"

    def test_tier_0_5_scorer_configuration(self, selector, tier_datasets):
        """Test Tier 0.5 uses MFCoreScorer with low confidence."""
        notes, _, _ = tier_datasets["tier_0.5_500"]
        tier = selector.select_tier(len(notes))

        assert Scorers.MFCoreScorer in tier.enabled_scorers
        assert len(tier.enabled_scorers) == 1
        assert tier.confidence_level == "low"

    def test_tier_1_scorer_configuration(self, selector, tier_datasets):
        """Test Tier 1 uses MFCoreScorer with medium confidence."""
        notes, _, _ = tier_datasets["tier_1_2000"]
        tier = selector.select_tier(len(notes))

        assert Scorers.MFCoreScorer in tier.enabled_scorers
        assert len(tier.enabled_scorers) == 1
        assert tier.confidence_level == "medium"

    def test_tier_2_scorer_configuration(self, selector, tier_datasets):
        """Test Tier 2 adds MFExpansionScorer."""
        notes, _, _ = tier_datasets["tier_2_7500"]
        tier = selector.select_tier(len(notes))

        assert Scorers.MFCoreScorer in tier.enabled_scorers
        assert Scorers.MFExpansionScorer in tier.enabled_scorers
        assert len(tier.enabled_scorers) == 2
        assert tier.confidence_level == "high"

    @pytest.mark.slow
    def test_tier_3_scorer_configuration(self, selector, tier_datasets):
        """Test Tier 3 adds group scorers."""
        notes, _, _ = tier_datasets["tier_3_25000"]
        tier = selector.select_tier(len(notes))

        assert Scorers.MFCoreScorer in tier.enabled_scorers
        assert Scorers.MFExpansionScorer in tier.enabled_scorers
        assert Scorers.MFGroupScorer in tier.enabled_scorers
        assert Scorers.MFExpansionPlusScorer in tier.enabled_scorers
        assert len(tier.enabled_scorers) == 4
        assert tier.confidence_level == "very_high"

    @pytest.mark.slow
    def test_tier_4_scorer_configuration(self, selector, tier_datasets):
        """Test Tier 4 uses full pipeline."""
        notes, _, _ = tier_datasets["tier_4_75000"]
        tier = selector.select_tier(len(notes))

        assert Scorers.MFCoreScorer in tier.enabled_scorers
        assert Scorers.MFExpansionScorer in tier.enabled_scorers
        assert Scorers.MFGroupScorer in tier.enabled_scorers
        assert Scorers.MFExpansionPlusScorer in tier.enabled_scorers
        assert Scorers.MFMultiGroupScorer in tier.enabled_scorers
        assert len(tier.enabled_scorers) == 5
        assert tier.confidence_level == "maximum"
